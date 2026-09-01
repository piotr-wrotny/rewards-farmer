# Profile variants + .sh orchestration + cron — design

Date: 2026-09-01. Branch: `bing-server-flow`. Status: approved in chat shape, pending spec review.

## Goal

One repo-owned way to run Bing mobile flows **per named profile variant**
(`prod_1`, `prod_2`, `test`, …) on the server ReDroid, driven by `.sh` scripts that work
identically interactively and from cron (KRON). Profile switch, single actions, full
flows, factory (login new profile) — all scripted.

## Current state (verified this session)

- Server `piotr.wrotny@10.17.103.115`, `~/rewards-farmer-main` (this repo).
- Containers on server: `redroid` (prod, 127.0.0.1:5555), `redroid-factory` (profile
  factory, 127.0.0.1:5556). Both `redroid/redroid:14.0.0-latest` +
  `androidboot.redroid_net_ndns=2 androidboot.redroid_net_dns1=172.20.0.41 androidboot.redroid_net_dns2=172.20.0.42`
  (ndns REQUIRED; see Proof-Of-Concept-Artifacts/docs/runtime-info.md).
- Bing `com.microsoft.bing` 34.0.440821002 (global, arm64-v8a APK from APKPure; local copy
  `assets/…APKPure.apk`, gitignored).
- `prod_2` snapshot exists: `~/profile-snapshots/prod_2.tar.gz` (full `/data`, ~183 MB,
  server-only, plaintext NEVER committed). It was restored and verified signed-in
  (616piotrek@gmail.com) — flow map for signed-in state not yet produced.
- Logged-out (anonymous) volume preserved: `~/redroid-data-dev-loggedout-20260901`.
- Driver: `src/bing_mobile_flow.py` (uiautomator2). Runs today from the Windows dev
  machine through SSH tunnels (15555→5555, 15556→5556). Server has Python 3.14, no u2 yet.
- Flow step map + selectors: `docs/bing-mobile-flow.md`. Runbook: `AGENTS.md`.

## Design

### 1. Variants = unpacked /data volumes on the server (source of truth)

```
~/profile-snapshots/<name>.tar.gz    # immutable snapshot per profile (from factory or clear)
~/redroid-variants/<name>/           # unpacked /data for <name>
```

- Active variant is NOT a symlink (Docker resolves bind sources at container CREATE;
  swapping a link under a live container is undefined). Switching = recreate container:
  `docker rm -f redroid; docker run … --volume ~/redroid-variants/<name>:/data …`.
  Container is stateless; boot ~10 s. Same pattern as existing `run_task.sh`.
- `test` is just a variant: anonymous Bing. `pm clear` allowed ONLY for `test`.
- Snapshot procedure (proven on prod_2): factory container (5556) → login via scrcpy →
  `am force-stop` + `sync` → `docker stop` → tar volume → `docker start` factory.
- Restore procedure (proven): fresh dir, untar, start `redroid` with that volume.
- Rollback = start container on any other variant volume. Nothing destructive, ever.

### 2. Registry (in repo, plaintext-safe)

`profiles/README.md` (git-allowed; `profiles/*` otherwise gitignored, only `.enc` +
README committable — enforced):

| name | kind | account | snapshot | notes |
|------|------|---------|----------|-------|
| test | anonymous | — | (created via `init test`) | pm clear allowed |
| prod_2 | signed-in | 616piotrek@gmail.com | prod_2.tar.gz | verified 2026-09-01 |
| prod_1 | signed-in | TBD | — | to be created via factory |

No secrets in repo. Optional encrypted backups `profiles/<name>.tar.gz.enc` (gpg, key/
passphrase from user) — decision pending, non-blocking.

### 3. `bing.sh` (server entrypoint; cron-safe)

Location: repo root `bing.sh`, deployed copy runs from `~/rewards-farmer-main`. All
subcommands: resolve variant → ensure container on that volume → invoke driver → logs.

```
./bing.sh use <name>                     # switch active variant (recreate container)
./bing.sh current                        # active variant + container/adb/account state
./bing.sh status                         # containers, variants, last logs per profile
./bing.sh run full   [--profile P]       # whole flow for P (default: active)
./bing.sh run <action> [--profile P]     # one action: search | rewards | screenshot
                                         # | read-to-earn (prod-flow, when implemented)
./bing.sh clear                          # pm clear — hard-refuses unless variant == test
./bing.sh snapshot <name>                # tar current factory volume → snapshots/<name>.tar.gz
```

