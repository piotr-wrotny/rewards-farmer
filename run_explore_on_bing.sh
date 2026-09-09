#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/run_task.sh" explore_on_bing "${1:-${WEB_PROFILE:-default}}"
