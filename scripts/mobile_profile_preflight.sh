#!/usr/bin/env bash
# Preflight guardrails for onboarding a mobile profile on ReDroid.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BING_SH="${BING_SH:-$ROOT/bing.sh}"
ADB="${ADB:-adb}"
VAR="${BING_VAR:-$HOME/redroid-variants}"
PORT="${BING_PORT:-5555}"
SERIAL="127.0.0.1:$PORT"
LOCK="/tmp/bing-$PORT.lock"

usage() {
  cat >&2 <<EOF
Usage:
  scripts/mobile_profile_preflight.sh pre-login <profile>
  scripts/mobile_profile_preflight.sh post-login <profile>

Checks:
  pre-login  - seed integrity + slot/adb readiness + expects rewards state=wall
  post-login - slot/adb readiness + expects rewards state!=wall
EOF
  exit 2
}

die() {
  echo "[FAIL] $1" >&2
  exit "${2:-2}"
}

ok() {
  echo "[OK] $1"
}

extract_json_line() {
  python3 -c "import json, re, sys
ansi = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
for raw in reversed(sys.stdin.read().splitlines()):
    line = ansi.sub('', raw).strip()
    if '{' not in line or '}' not in line:
        continue
    candidate = line[line.find('{'):line.rfind('}') + 1]
    try:
        json.loads(candidate)
    except Exception:
        continue
    print(candidate)
    break"
}

json_get() {
  local json="$1" key="$2"
  python3 - "$json" "$key" <<'PY'
import json, sys
obj = json.loads(sys.argv[1])
key = sys.argv[2]
cur = obj
for part in key.split("."):
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
print("" if cur is None else cur)
PY
}

run_capture() {
  local __outvar="$1"
  shift
  local captured rc
  set +e
  captured="$("$@" 2>&1)"
  rc=$?
  set -e
  printf -v "$__outvar" "%s" "$captured"
  return "$rc"
}

profile_path() {
  echo "$VAR/$1"
}

check_seed_integrity() {
  local profile="$1"
  local p entries
  p="$(profile_path "$profile")"
  [ -d "$p" ] || die "missing variant dir: $p" 3
  if ! docker run --rm -v "$p:/v:ro" busybox test -f /v/system/packages.xml >/dev/null 2>&1; then
    die "seed looks invalid: missing system/packages.xml in $p" 3
  fi
  entries="$(docker run --rm -v "$p:/v:ro" busybox sh -c 'find /v -mindepth 1 2>/dev/null | wc -l' 2>/dev/null | tr -d ' ')"
  [ "${entries:-0}" -ge 500 ] || die "seed looks too small ($entries entries): $p" 3
  ok "seed integrity: $p ($entries entries)"
}

check_slot_lock() {
  local holder
  if flock -n "$LOCK" true 2>/dev/null; then
    ok "slot lock is free: $LOCK"
    return 0
  fi
  holder="unknown"
  if command -v fuser >/dev/null 2>&1; then
    holder="$(fuser "$LOCK" 2>/dev/null | tr -s ' ' | sed 's/^ //')"
    [ -n "$holder" ] || holder="unknown"
  fi
  die "slot lock busy: $LOCK holder=$holder" 3
}

switch_profile() {
  local profile="$1" out=""
  if ! run_capture out "$BING_SH" use "$profile"; then
    die "bing.sh use $profile failed:
$out" 3
  fi
  ok "active profile switched: $profile"
}

check_running_user() {
  local out
  if ! out="$("$ADB" -s "$SERIAL" shell "dumpsys activity users 2>/dev/null | grep -m1 'User #0'" 2>/dev/null)"; then
    die "adb user-state probe failed for $SERIAL" 3
  fi
  echo "$out" | grep -q "RUNNING" || die "android user is not RUNNING on $SERIAL: $out" 3
  ok "android user ready on $SERIAL"
}

run_points_snapshot() {
  local profile="$1" out="" json state total daily
  if ! run_capture out "$BING_SH" run points-snapshot --profile "$profile" --post-run-cleanup keep-running; then
    die "points-snapshot failed:
$out" 3
  fi
  json="$(printf '%s\n' "$out" | extract_json_line)"
  [ -n "$json" ] || die "points-snapshot returned no JSON payload" 3
  state="$(json_get "$json" "state")"
  [ "$state" = "points_snapshot" ] || die "unexpected points-snapshot state='$state'" 3
  total="$(json_get "$json" "total_points")"
  daily="$(json_get "$json" "daily_points.end")"
  ok "points snapshot readable: total=${total:-n/a} daily=${daily:-n/a}"
}

probe_rewards_state() {
  local profile="$1" out="" json state
  if ! run_capture out "$BING_SH" run rewards --profile "$profile" --iters 0 --no-debug --post-run-cleanup keep-running; then
    die "rewards probe failed:
$out" 3
  fi
  json="$(printf '%s\n' "$out" | extract_json_line)"
  [ -n "$json" ] || die "rewards probe returned no JSON payload" 3
  state="$(json_get "$json" "state")"
  [ -n "$state" ] || die "rewards probe returned empty state" 3
  echo "$state"
}

main() {
  local mode="${1:-}" profile="${2:-}" rewards_state
  [ -n "$mode" ] || usage
  [ -n "$profile" ] || usage
  case "$mode" in
    pre-login|post-login) ;;
    *) usage ;;
  esac
  [ -x "$BING_SH" ] || die "bing.sh not executable: $BING_SH" 3
  command -v python3 >/dev/null 2>&1 || die "python3 is required" 3

  if [ "$mode" = "pre-login" ]; then
    check_seed_integrity "$profile"
  fi

  check_slot_lock
  switch_profile "$profile"
  check_running_user
  run_points_snapshot "$profile"

  rewards_state="$(probe_rewards_state "$profile")"
  if [ "$mode" = "pre-login" ]; then
    [ "$rewards_state" = "wall" ] || die "expected pre-login state=wall, got state=$rewards_state. Seed may be contaminated or already signed in." 2
    ok "pre-login gate passed (state=wall)"
    echo "NEXT: run scrcpy login on $profile, then run:"
    echo "  scripts/mobile_profile_preflight.sh post-login $profile"
    exit 0
  fi

  [ "$rewards_state" != "wall" ] || die "post-login gate failed: state=wall (still logged out)" 2
  ok "post-login gate passed (state=$rewards_state)"
  echo "NEXT: create safety snapshot:"
  echo "  docker stop redroid"
  echo "  docker run --rm -v \$HOME:/host busybox sh -c 'tar -C /host/redroid-variants/$profile -czf /host/profile-snapshots/$profile-signedin.tar.gz .'"
  echo "  tar -tzf ~/profile-snapshots/$profile-signedin.tar.gz | grep system/packages.xml >/dev/null"
  echo "  docker start redroid"
}

main "$@"
