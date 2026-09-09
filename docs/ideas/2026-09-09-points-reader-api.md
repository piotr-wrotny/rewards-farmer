# Idea: points reader — per-account balance, delta, daily-set progress (NOT started)

Status: recorded 2026-09-09; branch out from here when starting. Owner: Piotr.

Need, per PROD profile (`default`/prod_1, `domena1-prod`, later domena2/3):
current total points, day-over-day delta, and dashboard progress `x/y`
(daily set, searches, streak) — one place to see which account is farming
and how the growth trends.

## Core design decision (do not skip)

Split into two components with different risk:

1. **Collector** — the ONLY part that touches Microsoft accounts (low frequency,
   profile-lock aware). Appends to a local time series.
2. **API** — reads the local DB only. Zero account risk, can be hit freely.

Never let the API scrape live accounts on demand.

## Collection sources (verified vs to-verify)

- **Web (verified path)** — the signed-in rewards.bing.com dashboard already
  renders everything: earn tab `[id$="-tab-/earn"]`, and `element_selectors.py`
  already has `get_points_breakdown_button` + `get_points_earned_from_searches_on_points_breakdown`.
  A read-only variant of `verify_signed_in` (login_check, 2026-09-09) extended
  with points reads is ~1 task. Runs in the existing image+volume.
- **Mobile (verified reachable)** — the app's Rewards WebView is already driven
  by `bing_mobile_flow.py` (rewards step); the home glance card shows progress
  (`Rewards 0/75` seen 2026-09-09). Read-only pass reusing that navigation.
- **HTTP API (TO VERIFY first)** — community tools replay
  `https://rewards.bing.com/api/welcome` (JSON: `availablePoints`, `userStatus`
  with daily-set/streak state) using the account's cookies. If it works from our
  server it beats a browser: no volume lock, seconds per profile. Verify on
  `domena1-prod` only, read-only, once. `[INFERENCE — unverified against our accounts]`
- **Log mining (free, partial)** — `DONE state=… articles_read=N` in RTE logs and
  `[OK]/[SKIP]` lines in web logs already describe activity; deltas need absolute
  points, so this only enriches, not replaces.

## Storage + serving

- `~/rewards-metrics/points.sqlite3` (server, outside the repo dir, root of a new
  volume): `points(profile TEXT, ts TEXT, source TEXT, total INTEGER,
  daily_set_x INTEGER, daily_set_y INTEGER, searches_x INTEGER, searches_y INTEGER,
  streak INTEGER, raw_json TEXT)` + unique `(profile, ts, source)`.
- Container: small FastAPI/uvicorn service, image built from repo; binds
  `127.0.0.1:8090` ONLY (same tunnel pattern as adb/noVNC).
  Endpoints: `GET /profiles`, `GET /profiles/<p>/points?from&to`, `GET /summary`
  (today per profile: total, Δ vs previous day, x/y).
- Collector is NOT a daemon: cron lines, staggered so a profile volume is never
  in two containers at once (same singleton-lock rules as `run_task.sh`).

## Cadence (anti-detection + lock safety)

- ≤ 2 scrapes/account/day: (a) piggyback right after the daily flow
  (`run_daily.sh <p> && ./points_report.sh <p>`), (b) optional morning sweep 06:30.
- Collector reads, clicks nothing (dashboard + points-breakdown panel award nothing —
  proven by `check_selectors.py` which only reads).

## Acceptance when implementing

1. `./points_report.sh <profile>` on server → row in sqlite, rc 0; refuses when the
   profile's automation container is up (lock), rc 3.
2. API container answers `/summary` for all registered profiles (registry:
   `profiles/README.md`).
3. Two consecutive days on `domena1-prod` show correct Δ against the manually
   checked dashboard number.

## Out of scope (later)

Notifications (Telegram/e-mail on delta=0 days), charts UI, multi-day quota
forecast, points redemption.
