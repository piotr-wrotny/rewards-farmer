# Rewards Farmer — START HERE (operator handoff)

This file is the shortest reliable entrypoint for a fresh session.

## 1) Current production model

- **Mobile core (required):** `bing.sh run daily --profile <name>`
  - profile data: `~/redroid-variants/<name>`
  - single-slot lock: `/tmp/bing-5555.lock`
  - completion markers in logs:
    - `DONE state=daily_done`
    - `INCOMPLETE state=daily_incomplete ...`
- **Web layer (also required):** `run_daily.sh <name>` + evening `run_task.sh bonus_points <name>`
  - profile data: `~/rewards-farmer-main/edge-profiles/<name>`

## 2) Canonical files (read in this order)

1. `AGENTS.md` — full system map and operational rules
2. `profiles/README.md` — source of truth for cron grid + profile registry
3. `docs/profile-generation-manual-server.md` — server-side creation flow for new profiles
4. `docs/profile-login-procedure.md` — login + identity proof (`Web Data` grep)
5. `docs/re-droid-gotchas.md` — failure modes and guardrails

## 3) New retry layer (domain profiles)

Script: `scripts/mobile_daily_dispatcher.sh`

- picks **at most one** domain profile per invocation
- retries only when today's latest run is not `DONE state=daily_done`
- respects cooldown and per-day retry cap

Defaults:

- `BING_DISPATCHER_COOLDOWN_MINUTES=15`
- `BING_DISPATCHER_MAX_RETRIES_PER_DAY=2`
- `BING_DISPATCHER_DAILY_TARGET=120`

Recommended cron:

```cron
*/15 * * * * cd ~/rewards-farmer-main && BING_DISPATCHER_DAILY_TARGET=120 BING_DISPATCHER_COOLDOWN_MINUTES=15 BING_DISPATCHER_MAX_RETRIES_PER_DAY=2 scripts/mobile_daily_dispatcher.sh dispatch >> ~/rewards-farmer-main/logs/cron.log 2>&1
```

## 4) Mobile pacing knobs (recently tuned)

`src/bing_mobile_flow.py` reads env overrides:

- search: `BING_SEARCH_*`
- article dwell/open/back: `BING_ARTICLE_*`

Defaults are already reduced vs previous baseline to shorten `domena*` runs.

## 5) Fast health checks

```bash
cd ~/rewards-farmer-main
./bing.sh status
scripts/mobile_daily_dispatcher.sh status
tail -n 80 logs/cron.log
```

For server-local ADB readiness:

```bash
adb -s 127.0.0.1:5555 shell 'echo ok-from-server'
```

For new mobile-profile onboarding preflight:

```bash
scripts/mobile_profile_preflight.sh pre-login <profile>
```

For fresh `r_domena_*` mobile setup (reseed + Bing install + wall gate):

```bash
scripts/mobile_prepare_new_profile.sh r_domena_01
```

For local operator TUI (web+mobile onboarding and live views):

```bash
py -3 tools\profile_tui.py
# if terminal prints garbage on mouse move:
py -3 tools\profile_tui.py --no-mouse
```

Open central action menu: `x` (minimal footer, no horizontal key-scroll).
Keymap and workflow details: `docs/operator-tui.md`.
Deployment test command: `py -3 -m pytest tests\test_profile_tui.py -q`.

For safe server pause/resume around onboarding windows:

```bash
scripts/server_maintenance.sh status
scripts/server_maintenance.sh kill-switch          # soft/graceful
scripts/server_maintenance.sh kill-switch --hard   # escalation
scripts/server_maintenance.sh disable
scripts/resume_incomplete_mobile.sh --dry-run
scripts/resume_incomplete_mobile.sh --max 6
```

## 6) If local scrcpy says `offline`

On server first, ensure slot is healthy:

```bash
cd ~/rewards-farmer-main
./bing.sh use <profile>
./bing.sh status
adb -s 127.0.0.1:5555 shell 'echo ok-from-server'
```

Then on Windows:

```powershell
bin\platform-tools\adb.exe kill-server
bin\platform-tools\adb.exe start-server
ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
bin\platform-tools\adb.exe connect 127.0.0.1:15555
bin\platform-tools\adb.exe devices
bin\scrcpy\scrcpy.exe -s 127.0.0.1:15555
```

## 7) Deployment reminder

- local checkout is source of truth
- server has no git; deploy changed files by `scp/rsync`
- **never push to `origin`**; push to `fork` only
