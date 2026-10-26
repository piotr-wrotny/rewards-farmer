#!/usr/bin/env bash
# Guards for scripts/points_monitor.sh with fake bing/run_task.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
chk() { if [ "$2" != "$3" ]; then echo "FAIL $1: got '$2' want '$3'"; fail=1; else echo "ok $1"; fi; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_BING="$TMP/fake-bing.sh"
FAKE_TASK="$TMP/fake-run-task.sh"
LOG_DIR="$TMP/logs"
mkdir -p "$LOG_DIR"

cat > "$FAKE_BING" <<'EOF'
#!/usr/bin/env bash
set -eu
cmd="${1:-}"; shift || true
[ "$cmd" = "run" ] || exit 2
action="${1:-}"; shift || true
[ "$action" = "points-snapshot" ] || exit 2
profile="unknown"
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) profile="$2"; shift 2 ;;
    *) shift ;;
  esac
done
echo "[12:00:00] noise line with trailing brace }"
case "$profile" in
  profileA)
    echo '{"profile":"profileA","state":"points_snapshot","total_points":"1000","daily_points":{"start":"10/120","end":"120/120"}}'
    ;;
  profileB)
    echo '{"profile":"profileB","state":"points_snapshot","total_points":"250","daily_points":{"start":"10/120","end":"80/120"}}'
    ;;
  *)
    echo '{"profile":"unknown","state":"points_snapshot","total_points":"0","daily_points":{"start":"0/120","end":"0/120"}}'
    ;;
esac
EOF

cat > "$FAKE_TASK" <<'EOF'
#!/usr/bin/env bash
set -eu
echo "bonus:$*" >> "${FAKE_TASK_LOG:?}"
EOF

chmod +x "$FAKE_BING" "$FAKE_TASK"
export FAKE_TASK_LOG="$TMP/task.log"

SCRIPT="./scripts/points_monitor.sh"
COMMON_ENV=(
  "BING_SH=$FAKE_BING"
  "RUN_TASK_SH=$FAKE_TASK"
  "POINTS_LOG_DIR=$LOG_DIR"
  "POINTS_PROFILES=profileA profileB"
)

snap1="$(env "${COMMON_ENV[@]}" bash "$SCRIPT" snapshot before)"
chk snapshot-file-exists "$( [ -f "$snap1" ]; echo $? )" 0
grep -q "^profileA" "$snap1"; chk snapshot-has-profileA $? 0
grep -q "^profileB" "$snap1"; chk snapshot-has-profileB $? 0

env "${COMMON_ENV[@]}" bash "$SCRIPT" claim-and-snapshot after >/dev/null 2>&1
grep -q "bonus_points profileA" "$FAKE_TASK_LOG"; chk claim-called-profileA $? 0
grep -q "bonus_points profileB" "$FAKE_TASK_LOG"; chk claim-called-profileB $? 0

snap2="$(ls -1t "$LOG_DIR"/points-snapshot-after-*.tsv | head -n1)"
diff_out="$TMP/diff.tsv"
env "${COMMON_ENV[@]}" bash "$SCRIPT" diff "$snap1" "$snap2" > "$diff_out"
grep -q "^profileA" "$diff_out"; chk diff-has-profileA $? 0
grep -q "^profileB" "$diff_out"; chk diff-has-profileB $? 0

env "${COMMON_ENV[@]}" bash "$SCRIPT" check-full "$snap1" 120 >/dev/null 2>&1
chk check-full-fails-on-partial $? 1

cat > "$TMP/full-ok.tsv" <<'EOF'
profile	rc	state	total_points	daily_points	snapshot_at
profileA	0	points_snapshot	1000	120/120	2026-10-26T12:00:00+00:00
profileB	0	points_snapshot	1100	120/120	2026-10-26T12:00:00+00:00
EOF
env "${COMMON_ENV[@]}" bash "$SCRIPT" check-full "$TMP/full-ok.tsv" 120 >/dev/null 2>&1
chk check-full-ok $? 0

exit $fail
