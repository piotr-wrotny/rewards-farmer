# Rewards farmer runbook

This project runs on server `piotr.wrotny@10.17.103.115` from `~/rewards-farmer-main`.

## Main flow

- `./run_daily.sh` — full run (all tasks as implemented by `complete_all_tasks`).

## Task-specific flows

All scripts below use the same Edge profile volume (`~/rewards-farmer-main/edge-profile`), clear singleton locks, and write logs to `~/rewards-farmer-main/logs`.

- `./run_task.sh <task>` — generic entrypoint for one task.
- `./run_daily_set.sh` — runs `daily_set`.
- `./run_explore_on_bing.sh` — runs `explore_on_bing`.
- `./run_visual_search.sh` — runs `visual_search`.
- `./run_misc_cards.sh` — runs `misc_cards`.
- `./run_required_searches.sh` — runs `required_searches`.
- `./run_bonus_points.sh` — runs `bonus_points`.

Supported `<task>` values:

- `daily_set`
- `explore_on_bing`
- `visual_search`
- `misc_cards`
- `required_searches`
- `bonus_points`
- `all`

Optional env overrides for `run_task.sh`:

- `VISUAL_SEARCH_RUNS=<N>` for `visual_search`
- `REQUIRED_SEARCH_RUNS=<N>` for `required_searches`

## Search behavior (current)

- `required_searches` runs a fixed 30 searches per run.
- Search phrases are sampled randomly from a generated pool of 600 phrases.
- After each search, automation scrolls down by a random distance and waits 5–6 seconds.
- Every executed action is logged in server logs as `[ACTION] <context> [<detail>] trigger=<source/reason>`.

## Visual search asset

Automation resolves image in this order:

1. `/data/edge-profile/visual-search-asset.jpg`
2. `/data/edge-profile/visual_search.jpg`
3. `/app/visual-search-asset.jpg`
4. `/app/visual_search.jpg`

## Logs

- Daily flow: `logs/web-run-YYYYMMDD-HHMMSS.log`
- Task flow: `logs/web-run-<task>-YYYYMMDD-HHMMSS.log`
