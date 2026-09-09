#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/run_task.sh" required_searches "${1:-${WEB_PROFILE:-default}}"
