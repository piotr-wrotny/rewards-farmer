# Rewards Farmer — runbook and system map

**Status: DELIVERED (2026-09-14). Maintenance only.** The farm runs 13 signed-in
Microsoft Rewards profiles unattended on the server. No new features are planned;
changes are limited to breakage fixes and (someday, not now) the points-observer
idea in `docs/ideas/2026-09-09-points-reader-api.md` — a collector that publishes
per-profile `daily_points` via an API at the end of each flow. Do not build it
unless the owner asks.

Ground rules for any future change:

- **Never push to `origin`** (`User0332/rewards-farmer`, public — this repo contains
  account identities and profile data). Push only to `fork`
  (`piotr-wrotny:piotr-wrotny/rewards-farmer.git`). Branch tracking is set to
  `fork/main`; keep it that way.
- The local Windows checkout is the source of truth. The server
  (`piotr.wrotny@10.17.103.115:~/rewards-farmer-main`) is a deployment target with
  **no git** — files arrive by `rsync`/`scp` of the changed paths.
- Tests (manual, no CI exists): `py -3 -m pytest tests/ -q` on Windows (the hermes
  venv python lacks pytest), `bash tests/test_bing.sh` for the `bing.sh` guards.

## How the system works today

Two automation stacks share one server; both are required — mobile earns
RTE/streak/quiz, web earns visual search + bonus (full set = both):

```
cron ──13×──> bing.sh run daily --profile P ──flock──> ReDroid container (adb :5555)
                 │  (stateless; per-profile /data volume)
                 └──> python src/bing_mobile_flow.py --only daily   [LIVE CORE]

cron ──3×───> run_daily.sh [profile] ──> docker run rewards-farmer image
                 │  (Edge + Selenium, bind-mount src/rewards_tasks.py:ro)
                 └──> src/main.py -> rewards_tasks.complete_all_tasks()   [LIVE WEB]
```

Mobile flow per run: `bing.sh` takes the device lock, ensures the container is on
the profile's volume (`~/redroid-variants/<profile>` = whole Android `/data`),
waits for user-0 `RUNNING`, then the uiautomator2 driver runs the tile-driven
machine: read Rewards tiles -> cheapest-first action rounds (streak check-in sweep
> misc cards incl. quiz > Read-to-earn article sessions > required searches), max 6
rounds, stops on zero-point saturation; tab cleanup is the terminal invariant
everywhere. Every action logs `[ACTION] … trigger=…`; evidence lands in
`artifacts/<profile>/{screenshots,ui}/`. A full soak of a fresh profile runs
~20–25 min to 75/75 daily points; a saturated profile self-heals in ~6 min.

`src/bing_mobile_flow.py` method map: boot (`relaunch/dismiss_fre/dismiss_popups/
ensure_home`), classification (`rewards_state`: rte/done/unrendered/wall), actions
(`check_in` streak sweep, `misc_cards`+`_quiz_flow`, `read_to_earn_flow` 5/session
×≤20, `required_searches` from a 600-phrase pool built from `nouns.txt` ×
`SEARCH_QUERY_TEMPLATES`), orchestration (`daily_flow`, `read_tiles`, `all_terminal`).
CLI: `--only full|search|rewards|read-to-earn|misc-cards|required-searches|daily|
screenshot`; exit 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra.
Intentionally-dead methods kept as spec parity records: `total_points()` (points
reader for the someday observer idea), `close_article_tab_return_to_feed()`.

Schedule: 13 mobile lines on a 110-min even grid (01:10 prod_1 … 23:10 domena11) +
the two web lines. Canonical grid: **`profiles/README.md` § Cron grid** (the
registry is the single source of truth; `cron/README.md` is history).

## LIVE — mobile core (the farm)

- `bing.sh` — sole entrypoint, cron + interactive alike.
  - `use <profile>` — switch active variant (recreates container on that volume).
    Fail-fast (`flock -n`) on the device lock when a `run` holds it → rc 3 "device
    busy" (added 2026-09-14 after a mid-run switch corrupted a soak; it also
    validates the variant dir exists and verifies the switch landed).
  - `run daily|full|search|rewards|read-to-earn|misc-cards|screenshot [--profile P]
    [--iters N] [--debug|--no-debug]` — BLOCKING flock: cron lines queue behind a
    manual run instead of colliding. `--iters` is ignored for `daily`.
  - `current | status`; `clear` (pm clear — profile `test` ONLY, rc 3 otherwise);
    `snapshot <name>` — freezes the **factory** volume only (separate container
    `redroid-factory`, lock 5556). **Never** for signed-in profiles: snapshot a
    prod volume with a manual busybox tar while the container is stopped
    (`docs/profile-provisioning-mobile.md`).
  - Env overrides: `BING_PY`, `BING_VAR`, `BING_CONT`, `BING_PORT`, `ADB`.
