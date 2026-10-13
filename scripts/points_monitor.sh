#!/usr/bin/env bash
# Collect and compare per-profile points snapshots, with optional web bonus claim sweep.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

PROFILES=(
  "prod_1"
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
)

usage() {
  cat >&2 <<EOF
Usage:
  scripts/points_monitor.sh snapshot <label>
  scripts/points_monitor.sh claim-and-snapshot <label>
  scripts/points_monitor.sh diff <before.tsv> <after.tsv>
  scripts/points_monitor.sh check-full <snapshot.tsv> [target=120]
EOF
  exit 2
}

extract_json_line() {
  python3 -c "import sys
for line in reversed(sys.stdin.read().splitlines()):
    line=line.strip()
    if line.startswith('{') and line.endswith('}'):
        print(line); break"
}

snapshot() {
  local label="$1"
  local ts out_file now out rc json parsed
  ts="$(date +%Y%m%d-%H%M%S)"
  out_file="$LOG_DIR/points-snapshot-${label}-${ts}.tsv"
  echo -e "profile\trc\tstate\ttotal_points\tdaily_points\tsnapshot_at" > "$out_file"

  for profile in "${PROFILES[@]}"; do
    now="$(date --iso-8601=seconds)"
    set +e
    out="$("$ROOT/bing.sh" run points-snapshot --profile "$profile" --post-run-cleanup stop-container 2>&1)"
    rc=$?
    set -e
    json="$(printf '%s\n' "$out" | extract_json_line)"

    if [ -z "$json" ]; then
      echo -e "${profile}\t${rc}\tparse_error\t\t\t${now}" >> "$out_file"
      continue
    fi

    parsed="$(python3 -c "import json,sys
obj=json.loads(sys.argv[1])
state=obj.get('state','')
total=obj.get('total_points') or ''
daily=((obj.get('daily_points') or {}).get('end')) or ''
print(f'{state}\\t{total}\\t{daily}')" "$json")"
    echo -e "${profile}\t${rc}\t${parsed}\t${now}" >> "$out_file"
  done

  echo "$out_file"
}

claim_bonus_for_all() {
  for profile in "${PROFILES[@]}"; do
    "$ROOT/run_task.sh" bonus_points "$profile" >/dev/null 2>&1 || true
  done
}

diff_snapshots() {
  local before="$1" after="$2"
  python3 - "$before" "$after" <<'PY'
import sys, csv

before_path, after_path = sys.argv[1], sys.argv[2]

def read_tsv(path):
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            out[row["profile"]] = row
    return out

def parse_int(v):
    if not v:
        return None
    s = str(v).replace(",", "").strip()
    return int(s) if s.isdigit() else None

b = read_tsv(before_path)
a = read_tsv(after_path)

print("profile\ttotal_before\ttotal_after\tdelta\trc_before\trc_after")
for profile in sorted(set(b) | set(a)):
    rb = b.get(profile, {})
    ra = a.get(profile, {})
    tb = parse_int(rb.get("total_points"))
    ta = parse_int(ra.get("total_points"))
    delta = "" if tb is None or ta is None else str(ta - tb)
    print(
        f"{profile}\t{rb.get('total_points','')}\t{ra.get('total_points','')}\t{delta}\t"
        f"{rb.get('rc','')}\t{ra.get('rc','')}"
    )
PY
}

check_full() {
  local snapshot_file="$1"
  local target="${2:-120}"
  python3 - "$snapshot_file" "$target" <<'PY'
import sys, csv, re
path = sys.argv[1]
target = int(sys.argv[2])
bad = []
with open(path, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter="\t")
    for row in r:
        profile = row["profile"]
        daily = (row.get("daily_points") or "").strip()
        rc = row.get("rc", "")
        m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", daily)
        if not m:
            bad.append((profile, rc, daily, "invalid_daily_points"))
            continue
        got, cap = int(m.group(1)), int(m.group(2))
        if got < target or cap < target:
            bad.append((profile, rc, daily, f"below_target_{target}"))

if not bad:
    print(f"FULL_OK target={target}")
    sys.exit(0)

print("FULL_MISSING")
print("profile\trc\tdaily_points\treason")
for row in bad:
    print("\t".join(map(str, row)))
sys.exit(1)
PY
}

cmd="${1:-}"
case "$cmd" in
  snapshot)
    [ $# -eq 2 ] || usage
    snapshot "$2"
    ;;
  claim-and-snapshot)
    [ $# -eq 2 ] || usage
    claim_bonus_for_all
    snapshot "$2"
    ;;
  diff)
    [ $# -eq 3 ] || usage
    diff_snapshots "$2" "$3"
    ;;
  check-full)
    [ $# -ge 2 ] || usage
    check_full "$2" "${3:-120}"
    ;;
  *)
    usage
    ;;
esac
