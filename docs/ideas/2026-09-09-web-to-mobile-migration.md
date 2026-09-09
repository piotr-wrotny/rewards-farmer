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

## Lab findings (2026-09-09, local Docker with a domena1-prod profile copy)

Decided during the lab: **redroid is the primary track; web profiles are frozen**
(no new web selector work; web cron stays as-is until mobile parity, then retires).

Evidence gathered (read-only probes + one +5 card click, on the copied profile):

- The dashboard/earn UI our web flow drives is the SAME server-rendered React app
  the Bing app's WebView shows. `#moreactivities` ("Keep earning", progress 0/30),
  `#quests` (punchcards: onboarding 1/7 +1,320, Spotify 0/5), `#streaks` all exist —
  the web `misc_cards` SKIP is NOT absence of the section.
- Why web misc_cards SKIPs on current accounts: in this layout the earn content is
  lazy-hydrated — `#moreactivities` only exists after scrolling the dashboard/earn
  page, and the earn-tab click from `/dashboard` can be swallowed by the cookie
  banner + "Welcome to Microsoft Rewards" dialog (click intercepted at the card's
  point by an overlay). Production flow never scrolls before reading cards, so
  `_container_by_id('moreactivities')` raises → [SKIP].
- Card anatomy (mobile layout): `section#moreactivities > a[target=_blank]`, points
  as `+5` inside card text, section progress `p.text-metadata` = "N/30"; completed
  state also flips `data-disabled`. Old desktop selectors (`div.flex.w-full...`
  status row, `p:nth-child(2)` description) do not match this layout at all.
- Consequence for mobile port: the app's Rewards WebView contains exactly these
  sections as accessibility nodes → misc/daily-set/quests port is mostly
  uiautomator2 node walking, not new web selectors. **Do not invest in reworking
  web selectors.**
- Point targets visible on domena1-prod right now (what the mobile flow should
  capture): onboarding quest 7 tasks (+1,320 total), daily set (+50), Keep-earning
  cards 6×+5 (bing searches + edge welcome pages), streak bonus (12 stamps, 1000).

2026-09-09 (evening, addendum): after the lab, direction hardened to
**mobile-first**: new feature work (misc cards, daily set via WebView, quests,
points collection) happens in `bing_mobile_flow.py`; the web stack gets zero new
capability — it only keeps running its current tasks until retirement.
