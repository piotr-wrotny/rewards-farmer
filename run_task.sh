#!/usr/bin/env bash
set -euo pipefail

TASK="${1:-}"
PROFILE="${2:-default}"
if [ -z "$TASK" ]; then
  echo "Usage: ./run_task.sh <task> [profile]"
  echo "Tasks: daily_set, explore_on_bing, visual_search, misc_cards, required_searches, bonus_points, all, login_check"
  echo "Profiles: default (= ~/rewards-farmer-main/edge-profile) or a name under edge-profiles/ (registry: profiles/README.md)"
  exit 1
fi

ROOT="$HOME/rewards-farmer-main"
LOG_DIR="$ROOT/logs"
IMAGE="rewards-farmer-main-rewards-farmer:latest"
MAINTENANCE_FILE="${REWARDS_MAINTENANCE_FILE:-$ROOT/.maintenance-mode}"
REWARDS_IGNORE_MAINTENANCE="${REWARDS_IGNORE_MAINTENANCE:-0}"
mkdir -p "$LOG_DIR"

if [ "$REWARDS_IGNORE_MAINTENANCE" != 1 ] && [ "$TASK" != "login_check" ] && [ -f "$MAINTENANCE_FILE" ]; then
  echo "maintenance mode enabled ($MAINTENANCE_FILE); refusing task '$TASK'" >&2
  exit 3
fi

# Web credential profiles are separate user-data-dir volumes (one Microsoft account
# each). 'default' is the historical edge-profile dir; named profiles live under
# edge-profiles/<name> and mount at the same /data/edge-profile path in the image.
case "$PROFILE" in
  default) PROFILE_DIR="$ROOT/edge-profile"; SUFFIX="" ;;
  *)       PROFILE_DIR="$ROOT/edge-profiles/$PROFILE"; SUFFIX="-$PROFILE" ;;
esac
if [ ! -d "$PROFILE_DIR" ]; then
  echo "no web profile '$PROFILE' (looked in: $PROFILE_DIR)" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/web-run-${TASK}${SUFFIX}-${TS}.log"
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

LOCK_CLEANUP='rm -f /data/edge-profile/SingletonLock /data/edge-profile/SingletonCookie /data/edge-profile/SingletonSocket && find /data/edge-profile -maxdepth 2 -name "Singleton*" -exec rm -f {} +'

# Remove stale Chromium singleton locks.
docker run --rm --entrypoint /bin/bash \
  -v "$PROFILE_DIR:/data/edge-profile" \
  "$IMAGE" \
  -lc "$LOCK_CLEANUP" >/dev/null 2>&1 || true

set +e
timeout --signal=TERM 1800 docker run --rm --name rewards-web-once \
  -e RUN_AUTOMATION=1 \
  -e START_EDGE_ON_BOOT=0 \
  -e REWARDS_TASK="$TASK" \
  "${EXTRA_ENV[@]}" \
  -v "$PROFILE_DIR:/data/edge-profile" \
  -v "$ROOT/src/rewards_tasks.py:/app/src/rewards_tasks.py:ro" \
  "$IMAGE" \
  >> "$LOG_FILE" 2>&1
status=$?
set -e

docker rm -f rewards-web-once >/dev/null 2>&1 || true
echo "Log: $LOG_FILE"
exit $status
