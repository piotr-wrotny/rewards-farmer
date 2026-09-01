# Read-to-earn e2e port spec (old Android-emulator flow → ReDroid driver)

Source of truth: `deploy/read_to_earn.py` (277 lines, imports only random/re/sys/time/
uiautomator2 at :16-21). Produced by code analysis 2026-09-01; port target
`src/bing_mobile_flow.py`. All line citations refer to `deploy/read_to_earn.py`
unless noted.

**Import-graph verdict:** `src/rewards_tasks.py`, `src/tab_utils.py`,
`src/mimic_typing.py`, `src/mouse_trajectory.py`, `src/fitts_law.py` are **UNUSED** by
the mobile flow (Selenium web-side stack; no import edge exists). DO NOT port them.
Humanization = exactly what `read_to_earn.py` does inline (§5).

## 1. Session contract (`run()` :222-279)

- One session = one successful click on the active `Read to earn` card
  (walk Rewards → card → feed).
- Articles per session: `max_per_session=5`; caps `max_sessions=20`, `max_total=60` (:240).
- `seen` = set of article **titles**, declared ONCE before the session loop (:247),
  added on every click (:268) — never re-clicked across ALL sessions.
- Inner guard: `while read_in_session < max_per_session and total < max_total` (:255);
  no-candidate → `idle_scrolls += 1`, feed swipe + 2 s; `idle_scrolls > 8` → break
  session ("no fresh articles left in this feed") (:257-263); reset on candidate (:264).
