#!/usr/bin/env bash
# Full daily web flow. Was server-only until 2026-09-09 (prod cron entrypoint);
# now tracked. Profile argument: 'default' keeps the historical edge-profile dir;
# a named profile mounts edge-profiles/<name> (registry: profiles/README.md).
set -euo pipefail
PROFILE="${1:-default}"
ROOT="$HOME/rewards-farmer-main"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

case "$PROFILE" in
  default) PROFILE_DIR="$ROOT/edge-profile"; SUFFIX="" ;;
  *)       PROFILE_DIR="$ROOT/edge-profiles/$PROFILE"; SUFFIX="-$PROFILE" ;;
esac
if [ ! -d "$PROFILE_DIR" ]; then
  echo "no web profile '$PROFILE' (looked in: $PROFILE_DIR)" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/web-run${SUFFIX}-$TS.log"

# Ensure no other container holds the Edge profile directory lock.
docker rm -f exciting_mayer rewards-web-once >/dev/null 2>&1 || true
ids=$(docker ps -aq --filter ancestor=rewards-farmer-main-rewards-farmer:latest)
if [ -n "$ids" ]; then
  docker rm -f $ids >/dev/null 2>&1 || true
fi

LOCK_CLEANUP='rm -f /data/edge-profile/SingletonLock /data/edge-profile/SingletonCookie /data/edge-profile/SingletonSocket && find /data/edge-profile -maxdepth 2 -name "Singleton*" -exec rm -f {} +'

# Remove stale Chromium lock artifacts in profile (container runs as root).
docker run --rm --entrypoint /bin/bash \
  -v "$PROFILE_DIR:/data/edge-profile" \
  rewards-farmer-main-rewards-farmer:latest \
  -lc "$LOCK_CLEANUP" >/dev/null 2>&1 || true

# Hard timeout protects cron from hanging on terminal input waits.
set +e
timeout --signal=TERM 1800 docker run --rm --name rewards-web-once \
  -e RUN_AUTOMATION=1 \
  -e START_EDGE_ON_BOOT=0 \
  -v "$PROFILE_DIR:/data/edge-profile" \
  -v "$ROOT/src/rewards_tasks.py:/app/src/rewards_tasks.py:ro" \
  rewards-farmer-main-rewards-farmer:latest \
  >> "$LOG_FILE" 2>&1
status=$?
set -e

docker rm -f rewards-web-once >/dev/null 2>&1 || true
exit $status
