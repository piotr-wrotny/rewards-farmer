# Bing mobile flow — ReDroid (server-side)

> **STATUS: TEST PATH.** This is the *test* path itself, mapped end-to-end: it runs
> **without a Microsoft account** against a freshly `pm clear`-ed Bing app, re-traverses
> first-run noise every run (FRE, permission prompts, region popup — auto-handled), and
> **ends at the logged-out sign-in wall**. That wall is the test path's terminal state.
>
> The **production path is a SEPARATE path to be mapped later**, once the owner's
> credentials are attached: signed-in app, no first-run noise, real Rewards dashboard
> (Daily set / Read to earn), article loop, tab hygiene. The permission/popup handlers
> in `src/bing_mobile_flow.py` remain there as a safety net but will NOT be flow steps
> in prod. The emulator-era article heuristics ported into `candidate_articles()`
> (deploy/read_to_earn.py parity) are reserved for that future prod map — they are not
> reachable on the test path.

Runtime: `com.microsoft.bing` 34.0.440821002 (global) on ReDroid 14 (x86_64, ARM
translation), server `10.17.103.115`, container `redroid` mounted on the active profile
volume (see AGENTS.md § Mobile flow; `./bing.sh use <profile>`). Driver:
`src/bing_mobile_flow.py` (uiautomator2) — normally via `./bing.sh run … --profile P` on
the server; from the Windows dev machine via SSH tunnel `15555 → 127.0.0.1:5555`.
Screen 720x1280@320.

Every step is verified by a screenshot in `artifacts/<profile>/screenshots/` (+ UI
hierarchy dump in `artifacts/<profile>/ui/`). Evidence is keyed by profile variant
(`test` = logged-out path, `prod_N` = signed-in) and the buckets are never mixed.
`--debug` adds a screenshot per executed action (default on for `test`). `--clear` is
refused on prod profiles (it would log the account out). Actions are logged as
`[ACTION] <context> [<detail>] trigger=<source>`.

## Step map (verified 2026-09-01, evidence: artifacts/dev/screenshots/NN-*)


| # | Step | Selector / detection | Evidence shot | test-only? |
|---|------|----------------------|---------------|-----------|
| 0 | `pm clear com.microsoft.bing` (dev reset for a fresh attempt) | ssh + adb, `--clear` flag | log `[CLEAR] ... Success` | yes |
| 1 | Launch | `am start com.microsoft.bing/.…ity` | `01-after-launch` | |
| 2 | Permission dialogs (camera, notifications…) | focus contains `permissioncontroller`; click `permission_allow_button` / `_foreground_only_` / `_one_time_` | `02-action-permission-accepted` | yes (signed-in: granted once, never seen) |
| 3 | FRE first-run: dismiss "Maybe later" | focus `BingAppGlobalFreActivity`; tap `com.microsoft.bing:id/sapphire_fre_bing_no_button` | `03-fre-screen`, `04/05-*-fre-maybe-later` | yes |
| 4 | "Country/region updated" popup (appears with network, no GMS) | focus `ToModifyMarketPopupActivity`; tap `text="OK"` | `06` preceded by `[ACTION] popup` | likely |
| 5 | Home ready-check | focus `MainSapphireActivity` AND `com.microsoft.bing:id/sa_search_box` exists | `06-home-ready` | |
| 6 | Search: tap box | `sa_search_box` → focus `AIToolsSuggestActivity` | `07-action-tap-search-box` | |
| 7 | Type query | `send_keys` (text visible in dump) | `08-action-type-text` | |
| 8 | Submit | `KEYCODE_ENTER` → focus `com.microsoft.sapphire.app.browser.BrowserActivity` | `09-action-key-enter-submit-search` | |
| 9 | Results settle + verify | `BrowserActivity` + webview (SERP real: Wikipedia etc. after DNS fix) | `10-search-results` | |
| 10 | Back to home | `KEYCODE_BACK` → `MainSapphireActivity` | `11-action-key-back-leave-results` | |
| 11 | Open profile menu | `com.microsoft.bing:id/sa_profile_button` | `12/13-profile-menu` | |
| 12 | Rewards page | `text="Microsoft Rewards"` → focus `…runtime.templates.TemplateActivity` | `14/15-rewards-page` | |
| 13 | Classify Rewards state; **wall = TEST PATH TERMINAL** | dump regex: `Join Microsoft Rewards|Access now` → `wall`; RTE card `content-desc="Read to earn, , N out of M points earned"` → `rte`; done text `Read to earn, N points earned` → `done` | `16-rewards-state-<state>` | |

## Test path vs future production path

| | Test path (this map) | Production path (owner credentials) |
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
They belong to the future production map and are not reachable on the test path.


## Known states / gotchas

- `--clear` → first `am start` shows a permission dialog that holds window focus; the
  home-wait loop handles it (do not use `wait_activity` for post-launch home).
- Glance card `content-desc="Rewards"` [32,976][312,1144] misroutes to `CameraActivity`
  on a fresh logged-out install — use the profile-menu path instead (step 11).
- `ToModifyMarketPopupActivity` blocks home after FRE **only when the container has
  network** (PoC had none). Handled at step 4.
- DNS: container needs `androidboot.redroid_net_ndns=2` + resolver IPs (see
  Proof-Of-Concept-Artifacts/docs/runtime-info.md — verified fix).
