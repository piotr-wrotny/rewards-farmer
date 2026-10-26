#!/usr/bin/env bash
# Server-wide maintenance gate and safe stop/resume helpers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAINTENANCE_FILE="${REWARDS_MAINTENANCE_FILE:-$ROOT/.maintenance-mode}"
LOCK_FILE="${BING_LOCK_FILE:-/tmp/bing-5555.lock}"
WEB_IMAGE="${REWARDS_WEB_IMAGE:-rewards-farmer-main-rewards-farmer:latest}"
TARGET_PATTERN='bing\.sh run daily|run_daily\.sh|run_task\.sh|mobile_daily_dispatcher\.sh'

usage() {
  cat <<'EOF'
Usage:
  scripts/server_maintenance.sh status
  scripts/server_maintenance.sh enable
  scripts/server_maintenance.sh disable
  scripts/server_maintenance.sh kill-switch [--hard] [--timeout SEC]
EOF
}

maintenance_state() {
  if [ -f "$MAINTENANCE_FILE" ]; then
    echo "ON"
  else
    echo "OFF"
  fi
}

list_target_procs() {
  ps -eo pid=,cmd= \
    | grep -E "$TARGET_PATTERN" \
    | grep -v grep \
    || true
}

list_target_pids() {
  list_target_procs | awk '{print $1}' || true
}

list_lock_holders() {
  fuser "$LOCK_FILE" 2>/dev/null | tr -s ' ' | sed 's/^ //' || true
}

list_image_containers() {
  docker ps --filter "ancestor=$WEB_IMAGE" --format '{{.Names}}' || true
}

list_web_login_containers() {
  docker ps --format '{{.Names}}' | grep '^rewards-web-login-' || true
}

list_all_target_containers() {
  {
    list_image_containers
    list_web_login_containers
  } | sed '/^$/d' | sort -u
}

print_status() {
  local pids lock_holders containers
  pids="$(list_target_pids | tr '\n' ' ' | sed 's/ *$//')"
  lock_holders="$(list_lock_holders)"
  containers="$(list_all_target_containers | paste -sd, -)"

  echo "MAINTENANCE=$(maintenance_state)"
  echo "MAINTENANCE_FILE=$MAINTENANCE_FILE"
  echo "LOCK_FILE=$LOCK_FILE"
  echo "LOCK_HOLDERS=${lock_holders:-}"
  echo "TARGET_PIDS=${pids:-}"
  echo "TARGET_CONTAINERS=${containers:-}"
  echo "TARGET_PROCESSES_BEGIN"
  list_target_procs
  echo "TARGET_PROCESSES_END"
}

terminate_target_pids() {
  local signal="$1"
  local pid
  while read -r pid; do
    [ -n "$pid" ] || continue
    kill "-$signal" "$pid" 2>/dev/null || true
  done <<EOF
$(list_target_pids)
EOF
}

stop_target_containers() {
  local timeout_s="${1:-20}"
  local name
  while read -r name; do
    [ -n "$name" ] || continue
    docker stop -t "$timeout_s" "$name" >/dev/null 2>&1 || true
  done <<EOF
$(list_all_target_containers)
EOF
}

is_idle() {
  if [ -n "$(list_target_pids)" ]; then
    return 1
  fi
  if [ -n "$(list_lock_holders)" ]; then
    return 1
  fi
  if [ -n "$(list_all_target_containers)" ]; then
    return 1
  fi
  return 0
}

wait_until_idle() {
  local timeout_s="$1"
  local start now
  start="$(date +%s)"
  while true; do
    if is_idle; then
      return 0
    fi
    now="$(date +%s)"
    if [ $((now - start)) -ge "$timeout_s" ]; then
      return 1
    fi
    sleep 1
  done
}

cmd="${1:-status}"
shift || true

case "$cmd" in
  status)
    print_status
    ;;
  enable)
    touch "$MAINTENANCE_FILE"
    echo "maintenance enabled: $MAINTENANCE_FILE"
    print_status
    ;;
  disable)
    rm -f "$MAINTENANCE_FILE"
    echo "maintenance disabled: $MAINTENANCE_FILE"
    print_status
    ;;
  kill-switch)
    HARD=0
    TIMEOUT=45
    while [ $# -gt 0 ]; do
      case "$1" in
        --hard) HARD=1; shift ;;
        --timeout) TIMEOUT="${2:-}"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; usage >&2; exit 2 ;;
      esac
    done
    touch "$MAINTENANCE_FILE"
    echo "[KILL] maintenance enabled: $MAINTENANCE_FILE"
    terminate_target_pids TERM
    stop_target_containers 20
    if wait_until_idle "$TIMEOUT"; then
      echo "[KILL] idle reached after soft stop"
      print_status
      exit 0
    fi
    echo "[KILL] soft stop timeout (${TIMEOUT}s)"
    if [ "$HARD" -ne 1 ]; then
      print_status
      exit 1
    fi
    echo "[KILL] hard stop escalation"
    terminate_target_pids KILL
    stop_target_containers 5
    if wait_until_idle 15; then
      echo "[KILL] idle reached after hard stop"
      print_status
      exit 0
    fi
    echo "[KILL] unable to reach idle after hard stop" >&2
    print_status
    exit 1
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
