# Mobile daily flow — domena2-prod (2026-09-09, branch `mobile-daily-flow-d2`)

## Search-point credit — OPEN (needs fresh profile)

- `required_searches` batch (30) completed 30/30 rc 0 on domena2-prod (16:06→16:22,
  ~32 s/search incl. 1-3 scroll swipes + 5-6 s dwell per SERP).
- **Points NOT credited by searches on this profile**: Daily points 53/75 before the
  batch (misc card +10 same run) and 53/75 after — zero delta from 30 SERPs.
- Two candidate causes, NOT distinguishable on this profile:
  1. Searches were already at their daily cap before the batch (web flow ran this
     account earlier? registry says web NOT provisioned — but account may have
     history from snapshot creation).
  2. Mobile-app searches don't credit the "search points" category at all until
     some eligibility (PC/mobile split, account maturity — cf. check-in inert on
     fresh domena2-prod, docs/bing-mobile-flow.md §7).
- **Verification protocol (fresh profile, e.g. domena3-prod once owner logs in):**
  1. Read `daily_points()` + `total_points()` baseline.
  2. Run 3 searches, re-read points → expect +X (mobile search pts usually 3/90
     mobile + 7/90... PC; actual split visible in web points breakdown only).
  3. If delta 0 after 3 searches: run web `required_searches` on the same account,
     re-read → separates "category exhausted" vs "mobile never credits".
  4. Only then decide if mobile `required_searches` belongs in the daily flow.

## Benefit-driven termination (user directive 2026-09-09)

Every stage must terminate on a **benefit signal, not a timeout/counter**:
- `required_searches`: run until search-points category stops crediting (probe
  points every N searches), not a fixed 30. Cap stays as a safety ceiling only.
- `misc_cards`: already benefit-driven (pool exhaustion = card loses
  'earn N points' desc) — correct as is.
- `read_to_earn`: already terminal on `done` state — correct.
- Anti-pattern to kill: "wbić nadmiarowo N i lecieć w timeouty".

## Cadence (user directive)

Search-to-search gap target 8–15 s (not minutes). Current implementation:
~32 s/search (2 s box + 1.5 s type + SERP settle 5 s + scroll 2×~1.2 s + dwell
5-6 s + back 3 s). Cut dwell to ~3-4 s and settle to 3 s → ~15-20 s. Re-measure
on fresh profile.

## Driver state (this branch)

- `screenshot` `--only` was never dispatched in `run_only` (fell through to
  `rewards_tail` → article loop!) — fixed: early return `screenshot_step()`.
- New: `build_phrase_pool()` (nouns.txt + SEARCH_QUERY_TEMPLATES, port of web
  rewards_tasks.py:348), `required_searches(count)` with per-iteration
  `ensure_home()` (after back from SERP the app can rest on
  AIToolsSuggestActivity/MSN — home search box not addressable there; tunnel
  pilot 2026-09-09), CLI choice `required-searches`, `--iters` = count.
- misc_cards on d2 at 53/75: pool still pays (1 card +10 credited 16:02).

## Full `daily` e2e on domena2-prod (16:39→16:52, rc 0, 13.6 min)

`--only daily --iters 15` (misc-cards → read-to-earn → 15 searches):

| Stage | Result | Points |
|---|---|---|
| misc-cards | pool drained: 0 cards left, `points_credited=0` (pool exhausted this day) | — |
| read-to-earn | `state=done` — terminal, skipped cleanly (benefit signal worked) | — |
| required-searches | 15/15 SERPs, 15 tabs closed in cleanup | 0 delta |
| Balance | `65/75 → 65/75` — account saturated for the day | — |

Key proof: every stage correctly hit its **terminal/benefit state** instead of
burning timeouts — misc pool empty, RTE `done`, searches capped by count. The
chain is idempotent-safe to re-run.

Remaining 10/75 daily pts on d2: presumably the search category (uncredited on
mobile here — see OPEN above) or days' quiz cards. Fresh-profile verification
will resolve.

## Cadence measured (16:39→16:52 daily run)

15 searches inside the daily chain took ~6.5 min → ~26 s/search (down from
32 s standalone; misc/RTE fast-paths help). Still above the 8–15 s target —
trim SERP settle 5 s → 3 s and dwell 5-6 s → 3-4 s next pass.

## HANDOVER → domena3-prod rebuild (user directive 2026-09-09 evening)

**Decision: d2 flow is NOT the truth. The full path gets re-derived from zero on
a fresh domena3-prod (local redroid). d2 will be run later with the flow proven
on d3.**

### Core design principle (user directive)
**Every flow stage must be driven by a Rewards TILES state, not a hardcoded
sequence.** Each stage exists because a tile offers points; the driver must
recognize "this tile no longer needs interaction" and skip it — never repeat
an action past its benefit.

### Tile → stage → completion-signal map (draft from d2 experience, to verify on d3)

| Rewards tile | Stage | Completion signal (no interaction needed when true) |
|---|---|---|
| Streak check-in card | `check_in` | `checked` alt-text icon present (day ring) — on d2 fresh account button was INERT (needs maturity, §7) |
| 'earn N points' pool cards | `misc_cards` | card's content-desc loses the `earn N points` suffix (verified, §1) |
| Read-to-earn card | `read_to_earn` | desc `Read to earn, N points earned` (no 'out of') = done state (verified) |
| Search category | `required_searches` | **UNRESOLVED on d2** — 30 SERPs gave 0 delta. On d3: baseline → 3 searches → re-read → web cross-check (protocol above). Until proven: cap by probe, not count |
| Daily set panel | NOT needed on mobile (§8) — dailies stack into misc pool automatically. Verify on d3 whether the widget even exists / behaves |
| Quiz/puzzle tiles | not yet mapped on mobile — d3 walk will reveal |

### Infra facts for d3 (local redroid on Windows)
- Server bing.sh is Linux-bound (docker volume paths under ~/redroid-variants).
  Local Windows redroid needs its own compose/run with same DNS props
  (`androidboot.redroid_net_ndns=2` REQUIRED, publish only 5555).
- The d2 evidence stands (this file + docs/bing-mobile-flow.md § daily chain);
  d3 work supersedes the d2-built `daily` chain order only if the tile map
  differs. The d2 run stays as regression reference.
- Tunnel job (bg_24) died on connection reset after ~80 min — irrelevant now,
  d3 is local (serial 127.0.0.1:5555 directly).