- `src/bing_mobile_flow.py` — the driver (imports stdlib + uiautomator2 only).
- `nouns.txt` — phrase-pool seed (mobile + web both read it).
- `profiles/README.md` — registry: profile ↔ volume ↔ status ↔ cron grid.
  `docs/profile-accounts.md` — identities. Provisioning (current era, variant-direct
  seeding + user login via scrcpy): `docs/profile-provisioning-mobile.md`.
- Flow selector map: `docs/bing-mobile-flow.md`; ReDroid hazards:
  `docs/re-droid-gotchas.md` (ndns DNS props, publish 5555 only, RUNNING_UNLOCKED).
- Logs: `logs/bing-<profile>-daily-<ts>.log`; completion markers
  `daily: end daily_points=A/B->C/D` and `DONE state=daily_done`.
- Tests: `tests/test_bing.sh` covers `bing.sh` guards (fakes adb/python/container).

## LIVE — web layer (required for full coverage, rolling out to all prods)
Two stacks share one server. Owner decision 2026-09-14: **every prod account must
run the FULL set of earnable actions**, and neither stack alone covers it —
visual search (file-input path) and bonus-claim exist ONLY in web
(`src/bing_mobile_flow.py` has no visual/bonus code), while Read-to-earn/streak/quiz
exist only in mobile. So the web line is no longer a frozen fallback: it is a
permanent layer. Rollout 2026-09-14 COMPLETE (provisioning): `prod_1` +
domena1–11 all have web volumes (`edge-profiles/<p>`); d2–d11 provisioned +
identity-proven, launches ordered by owner AFTER provisioning (phase 2).

- Installed web lines: `30 1 * * * run_daily.sh` (`default`), `0 2 * * *
  run_daily.sh domena1-prod`, `30 3 * * * run_daily.sh prod_1` (added 2026-09-14;
  `login_check` rc 0; verification `run_daily` soak same day: daily set + visual
  search + bonus + required searches OK, explore/misc SKIP — same UI-variant skips
  as every other web profile).
- Phase 2 (verification, running): soak each of d2–d11 sequentially (one full
  `run_daily.sh <p>`, NEVER parallel — the ancestor sweep kills concurrent
  containers). Verdicts recorded in `profiles/README.md`. NO cron installed by the
  agent: activation strategy (which profiles, which slots, ≥1 h gaps against
  existing 01:30/02:00/03:30) is decided JOINTLY with the owner after results
  (phase 3, together with mobile-flow ordering).
- Provision recipe (proven 10× same day): fresh `./web_login.sh <p>` container (name
  `rewards-web-login-<p>`), user logs in via noVNC, agent greps `Web Data` for the
  registry email (login_check alone is account-blind — the d1-into-d2 incident),
  then `login_check`, then registry. One profile at a time; never pre-start the
  next container while a login is pending.
- `run_daily.sh` kills stray reward containers before starting (lock hygiene) —
  a 01:30 run still in progress at 02:00 gets killed by the next line; accepted.
  `default` remains the historical web volume: which Microsoft account it holds is
  not registered and not recoverable from the volume — [INFERENCE] one of the two
  gmails; both gmails have mobile grid slots, and `prod_1` now has its own
  deterministic web volume, so coverage no longer depends on it (details:
  `profiles/README.md` § Web).
- Everything runs inside the `rewards-farmer-main-rewards-farmer:latest` image
  (built on the server only; no Dockerfile in this repo; entrypoint
  `/entrypoint.sh`; its `/app/src` is frozen at 2026-08-26). The wrappers
  bind-mount `src/rewards_tasks.py` **only** (`:ro`) over the image copy — it is
  the single hot-patchable module.
- **Deploy gotcha:** the merged `rewards_tasks.py` imports `log_utils` and relies
  on upstream `element_selectors`/`tab_utils` — none of which are bind-mounted or
  in the image. Do NOT rsync the new `rewards_tasks.py` to the server without
  also shipping `src/log_utils.py` (and matching selector/tab modules) or
  rebuilding the image; the server currently runs the older self-contained copy.
