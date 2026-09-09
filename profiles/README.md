# Profile registry

Named credential variants for BOTH flows. One profile name = one Microsoft account,
held in two independent stores: a mobile Android `/data` volume and a web Edge
user-data-dir. Provision them separately (factory/noVNC), register them in one row.

**Mobile** (`com.microsoft.bing`): unpacked Android `/data` volume at
`~/redroid-variants/<name>` on the server + a snapshot
`~/profile-snapshots/<name>.tar.gz` (whole volume; uid-perfect; **server-only — never
commit profile data**, see `.gitignore`). Switch: `./bing.sh use <name>`. Create:
`scripts/factory.ps1 login <name>` (scrcpy, user logs in — agent never sees
credentials) then `factory.ps1 save <name>`. New variant from snapshot:

```bash
ssh piotr.wrotny@10.17.103.115 'p=<name>; docker run --rm -v /home/piotr.wrotny:/host busybox sh -c "mkdir -p /host/redroid-variants/$p && tar -C /host/redroid-variants/$p -xzf /host/profile-snapshots/$p.tar.gz" && cd ~/rewards-farmer-main && ./bing.sh use $p'
```

| name | kind | account | mobile snapshot | status |
|------|------|---------|-----------------|--------|
| test | anonymous | — | `test.tar.gz` | rebuilt 2026-09-01 from factory baseline (`pm clear` + `cp -a`); `bing.sh clear` allowed |
| prod_2 | signed-in | 616piotrek@gmail.com | `prod_2.tar.gz` | READ-TO-EARN e2e VERIFIED 2026-09-01: 30/30 daily pts, 2 sessions (`docs/bing-mobile-flow.md` § Read-to-earn e2e) |
| prod_1 | signed-in | piotrwro01@gmail.com | `prod_1.tar.gz` | VERIFIED signed-in 2026-09-01 (factory login → snapshot → variant); RTE `30 points earned` |
| domena1-prod | signed-in | domena-1@agregat-streszczen.pl | `domena1-prod.tar.gz` | PROVISIONED 2026-09-09 (`docs/profile-login-procedure.md`): mobile VERIFIED on variant (`rewards` probe → `state=rte` rc 0); MISC-CARDS e2e VERIFIED 2026-09-09 (5 cards +25 pts, `bing-domena1-prod-misc-cards-20260909-141327.log`); web VERIFIED `login_check` → `state=signed_in`; cron: web + mobile both 02:00 |
| domena2-prod | signed-in | domena-2@agregat-streszczen.pl | `domena2-prod.tar.gz` | PROVISIONED + MISC-CARDS e2e VERIFIED 2026-09-09 clean-account (9 cards +39 pts, `Daily points 0/75→15/75`, rc 0; `docs/bing-mobile-flow.md` § Misc cards e2e); check-in inert on fresh account; web NOT provisioned yet (needs `./web_login.sh domena2-prod`) |

**Web** (Edge): a user-data-dir volume — `default` is the historical
`~/rewards-farmer-main/edge-profile`; named profiles live at
`~/rewards-farmer-main/edge-profiles/<name>` (mounted as `/data/edge-profile`).
Provision: `./web_login.sh <name>` (login-mode container + noVNC, user signs in),
verify: `./run_task.sh login_check <name>` (rc 0 = signed in, 2 = wall). Run:
`./run_daily.sh <name>` / `./run_task.sh <task> <name>` (wrappers: `$1` or
`WEB_PROFILE`). Each volume needs `visual-search-asset.jpg` (web_login.sh copies it).

Snapshot hygiene: verify with `tar -tzf <f> | grep system/packages.xml >/dev/null`
(plain grep, NEVER `grep -q` — closes the pipe, tar SIGPIPE trips pipefail; bing.sh
snapshot has the correct form) and size > 100 MB (`docs/re-droid-gotchas.md` #2).
NEVER `chown` a volume (#1). Extract variants via docker too — the directory is
root-owned, bare `mkdir` as your user fails.
