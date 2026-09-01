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

## Mobile flow (ReDroid on this server, no emulator)

Bing app (`com.microsoft.bing`) runs in the `redroid` Docker container (Android 14 x86_64,
port 127.0.0.1:5555). Data lives in per-profile volumes `~/redroid-variants/<profile>/`
(whole Android `/data`); snapshots in `~/profile-snapshots/<profile>.tar.gz`. The container
is stateless — switching a profile recreates it on that volume (see `bing.sh use` below).
It must run with DNS props or web content fails with `ERR_NAME_NOT_RESOLVED`
(`androidboot.redroid_net_ndns` is REQUIRED — bare `redroid_net_dns1/2` are ignored by netd),
publish ONLY 5555 (host adb server owns 5037), and boot is ready only when
`dumpsys activity users` shows `state=RUNNING_UNLOCKED` (`sys.boot_completed` lies —
see `docs/re-droid-gotchas.md` #1/#6).

One entrypoint, interactive and cron alike (runs ON the server, `~/rewards-farmer-main`):

```bash
./bing.sh use <profile>                     # switch active variant (recreate container)
./bing.sh current | status
./bing.sh run full|search|rewards|read-to-earn|screenshot [--profile P] [--iters N] [--debug|--no-debug]
./bing.sh clear [--profile test]            # pm clear — profile test ONLY
./bing.sh snapshot <name>                   # freeze factory volume -> profile-snapshots/<name>.tar.gz
```

Profiles are named credential variants (`profiles/README.md` is the registry): `test` =
logged-out (pm clear allowed), `prod_N` = signed-in (never cleared). Driver-level usage
(from the Windows dev machine, tunnel `ssh -N -L 15555:127.0.0.1:5555`, serial
`127.0.0.1:15555`): `python src/bing_mobile_flow.py --profile P --only ACTION`.

- Evidence: `artifacts/<profile>/screenshots/` (+ `ui/`); `--debug` adds a screenshot per executed action (default: on for `test`).
- Exit codes: 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra; `--clear` on a prod profile exits 3 (would log the account out).
- Permission dialogs are auto-allowed (test path; prod keeps them only as a safety net).
- Logged-out terminal state: Rewards page shows the 'Join Microsoft Rewards' sign-in wall; Read-to-earn requires a signed-in profile.
- Step-by-step selector map: `docs/bing-mobile-flow.md`. Operational hazards: `docs/re-droid-gotchas.md`.
