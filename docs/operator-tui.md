# Operator TUI (`tools/profile_tui.py`)

Textual-based operator console for profile onboarding, maintenance kill-switch,
and resume of incomplete mobile sessions.

Run locally (Windows):

```bash
py -3 tools\profile_tui.py
```

Default mode has mouse disabled (safe baseline for terminals that print escape garbage on mouse move).

Optional:

```bash
py -3 tools\profile_tui.py --no-browser
py -3 tools\profile_tui.py --mouse
```

## Core behavior

- all server actions run over SSH (`piotr.wrotny@10.17.103.115` by default),
- long tasks run in background workers (UI stays responsive),
- command output goes to the right-side log panel,
- profile table is built from:
  - mobile variants (`~/redroid-variants`),
  - web profiles (`~/rewards-farmer-main/edge-profiles`),
- left panel columns are compact (`Profile | M | W | State | Today`) for readability.
- `M` and `W` each show two dots:
  - first dot (orange) = profile exists,
  - second dot = auth status (`green` logged-in, `red` logged-out, `gray` unknown).

## Keybindings

- `x` open centered action menu (recommended)
- `Enter` open action picker for currently selected profile row
- `l` refresh profiles
- `b` busy-state check
- `g` open stats center (per-profile totals/daily/gain/done-today)
- `a` add profile flow (mobile prepare + web view + mobile view)
- `p` prepare mobile profile only
- `w` start web view/tunnel
- `m` start mobile view/tunnel
- `o` start both views
- `s` run single orchestrated flow for selected profile
- `1` verify web (`run_task.sh login_check <profile>`)
- `2` verify mobile (`mobile_profile_preflight.sh post-login <profile>`)
- `t` maintenance status
- `k` kill-switch soft
- `Shift+H` kill-switch hard (with confirmation modal)
- `d` disable maintenance mode
- `v` preview incomplete mobile sessions
- `r` resume incomplete mobile sessions (starts in background with PID + log path)
- `y` resume status/tail (running process + tail from latest resume log)
- `c` stop local tunnels/views
- `q` quit

If no row is selected, profile-required actions open a modal input prompt.
Footer is intentionally minimal (Quit + Menu) to avoid horizontal scrolling;
all operations are available from the `x` popup menu.
In popup menu, highlighted action now shows:
- command/script it runs,
- short explanation of expected behavior.
- actions are grouped by workflow area (Overview, Onboarding, Views, Runs, Validation, Maintenance, Recovery).
- for `r` (resume run), output includes `pid` and `log=...` so you can follow progress.
- use `y` to quickly inspect whether resume is still running and what it logs now.
- `s` does:
  - mobile slot activate (`bing.sh use`),
  - mobile rewards probe/execute (`bing.sh run rewards --iters 0`),
  - web bonus claim (`run_task.sh bonus_points`) when web is available,
  - summary with skip reasons when actions are unavailable.
- `s` streams running logs live into `RichLog` (not only at the end).
- after `b` (busy check), profile rows are color-marked:
  - yellow + `RUN` for currently running profile,
  - green + `DONE` when the profile already completed daily run today.
- profile legend is shown under the left table for fast interpretation.
- stats center (`g`) opens as a dedicated modal view built from:
  - latest `logs/points-snapshot-*.tsv` (if available),
  - latest `logs/bing-<profile>-daily-*.log` for done-today and gain.
  - and prefers per-profile latest `bing-<profile>-points-snapshot-*.log` for
    **current profile total** (`Total now` column).

Mouse is disabled by default. Use `--mouse` only when your terminal handles
mouse reporting correctly.

## Maintenance and resume integration

TUI wraps these scripts:

- `scripts/server_maintenance.sh` (`status|enable|disable|kill-switch`)
- `scripts/resume_incomplete_mobile.sh` (`--dry-run` and resume mode)

Maintenance gate file:

- `~/rewards-farmer-main/.maintenance-mode`

When enabled, daily automation and dispatcher/resume are blocked until disabled.

## Deployment checks (recommended)

Run locally after changes:

```bash
python -m py_compile tools\profile_tui.py
py -3 -m pytest tests\test_profile_tui.py -q
```

What is covered:

- keybinding dispatch (`t`, `w`, `v`, `c`) in headless Textual runtime,
- modal profile input interaction when the profile table is empty,
- backend op wiring through `OperationResult` paths.
