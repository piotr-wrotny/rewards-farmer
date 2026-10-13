#!/usr/bin/env bash
# Post-run cleanup policy guards for bing.sh with fake docker/adb/python.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
chk() { if [ "$2" != "$3" ]; then echo "FAIL $1: got '$2' want '$3'"; fail=1; else echo "ok $1"; fi; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAKEBIN="$TMP/fakebin"
mkdir -p "$FAKEBIN"

cat > "$FAKEBIN/docker" <<'EOF'
#!/usr/bin/env bash
set -eu
cmd="${1:-}"; shift || true
if [ "$cmd" = "ps" ] && [ "${1:-}" = "-aq" ]; then
  exit 0
fi
if [ "$cmd" = "inspect" ]; then
  fmt="$2"; target="$3"
  if [ "$target" = "${BING_CONT:-redroid-a}" ] && [ "$fmt" = "{{.State.Running}}" ]; then
    echo "true"; exit 0
  fi
  if [ "$target" = "${BING_CONT:-redroid-a}" ] && [ "$fmt" = "{{range .Mounts}}{{if eq .Destination \"/data\"}}{{.Source}}{{end}}{{end}}" ]; then
    echo "${BING_VAR}/profileA"; exit 0
  fi
  exit 1
fi
if [ "$cmd" = "rm" ] || [ "$cmd" = "run" ]; then
  exit 0
fi
if [ "$cmd" = "stop" ]; then
  echo "$*" >> "${DOCKER_STOP_LOG:?}"
  exit 0
fi
exit 0
EOF

cat > "$FAKEBIN/adb" <<'EOF'
#!/usr/bin/env bash
set -eu
if [ "${1:-}" = "connect" ] || [ "${1:-}" = "disconnect" ]; then
  exit 0
fi
if [ "${1:-}" = "-s" ]; then
  serial="${2:-}"
  shift 2
  if [ "${1:-}" = "shell" ]; then
    shift
    cmd="$*"
    case "$cmd" in
      *"dumpsys activity users"*)
        echo "User #0 state=RUNNING_UNLOCKED"
        exit 0
        ;;
      *"input keyevent KEYCODE_HOME"*|*"am force-stop com.microsoft.bing"*)
        echo "$serial|$cmd" >> "${ADB_CLEANUP_LOG:?}"
        if [ "${ADB_CLEANUP_FAIL:-0}" = "1" ]; then
          exit 1
        fi
        exit 0
        ;;
    esac
  fi
fi
exit 0
EOF

cat > "$FAKEBIN/fakepy" <<'EOF'
#!/usr/bin/env bash
echo "fake run"
exit "${FAKE_PY_RC:-0}"
EOF

chmod +x "$FAKEBIN/docker" "$FAKEBIN/adb" "$FAKEBIN/fakepy"

export PATH="$FAKEBIN:$PATH"
export BING_VAR="$TMP/variants"
export BING_PY="$FAKEBIN/fakepy"
export BING_CONT="redroid-a"
export BING_PORT="5557"
export ADB_CLEANUP_LOG="$TMP/cleanup.log"
export DOCKER_STOP_LOG="$TMP/docker-stop.log"
mkdir -p "$BING_VAR/profileA"
: > "$ADB_CLEANUP_LOG"
: > "$DOCKER_STOP_LOG"

# 1) Profile-level lock blocks concurrent run on same profile.
profile_lock="/tmp/bing-profile-5557-profileA.lockdir"
rm -rf "$profile_lock"
mkdir "$profile_lock"
sleep 5 &
lock_holder=$!
echo "$lock_holder" > "$profile_lock/pid"
FAKE_PY_RC=0 ./bing.sh run screenshot --profile profileA >/dev/null 2>&1
chk profile-lock-busy $? 3
kill "$lock_holder" >/dev/null 2>&1 || true
wait "$lock_holder" 2>/dev/null || true
rm -rf "$profile_lock"

# 2) Default mode keeps current behavior and preserves non-zero job exit.
unset BING_POST_RUN_CLEANUP
FAKE_PY_RC=7 ./bing.sh run screenshot --profile profileA >/dev/null 2>&1
chk keep-running-exit $? 7
lines=$(wc -l < "$ADB_CLEANUP_LOG" | tr -d ' ')
chk keep-running-no-cleanup "$lines" 0

# 3) return-home issues KEYCODE_HOME on the active slot serial.
: > "$ADB_CLEANUP_LOG"
FAKE_PY_RC=0 ./bing.sh run screenshot --profile profileA --post-run-cleanup return-home >/dev/null 2>&1
chk return-home-exit $? 0
cleanup_line="$(cat "$ADB_CLEANUP_LOG")"
case "$cleanup_line" in
  "127.0.0.1:5557|input keyevent KEYCODE_HOME") chk return-home-command 0 0 ;;
  *) echo "FAIL return-home-command: got '$cleanup_line'"; fail=1 ;;
esac

# 4) force-stop issues package force-stop.
: > "$ADB_CLEANUP_LOG"
FAKE_PY_RC=0 ./bing.sh run screenshot --profile profileA --post-run-cleanup force-stop >/dev/null 2>&1
chk force-stop-exit $? 0
cleanup_line="$(cat "$ADB_CLEANUP_LOG")"
case "$cleanup_line" in
  "127.0.0.1:5557|am force-stop com.microsoft.bing") chk force-stop-command 0 0 ;;
  *) echo "FAIL force-stop-command: got '$cleanup_line'"; fail=1 ;;
esac

# 5) Cleanup failure does not mask original job rc.
: > "$ADB_CLEANUP_LOG"
ADB_CLEANUP_FAIL=1 FAKE_PY_RC=9 ./bing.sh run screenshot --profile profileA --post-run-cleanup force-stop >/dev/null 2>&1
chk cleanup-failure-preserves-job-rc $? 9
lines=$(wc -l < "$ADB_CLEANUP_LOG" | tr -d ' ')
chk cleanup-failure-command-executed "$lines" 1

# 6) stop-container stops active worker container.
: > "$DOCKER_STOP_LOG"
FAKE_PY_RC=0 ./bing.sh run screenshot --profile profileA --post-run-cleanup stop-container >/dev/null 2>&1
chk stop-container-exit $? 0
lines=$(wc -l < "$DOCKER_STOP_LOG" | tr -d ' ')
chk stop-container-command "$lines" 1

# 7) Invalid cleanup mode fails closed before running the flow.
: > "$ADB_CLEANUP_LOG"
FAKE_PY_RC=0 ./bing.sh run screenshot --profile profileA --post-run-cleanup nope >/dev/null 2>&1
chk invalid-cleanup-mode $? 2
lines=$(wc -l < "$ADB_CLEANUP_LOG" | tr -d ' ')
chk invalid-cleanup-mode-no-command "$lines" 0

exit $fail
