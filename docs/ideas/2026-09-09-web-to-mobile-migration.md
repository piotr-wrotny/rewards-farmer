# Idea: move the whole farm web → mobile (NOT started — separate branch)

Status: recorded 2026-09-09; Piotr opens the branch later and provisions
`domena2`, `domena3` profiles for it. Do not start on the current branch.
Owner: Piotr.

## Why (evidence from this repo)

- **Detection**: web = Selenium (navigator.webdriver/CDP artefacts, patched only
  superficially in `main.py`/`mouse_trajectory.py`). Mobile = uiautomator2 → input
  events at UI layer; to the Bing app that IS touch. One device story per account
  instead of containerized desktop Edge + phone app simultaneously.
- **Stack**: farm reduces to redroid + `bing_mobile_flow.py`; Xvfb/Edge/Selenium/
  noVNC stack retires. Registry/snapshots/probes already mobile-shaped.
- **Coverage** (2026-09-09 domena1-prod run as evidence): search + visual search
  ≈ the bulk of points; the app does both. `required_searches` is nearly the
  existing mobile search step (scroll+dwell already implemented).
- Web SKIPs on the fresh profile (daily set/explore/misc_cards NoSuchElement) show
  the new-account UI has little web-only surface to lose early on.

## Gaps to close BEFORE any cutover (each = its own PR)

1. **required_searches on mobile** — fixed phrase pool, scroll 120–360 px, dwell
   5–6 s, per-run pacing; port constants from `rewards_tasks.py`, keep the
   `[ACTION] ... trigger=` logging convention. Closest existing code; first PR.
2. **daily_set / misc_cards / bonus via WebView** — app renders rewards.bing.com
   inside WebView; uiautomator2 sees the DOM as accessibility nodes but selectors
   must be re-derived + hardened (our `element_selectors.py` lesson: never
   positional). Needs live revalidation on domena2/3, NOT on prod_1.
3. **visual_search** — web uses a file input; the app path is camera-search →
   pick from gallery. `adb push` asset to /sdcard/Pictures + media scan + drive
   the picker. Hardest step; do last.
4. **Throughput/serialization** — RTE 60 articles ≈ 35 min; full daily ≈ 1 h per
   account, serialized today by flock `/tmp/bing-5555.lock` on ONE container.
   N profiles ⇒ N redroid containers (one port per profile; `bing.sh` gains
   `--port/--cont` derived from profile, per-port flock). This is the real
   infra work; size it before promising cutover.
5. **Kill-switch ordering** — keep web cron as fallback until parity is measured
   (points delta 2–3 consecutive days, both accounts). Then retire web lines;
   DO NOT delete web code — keep it as fallback (tag before any removal).

## Risks

- Single point of failure: one Bing app update can farm-break the whole fleet
  (web was the independent backup; `assets/*.apk` pinning + snapshot-rollback
  via factory is the mitigation we already have).
- App updates can silently change layouts → the mobile flow is selector-fragile
  in a way Selenium-with-explicit-waits partially isn't. Mitigation: the
  per-action screenshots + UI dumps (`--debug`) we already capture.
- Quota behavior across surfaces may differ (some activities exist on one surface
  only — e.g. some promos). Parity must be measured in POINTS, not task counts.

## Measurement plan (what "parity" means)

Per account, 3+ days on domena2/3 (NOT prod_1): mobile-only daily vs web-only
daily (split days), compare total points earned/day (needs the points-reader —
`2026-09-09-points-reader-api.md`; these two ideas compose: reader first, then
migration uses it to prove parity).

## Decision record

2026-09-09: direction agreed as incremental (searches → cards → visual), never
big-bang; prod_1/domena1-prod stay on the current web+RTE schedule until domena2/3
prove parity.
