# Cron (KRON) wiring

KRON runs ON the server (`10.17.103.115`, existing scheduler process). Job lines call
the same entrypoint humans use — no separate path.

ACTUALLY INSTALLED (server crontab, 2026-09-09 evening; every change backs up first
to `~/crontab.backup-<ts>`):

```cron
30 1 * * * /home/piotr.wrotny/rewards-farmer-main/run_daily.sh >/dev/null 2>&1
0 2 * * * /home/piotr.wrotny/rewards-farmer-main/run_daily.sh domena1-prod >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 1 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile prod_1 --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 3 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena1-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 5 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena2-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena3-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
15 9 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena4-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

Mobile lines replaced the old per-task `read-to-earn --iters 60` pair (2026-09-09 night):
`bing.sh run daily` IS the whole day (tile-driven state machine: check-in → cards →
RTE → searches, benefit-driven termination; `--iters` intentionally not passed).
Fixed slots every 2 h starting 01:15 (owner decision over chaining-with-5-min-gap:
flock `/tmp/bing-5555.lock` already serialises overlaps safely, fixed slots keep
runtime predictable; measured worst case ≈ 25 min clean-slate, ≈ 5-10 min mature).
Scale note: at 12 domains + prod_1, a 2 h cadence fills the day exactly — raise
buffer or split web/mobile windows before profile #10. RESET-WINDOW CAVEAT: d3's
daily quota was observed resetting ~02:38 local; the 01:15 prod_1 slot may farm the
PREVIOUS day's tail on some accounts (tile-driven run is harmless either way —
it just stops at that day's terminal state). Watch first cron.log, move later if needed.

Schedule shape: web stays `default` 01:30 + `domena1-prod` 02:00; mobile daily runs
at 01:15/03:15/05:15/07:15/09:15. Mobile runs serialise on flock
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

Proposed for d5–d12 (branch `add-profiles-domena5-12`), NOT installed until each
profile passes the login gate. The 2 h grid from 01:15 leaves EXACTLY 7 free slots
(11:15…23:15 odd hours) for 8 profiles — d12 takes 00:15 (grid-consistent; RESET-WINDOW
caveat above applies: quota is midnight-UTC, 00:15 CEST = 22:15 UTC previous day, so the
run farms that day's fresh quota; tile-driven termination makes any overlap harmless):

```cron
# 15 11 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena5-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 13 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena6-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 15 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena7-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 17 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena8-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 19 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena9-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 21 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena10-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 23 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena11-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
# 15 0 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run daily --profile domena12-prod --no-debug >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```
(Mobile-only block: d5–d12 get NO web lines — web frozen per
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
