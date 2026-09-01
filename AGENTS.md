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
port 127.0.0.1:5555, data volume `~/redroid-data`). It must be started with DNS props or
web content fails with `ERR_NAME_NOT_RESOLVED`:

```bash
docker run --detach --name redroid --privileged \
  --publish 127.0.0.1:5555:5555 \
  --volume ~/redroid-data:/data \
  redroid/redroid:14.0.0-latest \
  androidboot.redroid_gpu_mode=guest \
  androidboot.redroid_net_ndns=2 \
  androidboot.redroid_net_dns1=172.20.0.41 \
  androidboot.redroid_net_dns2=172.20.0.42
```

`androidboot.redroid_net_ndns` is REQUIRED — bare `redroid_net_dns1/2` props are ignored by netd.

Dev runs from the Windows machine (tunnel first):

```bash
ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
python src/bing_mobile_flow.py --debug [--iters N] [--clear]
```

- Every step produces a screenshot in `artifacts/screenshots/` (+ UI dumps in `artifacts/ui/`); `--debug` adds one per executed action.
- `--clear` wipes Bing app data (`pm clear`) so FRE/onboarding reappear — dev/testing only; Prod keeps the app signed in.
- Permission dialogs are auto-allowed in dev mode.
- Logged-out terminal state: Rewards page shows the 'Join Microsoft Rewards' sign-in wall; Read-to-earn requires an account (Prod path).
