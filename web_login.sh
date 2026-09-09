#!/usr/bin/env bash
# Provision a WEB credential profile: run the Edge container in login mode with the
# noVNC GUI exposed, the user signs in by hand (agent never sees credentials), then
# stop and verify with ./run_task.sh login_check <profile> (mirror of the mobile
# factory.ps1 login/save flow).
#
#   ./web_login.sh <profile-name> [novnc-port]
#
# Requires: web image built, port 6080 free (or pass another). The named profile's
# user-data-dir lives at edge-profiles/<name>; 'default' targets the historical dir.
set -euo pipefail
PROFILE="${1:?usage: web_login.sh <profile-name> [novnc-port]}"
PORT="${2:-6080}"
ROOT="$HOME/rewards-farmer-main"
IMAGE="rewards-farmer-main-rewards-farmer:latest"

case "$PROFILE" in
  default) PROFILE_DIR="$ROOT/edge-profile" ;;
  *)       PROFILE_DIR="$ROOT/edge-profiles/$PROFILE" ;;
esac

# One Microsoft account per container volume; refuse to hand a signed-in profile
# to the browser GUI unless it already exists (fresh dir = intended target).
if [ ! -d "$PROFILE_DIR" ]; then
  mkdir -p "$PROFILE_DIR"
  echo "created fresh web profile dir: $PROFILE_DIR"
fi
# visual-search asset must resolve inside the volume (AGENTS.md resolution order)
[ -f "$PROFILE_DIR/visual-search-asset.jpg" ] || \
  cp "$ROOT/visual-search-asset.jpg" "$PROFILE_DIR/visual-search-asset.jpg" 2>/dev/null || true

# Same lock hygiene as run_task.sh: never share the volume with an automation run.
docker rm -f exciting_mayer rewards-web-once rewards-web-login >/dev/null 2>&1 || true
ids=$(docker ps -aq --filter ancestor="$IMAGE")
if [ -n "$ids" ]; then
  echo "refusing: a rewards-farmer container is running (would steal the profile lock)" >&2
  exit 3
fi

docker run -d --name rewards-web-login \
  -e START_EDGE_ON_BOOT=1 -e RUN_AUTOMATION=0 \
  -e EDGE_USER_DATA_DIR=/data/edge-profile \
  -v "$PROFILE_DIR:/data/edge-profile" \
  -p 127.0.0.1:$PORT:6080 \
  --shm-size=2g \
  "$IMAGE" >/dev/null

echo ">> open http://localhost:$PORT/vnc.html (or ssh -L $PORT:127.0.0.1:$PORT the server first),"
echo ">> sign into Microsoft account + bing.com + rewards.bing.com inside the browser,"
echo ">> then stop: docker rm -f rewards-web-login"
echo ">> verify:  ./run_task.sh login_check $PROFILE   (expect rc=0, state=signed_in)"
