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

## Cron grid (mobile, jedyna prawda dla harmonogramu — zainstalowane 2026-09-14)

13 profili signed-in, równy krok **110 min** od 01:10, backup starego crontabu:
`/tmp/crontab.bak.20260914-110915`. Run `daily` 16–26 min → bufor ≥80 min; ostatni
start 23:10, pauza nocna 120 min. Web-linie (`run_daily.sh` 01:30 + domena1 02:00)
bez zmian — inny subsystem (Edge), bez kolizji locka 5555.

`01:10 prod_1 · 03:00 prod_2 · 04:50 d1 · 06:40 d2 · 08:30 d3 · 10:20 d4 ·
12:10 d5 · 14:00 d6 · 15:50 d7 · 17:40 d8 · 19:30 d9 · 21:20 d10 · 23:10 d11`

Wiersze poniżej oznaczają tylko STATUS provisioningu; sloty crouna czytaj z tej sekcji.

| name | kind | account | mobile snapshot | status |
|------|------|---------|-----------------|--------|
| test | anonymous | — | `test.tar.gz` | rebuilt 2026-09-01 from factory baseline (`pm clear` + `cp -a`); `bing.sh clear` allowed |
| prod_2 | signed-in | 616piotrek@gmail.com | `prod_2.tar.gz` | READ-TO-EARN e2e VERIFIED 2026-09-01: 30/30 daily pts, 2 sessions (`docs/bing-mobile-flow.md` § Read-to-earn e2e) |
| prod_1 | signed-in | piotrwro01@gmail.com | `prod_1.tar.gz` | VERIFIED signed-in 2026-09-01 (factory login → snapshot → variant); RTE `30 points earned` |
| domena1-prod | signed-in | domena-1@agregat-streszczen.pl | `domena1-prod.tar.gz` | PROVISIONED 2026-09-09 (`docs/profile-login-procedure.md`): mobile VERIFIED on variant (`rewards` probe → `state=rte` rc 0); MISC-CARDS e2e VERIFIED 2026-09-09 (5 cards +25 pts, `bing-domena1-prod-misc-cards-20260909-141327.log`); web VERIFIED `login_check` → `state=signed_in`; cron: web + mobile both 02:00; TILE-DRIVEN DAILY VERIFIED 2026-09-09 evening (`bing.sh run daily`, rc 0, 75/75 all-terminal, check-in `ok`) |
| domena2-prod | signed-in | domena-2@agregat-streszczen.pl | `domena2-prod.tar.gz` | PROVISIONED + MISC-CARDS e2e VERIFIED 2026-09-09 clean-account (9 cards +39 pts, `Daily points 0/75→15/75`, rc 0; `docs/bing-mobile-flow.md` § Misc cards e2e); TILE-DRIVEN DAILY VERIFIED 2026-09-09 evening: 65/75→75/75 (pool card +10), check-in inert on fresh account (UNCONFIRMED best-effort); web NOT provisioned yet (needs `./web_login.sh domena2-prod`) |
| domena4-prod | signed-in | domena-4@agregat-streszczen.pl | `domena4-prod-signedin.tar.gz` (4295 entries, 211 MB, 2026-09-09 20:18) | PROVISIONED 2026-09-09 variant-direct (docs/profile-provisioning-mobile.md; seed from `test` volume per d3 precedent — doc §1 factory-source updated): login verified TEXTUALLY (email + 'Total points', no 'Sign in'), gate `bing.sh run rewards --iters 0` rc 0 state=rte (fresh day-0: RTE 0/30 active). TILE-DRIVEN DAILY clean-slate e2e VERIFIED same day: `bing.sh run daily` rc 0, `0/75→75/75` in ~23 min (10/10 pool cards credited incl. auto-answered quiz 'Wizarding Creator?' +10, RTE `done` 4 sessions/20 reads — feed opened first try every session, zero-bounds guard never tripped; 3 SERP search; check-in node absent day-0 (like d2) → best-effort skip) |
| domena3-prod | signed-in | domena-3@agregat-streszczen.pl | `domena3-prod-signedin.tar.gz` (4520 entries, 2026-09-09 17:38) | PROVISIONED variant-direct 2026-09-09 (`docs/profile-provisioning-mobile.md`): FULL REWARDS-TAB CRAWL VERIFIED dzień 0 (`tools/rewards_full_crawl.py`) — search 15/15 TERMINAL (3 pkt/SERP, mobile credit CONFIRMED), pool cards 8/8 credited, **quiz card** (Wizarding Creator) +10 zautomatyzowane w `_quiz_flow` (karty QUIZ ≠ artykuły: wymagają odpowiedzi A-D; dowolne wystarczą), check-in `ok` (streak 1 day), puzzle = tracker 7-dniowy (nie klikalna akcja); RTE RESOLVED dzień 1 (run 19:16: feed otwarty za pierwszym razem, +30 → 75/75; przyczyna dzień-0: zero-bounds tap (0,0) + scroll-blind read_tiles, obie naprawione fcd8565/85f4b36): `docs/ideas/2026-09-09-d3-tile-map.md`; end-of-day **45/75** (30 brak = RTE); web NOT provisioned |
| domena5-prod | signed-in | domena-5@agregat-streszczen.pl (CONFIRMED dumpem) | `domena5-prod-signedin.tar.gz` (4423 entries, 213 MB, 2026-09-12 16:53) | PROVISIONED 2026-09-12 variant-direct (docs/profile-provisioning-mobile.md; seed z `test`): login VERIFIED TEXTUALLY (`Signed in as` + email, no wall), gate `bing.sh run rewards --iters 0` rc 0 state=rte (day-0 fresh) |
| domena6-prod | signed-in | domena-6@agregat-streszczen.pl (CONFIRMED dumpem) | `domena6-prod-signedin.tar.gz` (4414 entries, 2026-09-12 17:00) | PROVISIONED 2026-09-12 variant-direct (seed z `test`): login VERIFIED TEXTUALLY (email + `Total points`, no wall), gate `bing.sh run rewards --iters 0` rc 0 state=rte (day-0 fresh) |
| domena7-prod | signed-in | domena-7@agregat-streszczen.pl (CONFIRMED dumpem) | `domena7-prod-signedin.tar.gz` (4373 entries, 2026-09-12 17:07) | PROVISIONED 2026-09-12 variant-direct (seed z `test`): login VERIFIED TEXTUALLY (email + `Total points`, no wall), gate `bing.sh run rewards --iters 0` rc 0 state=rte (day-0 fresh) |
| domena8-prod | signed-in | domena-8@agregat-streszczen.pl (CONFIRMED dumpem) | `domena8-prod-signedin.tar.gz` (4346 entries, 192 MB, 2026-09-14 09:57) | PROVISIONED 2026-09-14 (re-created after 2026-09-12 deletion): owner logged in on seeded d10 volume; agent materialized `domena8-prod` volume + snapshot from it, then re-seeded d10 clean. Login VERIFIED TEXTUALLY (`domena-8@…` + 'Total points', no wall), gate rc 0 state=rte. **CRON 17:40** (grid 110-min od 2026-09-14) |
| domena9-prod | signed-in | domena-9@agregat-streszczen.pl (CONFIRMED dumpem) | `domena9-prod-signedin.tar.gz` (4305 entries, 2026-09-14 10:03) | PROVISIONED 2026-09-14 (re-created after 2026-09-12 deletion; seed z `test` busybox-tarem bez sudo): login VERIFIED TEXTUALLY, gate rc 0 state=rte. **CRON 19:30** |
| domena10-prod | signed-in | domena-10@agregat-streszczen.pl (CONFIRMED dumpem) | `domena10-prod-signedin.tar.gz` (4393 entries, 2026-09-14 10:13) | PROVISIONED 2026-09-14 (wolumin seedowany 12.09, omyłkowo skasowany i reseedy 14.09 — fałszywy switch `bing.sh use` naprawiony gardą flock -n + walidacją, patrz bing.sh). Login VERIFIED TEXTUALLY, gate rc 0 state=rte. **CRON 21:20** |
| domena11-prod | signed-in | domena-11@agregat-streszczen.pl (CONFIRMED dumpem) | `domena11-prod-signedin.tar.gz` (4296 entries, 2026-09-14 10:58) | PROVISIONED 2026-09-14 variant-direct (seed z 12.09): login VERIFIED TEXTUALLY, gate rc 0 state=rte. **CRON 23:10** |
| domena12-prod | abandoned | domena-12@agregat-streszczen.pl | — | **ODPUSZCZONY 2026-09-14** (decyzja ownera, po zakończonym d11): ekran loginu był przygotowany, login nie wykonany. Wolumin `~/redroid-variants/domena12-prod` (czysty seed z 12.09) został na serwerze — odtworzyć procedurą z docs/profile-provisioning-mobile.md gdyby wrócił do planu |

Web NIE dotyczy d5–d12: decyzja mobile-first (`docs/ideas/2026-09-09-web-to-mobile-migration.md`
— web profiles frozen 2026-09-09; nowe profile = mobile-only).

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
