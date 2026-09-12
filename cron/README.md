# Cron (KRON) wiring

KRON runs ON the server (`10.17.103.115`, existing scheduler process). Job lines call
the same entrypoint humans use — no separate path.

ACTUALLY INSTALLED (server crontab, 2026-09-12 night — even-interval grid: 8 mobile
profiles (d8 removed), 24 h ÷ 8 = 3 h, start 01:15 (owner decision); every change backs
up first to `~/crontab.backup-<ts>`):

```cron
30 1 * * * /home/piotr.wrotny/rewards-farmer-main/run_daily.sh >/dev/null 2>&1
0 2 * * * /home/piotr.wrotny/rewards-farmer-main/run_daily.sh domena1-prod >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 1 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile prod_1 --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 4 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena1-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena2-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 10 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena3-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 13 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena4-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 16 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena5-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 19 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena6-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 22 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena7-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

Mobile lines replaced the old per-task `read-to-earn --iters 60` pair (2026-09-09 night):
`bing.sh run daily` IS the whole day (tile-driven state machine: check-in → cards →
RTE → searches, benefit-driven termination; `--iters` intentionally not passed).
Even-interval grid since 2026-09-12 (owner decision): day divided equally between all
mobile profiles — 24 h ÷ N, start pinned at 01:15 (N=8 → 3 h; d8/d9 removed from the
fleet same day). Previous shape was
fixed 2 h slots (2026-09-09); flock `/tmp/bing-5555.lock` already serialises overlaps
safely, fixed cadence keeps runtime predictable; measured worst case ≈ 25 min
clean-slate, ≈ 5-10 min mature. Scale note: recompute the grid whenever a profile is
added/removed (N+1 → 24 h ÷ (N+1)).
RESET-WINDOW CAVEAT: d3's daily quota was observed resetting ~02:38 local; the 01:15
prod_1 slot may farm the PREVIOUS day's tail on some accounts (tile-driven run is
harmless either way — it just stops at that day's terminal state). Watch first
cron.log, move later if needed.

Schedule shape: web stays `default` 01:30 + `domena1-prod` 02:00; mobile daily runs
on the 3 h grid 01:15→22:15 (prod_1, d1…d7). Mobile runs serialise on flock
`/tmp/bing-5555.lock` (queues, never corrupts).
RISK to keep an eye on: web `default` (01:30, hard timeout 30 min) and web
domena1-prod (02:00) share one image and `run_daily.sh` KILLS all image containers
before starting — a default run still alive at 02:00 gets terminated mid-flight.
Default runs finish ≈ 15 min in practice; if it ever overruns, move the domena1-prod
web line later.

Proposed, NOT installed: a `prod_2` read-to-earn line (stagger so flock
`/tmp/bing-5555.lock` never queues two runs; measured ≈ 6 min for 10 articles):

```cron
# 0 6 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run read-to-earn --profile prod_2 --iters 60 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

Pending: d8–d12 (branch `add-profiles-domena5-12`). d8/d9 REMOVED from server
2026-09-12 (owner: creation did not stick / deferred) — recreate from seed per
`docs/profile-provisioning-mobile.md`; d10–d12 volumes seeded, logins pending. When a
login gate passes, do NOT append a line: RECOMPUTE the whole grid (N+1 profiles →
24 h ÷ (N+1) from 01:15) and reinstall the full crontab (backup first). N=9 → 2 h 40 m
(01:15 03:55 06:35 09:15 11:55 14:35 17:15 19:55 22:35 — the shape installed earlier
2026-09-12 before d8 removal). RESET-WINDOW caveat above applies to any slot ≥ midnight.
(Mobile-only profiles: d5–d12 get NO web lines — web frozen per
`docs/ideas/2026-09-09-web-to-mobile-migration.md`.)

- Times: daily quotas reset at midnight UTC (points verified 2026-09-01); one run per
  account per day suffices — a second run exits `state=done` harmlessly.
- `--profile` is explicit (cron never relies on "active" variant).
- Exit codes: 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra — the scheduler
  sees failure via exit code; per-run detail in `logs/bing-<profile>-<action>-<TS>.log`.
- Self-heal: `bing.sh run` recreates a missing/dead container on the right volume.
- Web named profiles: `run_daily.sh <profile>` gets its own staggered line, installed
  only after `login_check <profile>` passes (see the installed block above).
- To add a profile: create the variant (`profiles/README.md`), add a staggered line.
