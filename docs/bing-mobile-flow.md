# Bing mobile flow — ReDroid (server-side)

> **STATUS: TEST FLOW (logged-out dev mode).** This map describes the *test* flow that
> runs **without a Microsoft account** against a freshly `pm clear`-ed Bing app. Every
> run re-traverses first-run noise (FRE, permission prompts, region popup) — that is why
> it has auto-allow handlers and wall detection.
>
> The **production flow** will run on the owner's credentials: the app stays signed in,
> FRE/onboarding/permission dialogs never reappear, and the Rewards page is the real
> dashboard (Daily set / Read to earn cards) instead of the sign-in wall. Handlers below
> stay in code for robustness but are NOT flow steps in prod — the core prod steps are
> marked with **[PROD]** below.

Runtime: `com.microsoft.bing` 34.0.440821002 (global) on ReDroid 14 (x86_64, ARM
translation), server `10.17.103.115`, container `redroid` (see AGENTS.md § Mobile flow
for the DNS-required docker run). Driver: `src/bing_mobile_flow.py` (uiautomator2) from
the Windows dev machine via SSH tunnel `15555 → 127.0.0.1:5555`. Screen 720x1280@320.

Every step is verified by a screenshot in `artifacts/screenshots/` (+ UI hierarchy dump
in `artifacts/ui/`); `--debug` adds a screenshot per executed action. Actions are logged
as `[ACTION] <context> [<detail>] trigger=<source>`.

## Step map (verified 2026-09-01, evidence: artifacts/screenshots/NN-*)

| # | Step | Selector / detection | Evidence shot | Prod? |
|---|------|----------------------|---------------|-------|
| 0 | `pm clear com.microsoft.bing` (dev reset for a fresh attempt) | ssh + adb, `--clear` flag | log `[CLEAR] ... Success` | dev-only |
| 1 | Launch | `am start com.microsoft.bing/.…ity` | `01-after-launch` | **[PROD]** |
| 2 | Permission dialogs (camera, notifications…) | focus contains `permissioncontroller`; click `permission_allow_button` / `_foreground_only_` / `_one_time_` | `02-action-permission-accepted` | handler only |
| 3 | FRE first-run: dismiss "Maybe later" | focus `BingAppGlobalFreActivity`; tap `com.microsoft.bing:id/sapphire_fre_bing_no_button` | `03-fre-screen`, `04/05-*-fre-maybe-later` | handler only |
| 4 | "Country/region updated" popup (appears with network, no GMS) | focus `ToModifyMarketPopupActivity`; tap `text="OK"` | `06` preceded by `[ACTION] popup` | handler only |
| 5 | Home ready-check | focus `MainSapphireActivity` AND `com.microsoft.bing:id/sa_search_box` exists | `06-home-ready` | **[PROD]** |
| 6 | Search: tap box | `sa_search_box` → focus `AIToolsSuggestActivity` | `07-action-tap-search-box` | **[PROD]** |
| 7 | Type query | `send_keys` (text visible in dump) | `08-action-type-text` | **[PROD]** |
| 8 | Submit | `KEYCODE_ENTER` → focus `com.microsoft.sapphire.app.browser.BrowserActivity` | `09-action-key-enter-submit-search` | **[PROD]** |
| 9 | Results settle + verify | `BrowserActivity` + webview (SERP real: Wikipedia etc. after DNS fix) | `10-search-results` | **[PROD]** |
| 10 | Back to home | `KEYCODE_BACK` → `MainSapphireActivity` | `11-action-key-back-leave-results` | **[PROD]** |
| 11 | Open profile menu | `com.microsoft.bing:id/sa_profile_button` | `12/13-profile-menu` | **[PROD]** |
| 12 | Rewards page | `text="Microsoft Rewards"` → focus `…runtime.templates.TemplateActivity` | `14/15-rewards-page` | **[PROD]** |
| 13 | Classify Rewards state | dump regex: RTE card `content-desc="Read to earn, , N out of M points earned"` → `rte` / done text `Read to earn, N points earned` → `done` / `Join Microsoft Rewards|Access now` → `wall` | `16-rewards-state-<state>` | **[PROD]** (state check) |
| 14 | **[PROD]** Click Read-to-earn card → article feed (logged-out: wall reached, flow stops here with evidence) | RTE card bounds center | `read-to-earn-feed` | **[PROD]** |
| 15 | **[PROD]** Article loop (ported from emulator flow): pick card (title >25 chars + source line `· ` below, skip video badge `m:ss`, ad bands `. Ad,`), tap, dwell-scroll 5–10 s, back; up to N articles | dump heuristics in `candidate_articles()` | `article-opened-/read-N` | **[PROD]** |
| 16 | **[PROD]** Tab hygiene (from deployed read_to_earn.py): tab manager `content-desc="Tabs"`, close via `Close tab: <name>`, switch via `Tab: <name>` | see deploy/read_to_earn.py | — | **[PROD]** |

## Test vs production

| | Test (this map, `--clear` runs) | Production (owner credentials) |
|---|---|---|
| Account | none (logged out) | signed-in MS account |
| Entry noise | FRE, permission prompts, region popup every run (after `--clear`) | none — first-run already done, permissions granted |
| Rewards page | "Join Microsoft Rewards" wall (`Access now` → OneAuth, ends at `[2603]`/wall) | full dashboard: streak, Daily set, **Read to earn** card |
| Permission/popup handlers | exercised every run — that is their purpose | present as safety net only; not flow steps |
| Dev reset | `--clear` (adb `pm clear`) between attempts | never (would log out) |
| Verification | screenshot per step/iteration in `artifacts/` | server logs `[ACTION]` lines |

The emulator-era article heuristics (video/ad skip, source-line pairing) were ported
verbatim from `deploy/read_to_earn.py` and are expected to work 1:1 on ReDroid — same app
version, same `com.microsoft.bing:id/*` ids (PoC: selector parity, no coordinate use).
They are only reachable once a signed-in state unlocks the Rewards dashboard.

## Known states / gotchas

- `--clear` → first `am start` shows a permission dialog that holds window focus; the
  home-wait loop handles it (do not use `wait_activity` for post-launch home).
- Glance card `content-desc="Rewards"` [32,976][312,1144] misroutes to `CameraActivity`
  on a fresh logged-out install — use the profile-menu path instead (step 11).
- `ToModifyMarketPopupActivity` blocks home after FRE **only when the container has
  network** (PoC had none). Handled at step 4.
- DNS: container needs `androidboot.redroid_net_ndns=2` + resolver IPs (see
  Proof-Of-Concept-Artifacts/docs/runtime-info.md — verified fix).
