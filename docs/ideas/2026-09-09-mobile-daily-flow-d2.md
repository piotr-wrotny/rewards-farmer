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
