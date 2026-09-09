#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/run_task.sh" daily_set "${1:-${WEB_PROFILE:-default}}"
