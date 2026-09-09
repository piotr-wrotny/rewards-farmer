#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/run_task.sh" visual_search "${1:-${WEB_PROFILE:-default}}"
