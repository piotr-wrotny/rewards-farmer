#!/usr/bin/env bash
# Guard tests for bing.sh — no device, no real volumes.
# Run on the server (or anywhere docker CLI exists): bash tests/test_bing.sh
set -u
cd "$(dirname "$0")/.."
fail=0
chk() { if [ "$2" != "$3" ]; then echo "FAIL $1: got '$2' want '$3'"; fail=1; else echo "ok $1"; fi }

export BING_VAR="$(mktemp -d)"   # empty variants registry
export ADB="false"               # any adb call fails => infra paths, never a real device
export BING_PY="false"
export BING_CONT=no_such_container   # isolate from any real redroid container

./bing.sh >/dev/null 2>&1; chk usage $? 2
./bing.sh bogus >/dev/null 2>&1; chk bogus $? 2
./bing.sh run screenshot --profile no_such_profile >/dev/null 2>&1; chk run-unknown-variant $? 3
./bing.sh clear --profile prod_x >/dev/null 2>&1; chk clear-refuses-prod $? 3
./bing.sh clear --profile no_such_profile >/dev/null 2>&1; chk clear-unknown $? 3
# current with no container: "none", exit 0
out=$(./bing.sh current 2>/dev/null); chk current-none "$out" "active=none"

rmdir "$BING_VAR" 2>/dev/null || true
exit $fail
