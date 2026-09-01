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

## WORKING STATE (verified 2026-09-01, profile `prod_2` / 616piotrek@gmail.com)

Signed-in path works on ReDroid via `./bing.sh run screenshot --profile prod_2` (exit 0,
`state=home`). Verified end-to-end with evidence in `artifacts/prod_2/`:

| Action | Result | Evidence |
|---|---|---|
| Launch + settle at home | `MainSapphireActivity`, `sa_search_box` present, NO FRE/popups (signed-in: no first-run noise, as predicted) | `screenshots/01-after-launch.png`, `02-home-ready.png` |
| Profile menu | email + Total/Daily points visible, no "Sign in" | `screenshots/02-prod-profile-prod2-CONFIRM.png` (earlier session) |
| Rewards page | profile → `text="Microsoft Rewards"` → focus `TemplateActivity` | `screenshots/demo-1-rewards.png`, `ui/demo-rewards.xml` |
| Search opens browser tab | query → `BrowserActivity` (SERP) | `screenshots/demo-4-serp-tab.png` |
| Tab manager | `description="Tabs"` works; lists `Tab: Rewards`, `Tab: pogoda Krakow` (×2 each) | `screenshots/demo-5-tabmanager-2tabs.png`, `ui/demo-tabmanager-2.xml` |
| **Tab switch** | click `Tab: Rewards` → focus `TemplateActivity`; pixel-diff vs `demo-1-rewards` = **0.001** (same page), vs SERP = 0.71 | `screenshots/demo-6-switched-to-rewards.png` |

Notes from the demo: each Rewards visit opens ANOTHER "Rewards" tab (duplicates pile up —
tab hygiene from the old emulator flow matters); tab selectors (`Tabs`, `Tab: <name>`,
`Close tab: <name>`) are identical to `deploy/read_to_earn.py`.

### Read-to-earn e2e (port of `deploy/read_to_earn.py`, verified 2026-09-01)

`./bing.sh run read-to-earn --profile prod_2` — session model per
`docs/superpowers/specs/2026-09-01-read-to-earn-port-spec.md` (5/session, 20 sessions,
60 total, global seen-set, idle cap 8, `cleanup_tabs` terminal invariant).

| Claim | Evidence |
|---|---|
| Points accrued 3 reads | RTE card content-desc `0 out of 30` (pre) → `9 out of 30` (post); `artifacts/prod_2/ui/05-rewards-state-rte.xml` runs 14:39/14:42 |
| 3 distinct articles read | screenshots `07/08/09-session1-article-*.png`, pairwise pixel-diff 0.352/0.469 (different pages, not stale frames) |
| Full daily cap | second run: `articles_read=10, sessions=2, rc=0` (5+5 split proves session loop); card → `done`: `Read to earn, 30 points earned`, fresh probe `state=done rc=0` |
| Tab hygiene | `[ACTION] tap [close-tab Rewards]`, `cleanup: closed 1 tabs`, zero-tabs invariant |

ReDroid-specific calibration (deviations from 1:1, documented in driver docstrings):
feed cards have source (`Daily Mail`) and age (`15h ago`) as SEPARATE nodes —
`feed_visible`/`candidate_articles` anchor on `AGE_LINE` (digit + ago/temu) with the
age measured from the title TOP (−40 px margin, nodes overlap); each title appears
twice, keep the tallest (short duplicate centers on the Like/Share row). Home gates
require `sa_profile_button` — the MSN feed view shares `MainSapphireActivity` +
search box but has no profile button (caused one rc=2).

## Test path vs production path

| | Test path (`test`) | Production path (`prod_N`) |
|---|---|---|
| Account | none (logged out) | signed-in MS account |
| Entry noise | FRE, permission prompts, region popup every run (after `--clear`) | none — first-run already done, permissions granted (verified in WORKING STATE above) |
| Rewards page | "Join Microsoft Rewards" wall (`Access now` → OneAuth) | full dashboard: `TemplateActivity`, streak/points (verified) |
| Permission/popup handlers | exercised every run — that is their purpose | present as safety net only; not flow steps |
| Reset | `bing.sh clear` (adb `pm clear`) between attempts | never (would log out; exit 3 guard) |
| Verification | screenshot per step/iteration in `artifacts/<profile>/` | server logs `[ACTION]` lines + demo trail above |

The emulator-era article heuristics (video/ad skip, source-line pairing) were ported
verbatim from `deploy/read_to_earn.py` and now belong to the production map (reachable on
`prod_2`). Full old-flow spec for the 1:1 port: produced by EmulatorFlowSpec analysis —
see `docs/superpowers/specs/` follow-up.


## Known states / gotchas

- `--clear` → first `am start` shows a permission dialog that holds window focus; the
  home-wait loop handles it (do not use `wait_activity` for post-launch home).
- Glance card `content-desc="Rewards"` [32,976][312,1144] misroutes to `CameraActivity`
  on a fresh logged-out install — use the profile-menu path instead (step 11).
- `ToModifyMarketPopupActivity` blocks home after FRE **only when the container has
  network** (PoC had none). Handled at step 4.
- DNS: container needs `androidboot.redroid_net_ndns=2` + resolver IPs (see
  Proof-Of-Concept-Artifacts/docs/runtime-info.md — verified fix).
