#!/usr/bin/env bash
set -euo pipefail

TASK="${1:-}"
if [ -z "$TASK" ]; then
  echo "Usage: ./run_task.sh <task>"
  echo "Tasks: daily_set, explore_on_bing, visual_search, misc_cards, required_searches, bonus_points, all"
  exit 1
fi

ROOT="$HOME/rewards-farmer-main"
LOG_DIR="$ROOT/logs"
IMAGE="rewards-farmer-main-rewards-farmer:latest"
mkdir -p "$LOG_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/web-run-${TASK}-${TS}.log"
EXTRA_ENV=()

if [ -n "${VISUAL_SEARCH_RUNS:-}" ]; then
  EXTRA_ENV+=(-e "VISUAL_SEARCH_RUNS=${VISUAL_SEARCH_RUNS}")
fi

if [ -n "${REQUIRED_SEARCH_RUNS:-}" ]; then
  EXTRA_ENV+=(-e "REQUIRED_SEARCH_RUNS=${REQUIRED_SEARCH_RUNS}")
fi

# Ensure no other container keeps profile locks.
docker rm -f exciting_mayer rewards-web-once >/dev/null 2>&1 || true
ids=$(docker ps -aq --filter ancestor="$IMAGE")
if [ -n "$ids" ]; then
  docker rm -f $ids >/dev/null 2>&1 || true
fi

# Remove stale Chromium singleton locks.
docker run --rm --entrypoint /bin/bash \
  -v "$ROOT/edge-profile:/data/edge-profile" \
  "$IMAGE" \
  -lc 'rm -f /data/edge-profile/SingletonLock /data/edge-profile/SingletonCookie /data/edge-profile/SingletonSocket; find /data/edge-profile -maxdepth 2 -name "Singleton*" -delete' >/dev/null 2>&1 || true

set +e
timeout --signal=TERM 1800 docker run --rm --name rewards-web-once \
  -e RUN_AUTOMATION=1 \
  -e START_EDGE_ON_BOOT=0 \
  -e REWARDS_TASK="$TASK" \
  "${EXTRA_ENV[@]}" \
  -v "$ROOT/edge-profile:/data/edge-profile" \
  -v "$ROOT/src/rewards_tasks.py:/app/src/rewards_tasks.py:ro" \
  "$IMAGE" \
  >> "$LOG_FILE" 2>&1
status=$?
set -e

docker rm -f rewards-web-once >/dev/null 2>&1 || true
echo "Log: $LOG_FILE"
exit $status
