#!/usr/bin/env bash
# Resume incomplete mobile daily sessions based on today's log state.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
MAINTENANCE_FILE="${REWARDS_MAINTENANCE_FILE:-$ROOT/.maintenance-mode}"
TODAY="$(date +%Y%m%d)"
TARGET="${BING_RESUME_DAILY_TARGET:-120}"
MAX_PROFILES="${BING_RESUME_MAX_PROFILES:-0}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/resume_incomplete_mobile.sh [--dry-run] [--today YYYYMMDD] [--target POINTS] [--max N] [profiles...]

Behavior:
  - without explicit profiles: picks profiles whose latest daily log for the day
    does not contain "DONE state=daily_done".
  - skips profiles where latest log contains "state=wall" (manual login required).
  - runs: ./bing.sh run daily --profile <profile> --no-debug
EOF
}

extract_profile() {
  local file="$1"
  local base tmp
  base="$(basename "$file")"
  tmp="${base#bing-}"
  echo "${tmp%-daily-*}"
}

latest_daily_log() {
  local profile="$1"
  ls -1t "$LOG_DIR/bing-$profile-daily-$TODAY-"*.log 2>/dev/null | head -1 || true
}

is_done_log() {
  local file="$1"
  grep -q 'DONE state=daily_done' "$file"
}

is_wall_log() {
  local file="$1"
  grep -q 'state=wall' "$file"
}

collect_profiles_from_logs() {
  local file profile
  declare -A seen=()
  while read -r file; do
    [ -n "$file" ] || continue
    profile="$(extract_profile "$file")"
    [ -n "$profile" ] || continue
    if [ -n "${seen[$profile]:-}" ]; then
      continue
    fi
    seen["$profile"]=1
    echo "$profile"
  done <<EOF
$(ls -1t "$LOG_DIR"/bing-*-daily-"$TODAY"-*.log 2>/dev/null || true)
EOF
}

resume_profiles() {
  local profiles=("$@")
  local profile latest reason resumed attempted rc
  local -a queue=()
  resumed=0
  attempted=0

  for profile in "${profiles[@]}"; do
    latest="$(latest_daily_log "$profile")"
    if [ -z "$latest" ]; then
      queue+=("$profile")
      continue
    fi
    if is_done_log "$latest"; then
      continue
    fi
    if is_wall_log "$latest"; then
      echo "[RESUME] skip profile=$profile reason=manual_login_required latest=$(basename "$latest")"
      continue
    fi
    queue+=("$profile")
  done

  if [ "${#queue[@]}" -eq 0 ]; then
    echo "[RESUME] no incomplete profiles to resume"
    return 0
  fi

  echo "profile\treason\taction\trun_rc\tlatest_log_after"
  for profile in "${queue[@]}"; do
    latest="$(latest_daily_log "$profile")"
    reason="incomplete_or_missing_daily_log"
    if [ -n "$latest" ]; then
      reason="$(basename "$latest")"
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
      echo -e "${profile}\t${reason}\tpreview\t-\t-"
      continue
    fi
    if [ "$MAX_PROFILES" -gt 0 ] && [ "$attempted" -ge "$MAX_PROFILES" ]; then
      echo "[RESUME] max reached (max=$MAX_PROFILES), stopping"
      break
    fi
    attempted=$((attempted + 1))
    set +e
    BING_DAILY_TARGET="$TARGET" "$ROOT/bing.sh" run daily --profile "$profile" --no-debug
    rc=$?
    set -e
    latest="$(latest_daily_log "$profile")"
    echo -e "${profile}\t${reason}\trun\t${rc}\t${latest##*/}"
    if [ "$rc" -eq 0 ] && [ -n "$latest" ] && is_done_log "$latest"; then
      resumed=$((resumed + 1))
    fi
  done

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[RESUME] preview-only mode"
    return 0
  fi

  echo "[RESUME] completed=$resumed attempted=$attempted"
}

profiles=()
while [ $# -gt 0 ]; do
  case "$1" in
    --today)
      TODAY="${2:-}"
      shift 2
      ;;
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --max)
      MAX_PROFILES="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      profiles+=("$1")
      shift
      ;;
  esac
done

if [ "${#profiles[@]}" -eq 0 ]; then
  mapfile -t profiles < <(collect_profiles_from_logs)
fi

if [ "${#profiles[@]}" -eq 0 ]; then
  echo "[RESUME] no daily logs found for day=$TODAY"
  exit 0
fi

if [ -f "$MAINTENANCE_FILE" ]; then
  echo "maintenance mode enabled ($MAINTENANCE_FILE); disable it before resume" >&2
  exit 3
fi

resume_profiles "${profiles[@]}"
