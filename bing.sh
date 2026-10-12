#!/usr/bin/env bash
# Bing mobile flows: one entrypoint for interactive use and server cron (KRON).
# Profiles are unpacked Android /data volumes: ~/redroid-variants/<profile>
# Registry (accounts/snapshots): profiles/README.md. Hazards: docs/re-droid-gotchas.md.
# Exit codes: 0 ok, 2 usage/flow failure, 3 infra.
set -u -o pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
IMG=redroid/redroid:14.0.0-latest
PROPS=(androidboot.redroid_gpu_mode=guest androidboot.redroid_net_ndns=2
       androidboot.redroid_net_dns1=172.20.0.41 androidboot.redroid_net_dns2=172.20.0.42)
PY="${BING_PY:-$ROOT/.venv/bin/python}"
DRIVER="$ROOT/src/bing_mobile_flow.py"
VAR="${BING_VAR:-$HOME/redroid-variants}"
SNAP="$HOME/profile-snapshots"
ADB="${ADB:-adb}"
LOGS="$ROOT/logs"; mkdir -p "$LOGS"
CONT="${BING_CONT:-redroid}"; PORT="${BING_PORT:-5555}"
INNER_PORT="${BING_INNER_PORT:-5555}"
OWNERSHIP_LOCK=/tmp/bing-profile-ownership.lock

serial() { echo "127.0.0.1:$1"; }
die() { echo "$*" >&2; exit "${2:-2}"; }
current() {
  local mount
  mount="$(container_data_mount "$CONT")"
  [ -n "$mount" ] || return 1
  basename "$mount"
}
user_running() { $ADB -s "$(serial $PORT)" shell "dumpsys activity users 2>/dev/null | grep -m1 'User #0'" 2>/dev/null | grep -q RUNNING; }

canon_path() {
  local p="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath -m "$p"; return
  fi
  if command -v readlink >/dev/null 2>&1; then
    readlink -f "$p" 2>/dev/null && return
  fi
  (cd "$p" 2>/dev/null && pwd -P) || echo "$p"
}

profile_path() {
  local p="$1" v="$VAR/$p"
  [ -d "$v" ] || die "no variant $p (known: $(ls "$VAR" 2>/dev/null | tr '\n' ' '))" 3
  canon_path "$v"
}

container_data_mount() {
  local c="$1"
  docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$c" 2>/dev/null || true
}

assert_profile_unowned() {
  local profile="$1" allow_cont="$2"
  local target
  target="$(profile_path "$profile")"
  local ids
  ids="$(docker ps -aq 2>/dev/null || true)"
  [ -n "$ids" ] || return 0
  while IFS= read -r cid; do
    [ -n "$cid" ] || continue
    local name src src_canon state restart
    name="$(docker inspect -f '{{.Name}}' "$cid" 2>/dev/null | sed 's#^/##')"
    [ -n "$name" ] || continue
    [ "$name" = "$allow_cont" ] && continue
    src="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$cid" 2>/dev/null || true)"
    [ -n "$src" ] || continue
    src_canon="$(canon_path "$src")"
    if [ "$src_canon" = "$target" ]; then
      state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
      restart="$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$cid" 2>/dev/null || echo unknown)"
      die "profile '$profile' already mounted by container '$name' (state=$state restart=$restart mount=$src_canon)" 3
    fi
  done <<EOF
$ids
EOF
}

verify_slot_mapping() {
  local profile="$1" target mount
  target="$(profile_path "$profile")"
  mount="$(container_data_mount "$CONT")"
  [ -n "$mount" ] || die "container $CONT has no /data mount; aborting" 3
  mount="$(canon_path "$mount")"
  [ "$mount" = "$target" ] || die "container $CONT mounted $mount, expected $target for profile $profile" 3
}

# Boot-ready means user RUNNING (sys.boot_completed lies; gotchas #6).
wait_ready() {
  for _ in $(seq 1 40); do sleep 3
    $ADB connect "$(serial $PORT)" >/dev/null 2>&1
    user_running && return 0
  done; return 1
}

ensure_container() {
  local p="$1" v running
  v="$VAR/$p"
  running="$(docker inspect -f '{{.State.Running}}' "$CONT" 2>/dev/null || true)"
  if [ "$(current)" = "$p" ] && [ "$running" = true ]; then
    verify_slot_mapping "$p"
    assert_profile_unowned "$p" "$CONT"
    $ADB connect "$(serial $PORT)" >/dev/null 2>&1
    user_running && return 0
  fi

  exec 8>"$OWNERSHIP_LOCK"; flock 8
  assert_profile_unowned "$p" "$CONT"

  running="$(docker inspect -f '{{.State.Running}}' "$CONT" 2>/dev/null || true)"
  if [ "$(current)" = "$p" ] && [ "$running" = true ]; then
    verify_slot_mapping "$p"
    assert_profile_unowned "$p" "$CONT"
    $ADB connect "$(serial $PORT)" >/dev/null 2>&1
    user_running && return 0
  fi
  docker rm -f "$CONT" >/dev/null 2>&1 || true
  # NOTE: publish adbd only (default container port 5555) — host adb server owns 5037.
  docker run -d --name "$CONT" --privileged -v "$v:/data" \
    -p 127.0.0.1:$PORT:$INNER_PORT --restart unless-stopped "$IMG" "${PROPS[@]}" >/dev/null \
    || die "docker run failed" 3
  verify_slot_mapping "$p"
  assert_profile_unowned "$p" "$CONT"
  $ADB disconnect "$(serial $PORT)" >/dev/null 2>&1 || true   # stale state (gotchas #5)
  wait_ready || die "boot timeout on variant $p (user never RUNNING — see docs/re-droid-gotchas.md #1)" 3
}

