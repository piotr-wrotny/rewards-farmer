#!/usr/bin/env bash
# Multi-instance isolation guards for bing.sh with fake docker/adb.
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
scenario="${FAKE_DOCKER_SCENARIO:-}"
cmd="${1:-}"; shift || true

if [ "$cmd" = "ps" ]; then
  if [ "${1:-}" = "-aq" ]; then
    [ "$scenario" = "conflict" ] && echo "cid-other"
    exit 0
  fi
  exit 0
fi

if [ "$cmd" = "inspect" ]; then
  fmt="$2"; target="$3"
  case "$target:$fmt" in
    redroid-a:"{{.State.Running}}")
      [ "$scenario" = "healthy" ] && echo "true" || echo "false"
      exit 0 ;;
    redroid-a:"{{range .Mounts}}{{if eq .Destination \"/data\"}}{{.Source}}{{end}}{{end}}")
      case "$scenario" in
        healthy|mismatch) echo "${BING_VAR}/profileA";;
      esac
      exit 0 ;;
    cid-other:"{{.Name}}") echo "/redroid-b"; exit 0 ;;
    cid-other:"{{range .Mounts}}{{if eq .Destination \"/data\"}}{{.Source}}{{end}}{{end}}")
      echo "${BING_VAR}/profileA"; exit 0 ;;
    cid-other:"{{.State.Status}}") echo "exited"; exit 0 ;;
    cid-other:"{{.HostConfig.RestartPolicy.Name}}") echo "unless-stopped"; exit 0 ;;
  esac
  exit 1
fi

if [ "$cmd" = "rm" ]; then
  exit 0
fi

if [ "$cmd" = "run" ]; then
  if [ "$scenario" = "mismatch" ]; then
    # Simulate container now mounted to wrong profile path.
    cat > "${TMP_DOCKER_MOUNT_FILE:?}" <<EOM
${BING_VAR}/profileB
EOM
  fi
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
  # Always ready for RUNNING check.
  if [ "${3:-}" = "shell" ]; then
    echo "User #0 state=RUNNING_UNLOCKED"
    exit 0
  fi
fi
exit 0
EOF

cat > "$FAKEBIN/falsepy" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

chmod +x "$FAKEBIN/docker" "$FAKEBIN/adb" "$FAKEBIN/falsepy"

export PATH="$FAKEBIN:$PATH"
export BING_VAR="$TMP/variants"
export BING_PY="$FAKEBIN/falsepy"
export BING_CONT="redroid-a"
export BING_PORT="5555"
export TMP_DOCKER_MOUNT_FILE="$TMP/current_mount"
mkdir -p "$BING_VAR/profileA" "$BING_VAR/profileB"

# 0) Switch blocked while active job holds slot lock.
LOCK_FILE="/tmp/bing-${BING_PORT}.lock"
flock -n "$LOCK_FILE" -c "sleep 2" &
lock_holder=$!
sleep 0.2
./bing.sh use profileA >/dev/null 2>&1; chk switch-while-active $? 3
wait "$lock_holder"

# 1) Conflict with another container (even exited) must fail closed.
export FAKE_DOCKER_SCENARIO="conflict"
./bing.sh use profileA >/dev/null 2>&1; chk conflict-mounted-profile $? 3

# 2) Mapping mismatch after recreate must fail closed.
export FAKE_DOCKER_SCENARIO="mismatch"
cat > "$TMP/current_mount" <<EOM
${BING_VAR}/profileA
EOM

# Override docker shim for current mount lookup after run.
cat > "$FAKEBIN/docker" <<'EOF'
#!/usr/bin/env bash
set -eu
scenario="${FAKE_DOCKER_SCENARIO:-}"
cmd="${1:-}"; shift || true
if [ "$cmd" = "ps" ] && [ "${1:-}" = "-aq" ]; then exit 0; fi
if [ "$cmd" = "inspect" ]; then
  fmt="$2"; target="$3"
  if [ "$target" = "redroid-a" ] && [ "$fmt" = "{{.State.Running}}" ]; then
    echo "false"; exit 0
  fi
  if [ "$target" = "redroid-a" ] && [ "$fmt" = "{{range .Mounts}}{{if eq .Destination \"/data\"}}{{.Source}}{{end}}{{end}}" ]; then
    cat "${TMP_DOCKER_MOUNT_FILE:?}"; exit 0
  fi
  exit 1
fi
if [ "$cmd" = "rm" ]; then exit 0; fi
if [ "$cmd" = "run" ]; then
  echo "${BING_VAR}/profileB" > "${TMP_DOCKER_MOUNT_FILE:?}"
  exit 0
fi
exit 0
EOF
chmod +x "$FAKEBIN/docker"

./bing.sh use profileA >/dev/null 2>&1; chk mapping-mismatch $? 3

exit $fail