- Terminal: `walk_rewards_path()` False (active card regex gone / feed didn't open) →
  break → cleanup (:251-253, :165-166).
- Tab closure semantics: article tabs STAY OPEN during sessions; ALL tabs closed only
  at end (`cleanup_tabs`, :276-278; docstring line 9: zero open tabs invariant). No
  per-session cleanup.
- Logging: `[session N (k/5)] title` (:274). (ReDroid driver keeps its own
  `[ACTION] … trigger=` convention per AGENTS.md.)

## 2. Step-by-step (verbatim constants)

```python
PKG = "com.microsoft.bing"
VIDEO_BADGE = re.compile(r"^\d+:\d\d$")
SOURCE_LINE = re.compile(r"^.+\s·\s.+$")
SKIP_WORDS = ("Oferta", "Koszula", "Regatta", "Search", "Rewards", "Image Creator", "Trending")
RTE_ACTIVE = re.compile(
    r'content-desc="Read to earn, , \d+ out of \d+ points earned"'
    r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
RTE_DONE_TEXT = re.compile(r'text="Read to earn, \d+ points earned"')
```

Per session:
1. `walk_rewards_path` (:155-167): open Rewards page → `find_read_to_earn`
   (:114-127: ≤10 dumps; RTE_ACTIVE → card center; RTE_DONE_TEXT → None [terminal];
   else rewards-scroll + 2 s) → click card → sleep 8 → `feed_visible` (:128-129:
   any text matching SOURCE_LINE) — else terminal.
2. Inner article loop per §1: candidates → `random.choice(cands[:3])` → click →
   sleep U(5,7) [article load] → dwell U(5,10) reading → `press back` →
   sleep U(3,4.5).
3. Repeat until caps or terminal; then `cleanup_tabs` (all closed).

Rewards-entry DELTA (intentional): old flow used bottom `Apps` icon → `text="Rewards"`
(:130-151). ReDroid uses profile-menu path (`sa_profile_button` →
`text="Microsoft Rewards"`) — PoC-proven, glance card misroutes to CameraActivity.

## 3. Tab hygiene state machine (:48-97) — verbatim selectors

- `open_tabs_manager` (:48-56): ≤3 attempts: `d(description="Tabs")` → click, 2.5 s;
  else `press back` + 2 s. Fail → RuntimeError.
- `close_tabs(keep_feed, max_rounds=40)` (:59-79): regex
  `content-desc="Close tab: ([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"`;
  first match per round; skip when `keep_feed is not None and name.startswith("Rewards")`;
  click center; 1.5 s/round.
- `switch_to_feed_tab` (:82-89): `content-desc="Tab: Rewards"` bounds → click center, 5 s.
- `close_article_tab_return_to_feed` (:92-100): open manager → close non-Rewards* →
  switch to feed tab (fallback back). **Defined but UNUSED at runtime** — old runtime
  exits articles via `press back`; port the helper, keep back-press as live behavior.
- `cleanup_tabs` (:103-108): open manager → `close_tabs(keep_feed=None)` → back.
  Called once at end. Terminal invariant: zero open tabs.
- Demo-verified on ReDroid (2026-09-01): `Tabs` button, `Tab: <name>` entries, tab
  switch works (`docs/bing-mobile-flow.md` § WORKING STATE; `artifacts/prod_2/ui/demo-tabmanager-2.xml`).
  NOTE: each Rewards visit opens ANOTHER "Rewards" tab on ReDroid — duplicates pile up;
  `keep_feed` prefix rule keeps all of them until end-of-run cleanup.

## 4. Article heuristics `candidate_articles` (:173-202)

Already ported near-verbatim to `bing_mobile_flow.py:320-354` (ad bands ±350 px around
content-desc `. Ad,`/`Ad, `; title len > 25; SOURCE_LINE within 0..260 px below title
bottom; VIDEO_BADGE `^\d+:\d\d$` (y1>100) within 0..400 px above title → skip;
SKIP_WORDS substring; output `(title, cx, cy)`; caller: seen-filter + top-3 random).
CAUTION: px thresholds were tuned for the old 1080×2400 emulator; ReDroid is 720×1280 —
verify band widths against the first live prod feed dump; calibrate if candidates
vanish (debug screenshots will show whether feed cards are over-filtered).

## 5. Humanization — USED vs UNUSED

USED (all inline, uniform-random only): article-load settle U(5,7); dwell U(5,10);
reading swipes = short drags 250-450 px over 0.2 s + pause U(1.2,2.0) (:208-211);
post-back pause U(3,4.5); navigation scrolls fixed-px with 2 s settles; top-3 random.
UNUSED: every helper module from the Selenium stack (§0). Do not port Bezier/Fitts.

**Coordinate conversion** (old 1080×2400 → ReDroid 720×1280, proportional):
feed idle swipe (540,1600)→(540,700) ⇒ x=0.5·w, y 0.667→0.292·h;
rewards scroll (540,1800)→(540,700) ⇒ y 0.75→0.292·h;
article swipe (540,1500)→(540,U(1050,1250)) ⇒ x=0.5·w, y 0.625→U(0.437,0.521)·h,
duration 0.2 s, pause U(1.2,2.0). NOTE the old x=540 is SCREEN CENTER on 1080-wide —
the port must swipe at x=0.5, not 0.75.

## 6. Delta table (port actions)

| Behavior | Old flow | ReDroid driver | Action |
|---|---|---|---|
| Rewards entry | Apps icon → Rewards | profile button → "Microsoft Rewards" | keep ReDroid |
| RTE card find | 10× dump+scroll, done-text terminal | 6× fractional scrolls in rewards_state | align: 10 rounds, 2 s settle |
| Feed-open verify | SOURCE_LINE check post-click | MISSING | **PORT** (terminal on fail) |
| Session model | 5/session, 20 sessions, 60 total, global seen | single flat loop, per-call seen | **PORT** |
| Idle cap | 8 scrolls/session | 60 scrolls global | align to 8/session |
| Tab hygiene | 5 functions, end-cleanup all | ABSENT | **PORT all verbatim** |
| Wall handling | n/a (signed in) | SIGNIN_WALL detection | keep ReDroid addition |
| Post-article | press back (tab left open) | press back | keep (= old runtime) |
| Logging | plain | [ACTION] convention + artifacts | keep ReDroid |

## 7. Server notes

- Serial/launch: keep `127.0.0.1:<tunnel-or-5555>` + explicit `LAUNCH_ACTIVITY`;
  `d.app_start(PKG)` alone is not enough on ReDroid.
- Fre/permission handlers stay BEFORE the walk (prod: no-ops; test: required).
- Settle times: keep 1:1 first; extend only on observed timeouts over SSH.
- Run under `bing.sh run read-to-earn --profile prod_N` — flock guarantees single
  driver per device; exit 0 only on clean terminal states (done/wall/exhausted).
