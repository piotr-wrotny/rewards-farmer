#!/usr/bin/env bash
# Guards for scripts/mobile_profile_preflight.sh with fake bing/adb.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
chk() { if [ "$2" != "$3" ]; then echo "FAIL $1: got '$2' want '$3'"; fail=1; else echo "ok $1"; fi; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_BING="$TMP/fake-bing.sh"
FAKE_ADB="$TMP/fake-adb.sh"
VAR="$TMP/variants"
mkdir -p "$VAR/profileA/system"
printf "<xml/>" > "$VAR/profileA/system/packages.xml"
# Ensure the profile has enough entries for the seed-integrity floor.
for i in $(seq 1 520); do
  touch "$VAR/profileA/f$i"
done

cat > "$FAKE_BING" <<'EOF'
#!/usr/bin/env bash
set -eu
cmd="${1:-}"; shift || true
case "$cmd" in
  use)
    profile="${1:-}"
    [ -d "${BING_VAR}/$profile" ] || exit 3
    echo "active=$profile"
    ;;
  run)
    action="${1:-}"; shift || true
    case "$action" in
      points-snapshot)
        echo '{"profile":"profileA","state":"points_snapshot","total_points":"1234","daily_points":{"start":"20/120","end":"20/120"}}'
        ;;
      rewards)
        state="${FAKE_REWARDS_STATE:-wall}"
        echo "{\"profile\":\"profileA\",\"state\":\"$state\",\"articles_read\":0}"
        ;;
      *)
        exit 2
        ;;
    esac
    ;;
  *)
    exit 2
    ;;
esac
EOF

cat > "$FAKE_ADB" <<'EOF'
#!/usr/bin/env bash
set -eu
if [ "${1:-}" = "-s" ] && [ "${3:-}" = "shell" ]; then
  echo "User #0 state=RUNNING_UNLOCKED"
  exit 0
fi
exit 0
EOF

chmod +x "$FAKE_BING" "$FAKE_ADB"

SCRIPT="./scripts/mobile_profile_preflight.sh"
COMMON_ENV=(
  "BING_SH=$FAKE_BING"
  "ADB=$FAKE_ADB"
  "BING_VAR=$VAR"
  "BING_PORT=5555"
)

# pre-login succeeds when probe says wall.
env "${COMMON_ENV[@]}" FAKE_REWARDS_STATE=wall bash "$SCRIPT" pre-login profileA >/dev/null 2>&1
chk pre-login-wall $? 0

# pre-login fails when probe says signed-in-ish state.
env "${COMMON_ENV[@]}" FAKE_REWARDS_STATE=rte bash "$SCRIPT" pre-login profileA >/dev/null 2>&1
chk pre-login-not-wall $? 2

# post-login fails when probe is still wall.
env "${COMMON_ENV[@]}" FAKE_REWARDS_STATE=wall bash "$SCRIPT" post-login profileA >/dev/null 2>&1
chk post-login-wall $? 2

# post-login succeeds when state != wall.
env "${COMMON_ENV[@]}" FAKE_REWARDS_STATE=done bash "$SCRIPT" post-login profileA >/dev/null 2>&1
chk post-login-done $? 0

exit $fail
