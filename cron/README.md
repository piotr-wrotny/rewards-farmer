# Cron (KRON) wiring

KRON runs ON the server (`10.17.103.115`, existing scheduler process). Job lines call
the same entrypoint humans use — no separate path. Paste into the scheduler's crontab
(user must do this; agent never installs crontab unasked):

```cron
# bing mobile flows — staggered so flock (/tmp/bing-5555.lock) never queues two runs.
# Measured: read-to-earn 10 articles ≈ 6 min (prod_2, 2026-09-01).
0 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run read-to-earn --profile prod_2 --iters 60 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
30 8 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run read-to-earn --profile prod_1 --iters 60 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

- Times: daily quotas reset at midnight UTC (points verified 2026-09-01); one run per
  account per day suffices — a second run exits `state=done` harmlessly.
- `--profile` is explicit (cron never relies on "active" variant).
- Exit codes: 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra — the scheduler
  sees failure via exit code; per-run detail in `logs/bing-<profile>-<action>-<TS>.log`.
- Self-heal: `bing.sh run` recreates a missing/dead container on the right volume.
- To add a profile: create the variant (`profiles/README.md`), add a staggered line.
