#!/usr/bin/env bash
# Retry-first dispatcher for mobile daily runs (domain profiles only).
# Intended to be started by cron every 10-15 minutes; it picks at most one profile
# per invocation, respecting cooldown and per-day retry limits.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
MAINTENANCE_FILE="${REWARDS_MAINTENANCE_FILE:-$ROOT/.maintenance-mode}"
REWARDS_IGNORE_MAINTENANCE="${REWARDS_IGNORE_MAINTENANCE:-0}"
mkdir -p "$LOG_DIR"

LOCK_DIR="/tmp/bing-mobile-dispatcher.lockdir"
TODAY="$(date +%Y%m%d)"
STATE_FILE="$LOG_DIR/mobile-dispatcher-retries-$TODAY.tsv"

COOLDOWN_MINUTES="${BING_DISPATCHER_COOLDOWN_MINUTES:-15}"
MAX_RETRIES_PER_DAY="${BING_DISPATCHER_MAX_RETRIES_PER_DAY:-2}"
DAILY_TARGET="${BING_DISPATCHER_DAILY_TARGET:-120}"

DEFAULT_PROFILES=(
  "domena1-prod"
  "domena2-prod"
  "domena3-prod"
  "domena4-prod"
  "domena5-prod"
  "domena6-prod"
  "domena7-prod"
  "domena8-prod"
  "domena9-prod"
  "domena10-prod"
  "domena11-prod"
  "r_domena_01"
)

usage() {
  cat <<'EOF'
Usage:
  scripts/mobile_daily_dispatcher.sh dispatch
  scripts/mobile_daily_dispatcher.sh status

Env:
  BING_DISPATCHER_PROFILES=comma,separated,list
  BING_DISPATCHER_COOLDOWN_MINUTES=15
  BING_DISPATCHER_MAX_RETRIES_PER_DAY=2
  BING_DISPATCHER_DAILY_TARGET=120
EOF
}

init_state_file() {
  if [ ! -f "$STATE_FILE" ]; then
    : > "$STATE_FILE"
  fi
}

get_profiles() {
  if [ -n "${BING_DISPATCHER_PROFILES:-}" ]; then
    IFS=',' read -r -a PROFILES <<<"$BING_DISPATCHER_PROFILES"
  else
    PROFILES=("${DEFAULT_PROFILES[@]}")
  fi
}

retry_count() {
  local profile="$1"
  awk -F'\t' -v p="$profile" '$1==p {print $2}' "$STATE_FILE" | tail -n1
}

set_retry_count() {
  local profile="$1" count="$2"
  local tmp
  tmp="$(mktemp)"
  awk -F'\t' -v p="$profile" '$1!=p' "$STATE_FILE" > "$tmp"
  printf "%s\t%s\n" "$profile" "$count" >> "$tmp"
  mv "$tmp" "$STATE_FILE"
}

inc_retry_count() {
  local profile="$1"
  local cur
  cur="$(retry_count "$profile")"
  cur="${cur:-0}"
  set_retry_count "$profile" "$((cur + 1))"
}

latest_log_today() {
  local profile="$1"
  ls -1t "$LOG_DIR/bing-$profile-daily-$TODAY-"*.log 2>/dev/null | head -1 || true
}

age_minutes() {
  local path="$1"
  local now mtime
  now="$(date +%s)"
  mtime="$(stat -c %Y "$path")"
  echo $(((now - mtime) / 60))
}

log_done() {
  local path="$1"
  grep -q 'DONE state=daily_done' "$path"
}

pick_candidate() {
  local profile last_log last_age retries
  for profile in "${PROFILES[@]}"; do
    last_log="$(latest_log_today "$profile")"
    retries="$(retry_count "$profile")"
    retries="${retries:-0}"
    if [ -z "$last_log" ]; then
      echo "$profile|no-run-today|$retries"
      return 0
    fi
    last_age="$(age_minutes "$last_log")"
    if [ "$last_age" -lt "$COOLDOWN_MINUTES" ]; then
      continue
    fi
    if log_done "$last_log"; then
      continue
    fi
    if [ "$retries" -ge "$MAX_RETRIES_PER_DAY" ]; then
      continue
    fi
    echo "$profile|retry-needed|$retries"
    return 0
  done
  return 1
}

dispatch_once() {
  if [ "$REWARDS_IGNORE_MAINTENANCE" != 1 ] && [ -f "$MAINTENANCE_FILE" ]; then
    echo "[DISPATCH] maintenance mode enabled ($MAINTENANCE_FILE); skipping dispatch"
    return 0
  fi
  local picked profile reason retries ts log_file run_rc run_log
  picked="$(pick_candidate || true)"
  if [ -z "$picked" ]; then
    echo "[DISPATCH] no eligible profile"
    return 0
  fi
  IFS='|' read -r profile reason retries <<<"$picked"
  ts="$(date +%Y%m%d-%H%M%S)"
  log_file="$LOG_DIR/mobile-dispatcher-$ts.log"
  echo "[DISPATCH] profile=$profile reason=$reason retries_today=$retries target=$DAILY_TARGET cooldown_min=$COOLDOWN_MINUTES"
  set +e
  BING_DAILY_TARGET="$DAILY_TARGET" \
    "$ROOT/bing.sh" run daily --profile "$profile" --no-debug 2>&1 | tee -a "$log_file"
  run_rc=${PIPESTATUS[0]}
  set -e
  run_log="$(latest_log_today "$profile")"
  if [ "$run_rc" -eq 0 ] && [ -n "$run_log" ] && log_done "$run_log"; then
    echo "[DISPATCH] done profile=$profile rc=$run_rc log=$run_log"
    return 0
  fi
  inc_retry_count "$profile"
  echo "[DISPATCH] retry-marked profile=$profile rc=$run_rc log=${run_log:-none}"
  return "$run_rc"
}

status() {
  local profile last_log retries
  printf "profile\tlast_log\tdone\tretries_today\n"
  for profile in "${PROFILES[@]}"; do
    last_log="$(latest_log_today "$profile")"
    retries="$(retry_count "$profile")"
    retries="${retries:-0}"
    if [ -z "$last_log" ]; then
      printf "%s\t-\t-\t%s\n" "$profile" "$retries"
      continue
    fi
    if log_done "$last_log"; then
      printf "%s\t%s\tyes\t%s\n" "$profile" "$(basename "$last_log")" "$retries"
    else
      printf "%s\t%s\tno\t%s\n" "$profile" "$(basename "$last_log")" "$retries"
    fi
  done
}

main() {
  local cmd="${1:-dispatch}"
  case "$cmd" in
    -h|--help|help)
      usage
      exit 0
      ;;
    dispatch|status)
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac

  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[DISPATCH] lock busy ($LOCK_DIR) — another dispatcher run is active"
    exit 0
  fi
  trap 'rmdir "$LOCK_DIR" >/dev/null 2>&1 || true' EXIT

  init_state_file
  get_profiles

  case "$cmd" in
    dispatch) dispatch_once ;;
    status) status ;;
  esac
}

main "$@"
