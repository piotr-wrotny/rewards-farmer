#!/usr/bin/env bash
# Prepare a fresh mobile profile for r_domena_* on the 5555 slot:
# - backup current volume (if present),
# - recreate empty /data volume,
# - boot container on the profile,
# - install Bing APK copied from test volume,
# - verify pre-login gate (state=wall).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BING="$ROOT/bing.sh"
LOCK="/tmp/bing-5555.lock"
PROFILE="${1:-}"
VAR_BASE="$HOME/redroid-variants"
PROFILE_DIR="$VAR_BASE/$PROFILE"
TMP_APK="$ROOT/tmp-bing-base.apk"

cleanup() {
  rm -f "$TMP_APK" 2>/dev/null || true
}
trap cleanup EXIT

die() {
  echo "$*" >&2
  exit "${2:-2}"
}

usage() {
  cat >&2 <<EOF
Usage:
  scripts/mobile_prepare_new_profile.sh <profile>

Notes:
  - Intended for new r_domena_* profiles only.
  - Requires docker access (uses busybox root container for volume operations).
EOF
  exit 2
}

[ -n "$PROFILE" ] || usage
case "$PROFILE" in
  r_domena_*) ;;
  *) die "refusing profile '$PROFILE' (allowed prefix: r_domena_*)" 2 ;;
esac

[ -x "$BING" ] || die "missing executable bing.sh at $BING" 3
command -v docker >/dev/null 2>&1 || die "docker is required" 3
command -v adb >/dev/null 2>&1 || die "adb is required" 3

flock -n "$LOCK" true || die "slot busy: $LOCK (stop active run first)" 3

echo "[1/5] stopping slot container"
docker rm -f redroid >/dev/null 2>&1 || true

echo "[2/5] backing up and recreating $PROFILE_DIR"
docker run --rm -v "$HOME:/host" busybox sh -c "
  set -e
  ts=\$(date +%Y%m%d-%H%M%S)
  if [ -d /host/redroid-variants/$PROFILE ]; then
    tar -C /host/redroid-variants/$PROFILE -czf /host/profile-snapshots/${PROFILE}-pre-fresh-\$ts.tar.gz . || true
  fi
  rm -rf /host/redroid-variants/$PROFILE
  mkdir -p /host/redroid-variants/$PROFILE
  echo backup=/host/profile-snapshots/${PROFILE}-pre-fresh-\$ts.tar.gz
"

echo "[3/5] booting fresh profile on slot"
BING_ADB_TIMEOUT_SECONDS=5 "$BING" use "$PROFILE"
timeout 10 docker exec redroid sh -c "dumpsys activity users 2>/dev/null | sed -n '1,8p'"

echo "[4/5] copying Bing APK from test volume and installing"
docker run --rm -v "$HOME:/host" busybox sh -c "
  set -e
  apk=\$(find /host/redroid-variants/test/app -type f -name base.apk | head -n 1)
  [ -n \"\$apk\" ]
  cp \"\$apk\" /host/rewards-farmer-main/tmp-bing-base.apk
  chmod 644 /host/rewards-farmer-main/tmp-bing-base.apk
  echo copied_from=\$apk
"
adb -s 127.0.0.1:5555 install -r "$TMP_APK"
adb -s 127.0.0.1:5555 shell pm path com.microsoft.bing

echo "[5/5] pre-login gate (expected: state=wall)"
"$BING" run rewards --profile "$PROFILE" --iters 0 --no-debug --post-run-cleanup keep-running
