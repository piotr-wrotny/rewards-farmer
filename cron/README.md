# Cron (KRON) wiring

KRON runs ON the server (`10.17.103.115`, existing scheduler process). Job lines call
the same entrypoint humans use — no separate path.

ACTUALLY INSTALLED (server crontab, 2026-09-01; backup `~/crontab.backup-20260901`):

```cron
30 1 * * * /home/piotr.wrotny/rewards-farmer-main/run_daily.sh >/dev/null 2>&1
0 2 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run read-to-earn --profile prod_1 --iters 60 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

Proposed, NOT installed: a `prod_2` read-to-earn line (stagger so flock
`/tmp/bing-5555.lock` never queues two runs; measured ≈ 6 min for 10 articles):

```cron
# 0 6 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run read-to-earn --profile prod_2 --iters 60 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

- Times: daily quotas reset at midnight UTC (points verified 2026-09-01); one run per
  account per day suffices — a second run exits `state=done` harmlessly.
- `--profile` is explicit (cron never relies on "active" variant).
- Exit codes: 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra — the scheduler
  sees failure via exit code; per-run detail in `logs/bing-<profile>-<action>-<TS>.log`.
- Self-heal: `bing.sh run` recreates a missing/dead container on the right volume.
- Web named profiles: `run_daily.sh <profile>` gets its own staggered line (the web
  flow kills all image containers before starting, so two web profiles must never
  overlap). Install only after `login_check <profile>` passes:

```cron
# 30 3 * * * /home/piotr.wrotny/rewards-farmer-main/run_daily.sh domena1-prod >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```
- To add a profile: create the variant (`profiles/README.md`), add a staggered line.