- Manual wrappers (all delegate to `run_task.sh <task> [profile]`; profile =
  `edge-profile/` for `default`, `edge-profiles/<name>` otherwise):
  `run_daily_set.sh`, `run_explore_on_bing.sh`, `run_visual_search.sh`,
  `run_misc_cards.sh`, `run_required_searches.sh`, `run_bonus_points.sh`.
  Tasks: `daily_set explore_on_bing visual_search misc_cards required_searches
  bonus_points all login_check` (`login_check`: rc 0 signed-in / 2 wall; never
  part of `all`). Env: `VISUAL_SEARCH_RUNS`, `REQUIRED_SEARCH_RUNS` (default 30
  searches, random scroll + 5–6 s dwell, `[ACTION]` logging).
- `web_login.sh <profile> [novnc-port]` — web-profile provisioning (noVNC sign-in,
  then `run_task.sh login_check <profile>`). Web profile procedure:
  `docs/profile-login-procedure.md` §2.
- Visual search asset order: `/data/edge-profile/visual-search-asset.jpg` →
  `/data/edge-profile/visual_search.jpg` → `/app/visual-search-asset.jpg` →
  `/app/visual_search.jpg`. Web logs: `logs/web-run[-<profile>].log`,
  `logs/web-run-<task>[-<profile>]-…log`.
- Supporting modules (imported by `rewards_tasks.py`): `tab_utils`, `llm_utils`
  (Ollama queries; `setup_logging` is never called → log-level env vars are inert),
  `mouse_trajectory`, `mimic_typing`, `element_selectors`.

## DEAD / historical — kept on purpose, touch only on owner's word

| Path | What it is | Verdict |
|---|---|---|
| `src/main.py`, `src/constants.py` | upstream web entry + `data-dir` constants (reconciled by the image entrypoint, not in repo) | in-image; keep as provenance |
| `tools/rewards_full_crawl.py`, `rewards_act.py`, `quiz_step.py`, `d3_tile_inventory.py` | live-device probes from the tile-map investigation (`docs/ideas/2026-09-09-d3-tile-map.md`) — import the mobile driver | keep: still the best diagnostic kit |
| `scripts/factory.ps1` | Windows scrcpy login/snapshot driver — superseded by variant-direct seeding (`docs/profile-provisioning-mobile.md`) for every profile since d4 | keep as fallback; use factory volume 5556 flow only when reseeding the baseline |
| `src/fitts_law.py`, `recordpress.py`, `analyze_keypresses.py`, `visualize_*.py`, `check_selectors.py`, `random_image_for_visual_search.py` | upstream PoC/dev tooling, zero live imports | keep (upstream heritage; deps in pyproject serve only these + web) |
| `Proof-Of-Concept-Artifacts/` | self-contained PoC evidence package (UI dumps, screenshots, ADB ps1 wrappers); `docs/runtime-info.md` is cited by live docs | keep; ignore README drift (`back.ps1` never existed) |
| `docs/superpowers/` | original plans/specs (2026-09-01 era) | historical record |
| `cron/README.md` | grid history — describes the pre-2026-09-14 8×3 h grid | superseded by `profiles/README.md` § Cron grid |
| `README.md` | upstream community readme (Ollama, poetry, local Edge) — says nothing about the farm | provenance only; read `AGENTS.md` instead |
| `docs/ideas/*` | decision records: migration (done; web-retirement end-state NOT yet reached), d2 (historical), d3 tile map (canonical), points-reader-api (**the open someday-item**) | keep |

## Operational hazards (learned, not hypothetical)

- Device lock `/tmp/bing-5555.lock`: `run` queues (blocking), `use` refuses
  (rc 3). Expect queued manual runs to start after a cron line finishes — kill
  them if stale (`ps -eo pid,ppid,lstart,cmd | grep bing.sh`, kill the flock
  holder's whole process group).
- Launching a detached manual run over ssh: bare `&` silently dies AND
  double-queues duplicates. Use
  `setsid nohup ./bing.sh run daily --profile P --no-debug >/tmp/x.out 2>&1 </dev/null &`
  and verify exactly one pid appears.
- `bing.sh snapshot` = factory volume ONLY (see LIVE above).
- Web image `/app/src` is frozen: never assume local web fixes reach the server
  without the companion-file rsync (see deploy gotcha in § LIVE web layer).
- Open watch item (2026-09-15): d6 streak — post-sweep probe showed `Check in`
  still present; verify the streak card credited on the next day's run.
- Windows dev box: `py -3` has pytest/ollama; never use the hermes venv python.