usage() { echo "usage: bing.sh use|current|status|run|clear|snapshot [--help]" >&2; exit 2; }

cmd="${1:-}"; shift || true
[ -n "$cmd" ] || usage
LOCK=""
case "$cmd" in
  use)
    p="${1:?profile}"
    [ -d "$VAR/$p" ] || die "no variant $p (known: $(ls "$VAR" 2>/dev/null | tr '\n' ' '))" 3
    LOCK=/tmp/bing-$PORT.lock; exec 9>"$LOCK"
    # Non-blocking: device busy with a flow/cron -> fail fast, never queue a
    # mid-flight takeover (d11 2026-09-14: queueing `use` behind cron d3).
    flock -n 9 || die "device busy (holder: $(fuser "$LOCK" 2>/dev/null | tr -s ' ')); retry after run ends" 3
    ensure_container "$p"
    [ "$(current)" = "$p" ] || die "switch failed: active=$(current || echo none), expected $p" 3
    echo "active=$p" ;;
  current)
    echo "active=$(current || echo none)" ;;
  status)
    docker ps --format '{{.Names}}\t{{.Status}}' | grep redroid || echo "no redroid containers"
    echo "variants: $(ls "$VAR" 2>/dev/null | tr '\n' ' ')"
    echo "active: $(current || echo none)"
    user_running && echo "user: RUNNING" || echo "user: NOT RUNNING"
    ls -1t "$LOGS"/bing-*.log 2>/dev/null | head -5 ;;
  run)
    action="${1:?full|search|rewards|read-to-earn|misc-cards|screenshot|daily}"; shift
    prof=""; iters=6; dbg=""
    while [ $# -gt 0 ]; do case "$1" in
      --profile) prof="$2"; shift 2;;
      --iters) iters="$2"; shift 2;;
      --debug|--no-debug) dbg="$1"; shift;;
      *) die "unknown flag $1" 2;; esac; done
    [ -n "$prof" ] || prof="$(current)"
    [ -n "$prof" ] || die "no active profile; pass --profile" 3
    LOCK=/tmp/bing-$PORT.lock; exec 9>"$LOCK"; flock 9
    ensure_container "$prof"
    ts="$(date +%Y%m%d-%H%M%S)"; log="$LOGS/bing-$prof-$action-$ts.log"
    args=("$DRIVER" --serial "$(serial $PORT)" --profile "$prof" --only "$action")
    [ "$action" = daily ] || args+=(--iters "$iters")  # daily: tiles cap stages
    "$PY" "${args[@]}" 2>&1 | tee "$log"; rc=${PIPESTATUS[0]}
    echo "log=$log rc=$rc"; exit $rc ;;
  clear)
    prof=""
    while [ $# -gt 0 ]; do case "$1" in
      --profile) prof="$2"; shift 2;;
      *) die "unknown flag $1" 2;; esac; done
    [ -n "$prof" ] || prof="$(current)"
    [ -n "$prof" ] || die "no active profile; pass --profile" 3
    [ "$prof" = test ] || die "clear is allowed only for profile test (prod would log out)" 3
    LOCK=/tmp/bing-$PORT.lock; exec 9>"$LOCK"; flock 9
    ensure_container "$prof"
    "$PY" "$DRIVER" --serial "$(serial $PORT)" --server-serial "$(serial $PORT)" \
      --profile test --only screenshot --clear \
      || exit $?
    echo "cleared $prof" ;;
  snapshot)
    p="${1:?profile name to save}"
    LOCK=/tmp/bing-5556.lock; exec 9>"$LOCK"; flock 9
    docker ps --format '{{.Names}}' | grep -qx redroid-factory || die "factory not running" 3
    # freeze order is sacred (AGENTS.md): force-stop -> sync -> stop -> tar -> start
    $ADB -s 127.0.0.1:5556 shell am force-stop com.microsoft.bing
    $ADB -s 127.0.0.1:5556 shell sync; sleep 3
    docker stop -t 30 redroid-factory >/dev/null
    docker run --rm -v "$HOME:/host" busybox sh -c \
      "tar -C /host/profile-factory-data -czf /host/profile-snapshots/$p.tar.gz ." || die "tar failed" 3
    docker start redroid-factory >/dev/null
    # never trust a snapshot blind (gotchas #2): require real content. Plain grep
    # (NOT grep -q): -q closes the pipe early -> tar SIGPIPE -> pipefail false alarm.
    tar -tzf "$SNAP/$p.tar.gz" | grep "system/packages.xml" >/dev/null || die "snapshot $p looks empty/corrupt" 3
    ls -la "$SNAP/$p.tar.gz" ;;
  *) usage ;;
esac
