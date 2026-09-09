#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/run_task.sh" bonus_points "${1:-${WEB_PROFILE:-default}}"