- `--profile` explicit for cron (never relies on "active" under cron); interactive default
  is convenience only.
- Exit codes: 0 ok (incl. clean "wall"/"done" terminal states), 2 flow failure, 3 infra
  (container/adb/driver). Cron-friendly.
- Concurrency: `flock /tmp/bing-<port>.lock` per container — two crons never share one Bing.
- Actions map 1:1 to `bing_mobile_flow.py` methods; add `--only <action>` to the driver
  (step-level run), keeping `full` as today's `run()`.

### 4. Driver on the server (cron lives there)

- Verify `pip install uiautomator2` on server Python 3.14 FIRST (plan Task 1). Fallbacks,
  in order: (a) `python3.12` venv via deadsnakes, (b) tiny driver container (`python:3.12-slim`
  with repo src mounted, `pip install uiautomator2`, adb from server host).
- On server adb connects `127.0.0.1:5555` directly — no tunnel. Windows dev keeps tunnels
  + scrcpy for interactive work only.
- `u2.connect` target passed via `--serial` (existing flag).

### 5. Evidence & logs (profile-keyed, replaces dev/prod buckets)

- `~/rewards-farmer-main/artifacts/<profile>/{screenshots,ui}/` — kubełek = nazwa profilu
  (`test` = dzisiejszy dev). Driver `--mode` replaced by `--profile <name>` (mode dirs
  `artifacts/<name>/`).
- `~/rewards-farmer-main/logs/bing-<profile>-<action>-<TS>.log`, `[ACTION] …` convention.
- Screenshot every action remains `--debug` behavior (default for `test`, flag-controlled
  for prod to keep volume sane).

### 6. Factory (profile creation) — dev-machine workflow

scrcpy MUST run on the user's machine (interactive login), so factory commands split:

- `factory.ps1 login <name>` (Windows): ensures factory container on server, tunnel 15556,
  opens scrcpy window titled for `<name>`.
- `factory.ps1 save <name>` (Windows→ssh): snapshot per §1 procedure; then appends the
  registry row and (if user chose encryption) gpg-encrypts a copy into `profiles/`.
- Server-side `bing.sh snapshot` does the tar part; factory.ps1 orchestrates.

### 7. Cron / KRON interface

- Cron runs on this server: `cd ~/rewards-farmer-main && ./bing.sh run full --profile prod_2 >> logs/cron.log 2>&1`.
- If KRON turns out to be external: it only needs ssh + same argv contract; nothing changes
  in this design (open question #1 below).
- Schedule example (placeholder until prod flow mapped): search 07:00, rewards 07:30,
  read-to-earn 08:00 per profile, staggered so one driver never contends.

### 8. Error handling

- Container missing/dead → `use`/`run` recreate it; one retry; then infra exit 3 + log.
- adb offline → `adb connect` retry ×3; device wedged → `docker restart redroid`, retry once.
- Flow step failure → screenshot named `*-failed-*` + non-zero exit; cron sees failure via
  exit code and log tail.
- `clear` on non-test variant → exit 3, message; guard tested.

### 9. Testing

- Pure-shell unit checks (no device): variant resolution, `clear` guard, `--profile` default
  resolution, log naming. `bats` or plain `assert` script `tests/test_bing.sh`.
- Driver `--only` actions: run against `test` variant end-to-end (it is safe to clear).
- Contract smoke: `./bing.sh run screenshot --profile test` from a cold state (container
  removed) must self-heal and produce exactly one screenshot artifact + exit 0.
- Variant switch round-trip: `use test` → `use prod_2` → `current` reports correct account
  (assert on UI: no email under test, email under prod_2).

## Open questions (answers do not change the architecture)

1. **KRON**: cron on this server, or an external scheduler invoking via ssh? Design serves
   both; decides only where the crontab line lives.
2. **Encrypted backups** `profiles/*.enc` into git: wanted or server-only snapshots enough?
3. **prod_1**: schedule its factory session (needs ~5 min interactive scrcpy).

## Non-goals (for now)

- Multiple simultaneous containers per profile (serial farming) — one active at a time.
- Mapping the signed-in prod flow (Rewards dashboard → Read to earn) — this infra first,
  flow mapping is the next phase on top of `--only` actions.
- Moving the web/Edge (rewards.bing.com) flows into `bing.sh` — separate concern.
