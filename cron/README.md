# Cron (KRON) wiring

KRON runs ON the server (`10.17.103.115`, existing scheduler process). Job lines call
the same entrypoint humans use — no separate path. Paste into the scheduler's crontab
(user must do this; agent never installs crontab unasked):

```cron
# bing mobile flows — staggered so flock (/tmp/bing-5555.lock) never queues two runs
0 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run full --profile prod_2 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
30 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run full --profile test  >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

- Times are PLACEHOLDERS until the full prod flow (Read-to-earn port) is implemented.
- `--profile` is explicit (cron never relies on "active" variant).
- Exit codes: 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra — the scheduler
  sees failure via exit code; per-run detail in `logs/bing-<profile>-<action>-<TS>.log`.
- Self-heal: `bing.sh run` recreates a missing/dead container on the right volume.
- To add a profile: create the variant (`profiles/README.md`), add a staggered line.
