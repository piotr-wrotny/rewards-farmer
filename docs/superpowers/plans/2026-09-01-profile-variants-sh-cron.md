# Profile Variants + bing.sh + Cron — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-profile (`test` / `prod_1` / `prod_2` …) Bing mobile flows on the server ReDroid, driven by one `bing.sh` entrypoint that behaves identically interactively and under the server's KRON crontab.

**Architecture:** Profiles are unpacked Android `/data` volumes (`~/redroid-variants/<name>/`) on server `10.17.103.115`; switching a profile recreates the stateless `redroid` container on that volume. `bing.sh` (server, repo-owned) resolves profile → container → invokes `src/bing_mobile_flow.py` with `--profile/--only`, logs to `logs/bing-<profile>-<action>-<TS>.log`, evidence to `artifacts/<profile>/`. `factory.ps1` (Windows) drives interactive login via scrcpy; snapshots move profiles between factory and variants.

**Tech Stack:** bash, PowerShell, Python 3 (uiautomator2), docker, adb, scrcpy.

**Spec:** `docs/superpowers/specs/2026-09-01-profile-variants-sh-cron-design.md`

## Global Constraints

- Server: `piotr.wrotny@10.17.103.115`, repo `~/rewards-farmer-main`; containers `redroid` (127.0.0.1:5555 = active/production) and `redroid-factory` (127.0.0.1:5556 = factory only).
- Boot props for BOTH containers (netd ignores DNS without `ndns`): `androidboot.redroid_gpu_mode=guest androidboot.redroid_net_ndns=2 androidboot.redroid_net_dns1=172.20.0.41 androidboot.redroid_net_dns2=172.20.0.42`.
- Bing pkg `com.microsoft.bing`; launcher `com.microsoft.sapphire.app.main.SapphireMainActivity`. Screen 720x1280.
- Snapshot order is sacred: `am force-stop com.microsoft.bing` → `sync` → sleep 3 → `docker stop` → tar whole `/data` → `docker start`.
- NEVER commit profile data: `profiles/*` gitignored except `README.md`; `profile-snapshots/` (local copies) gitignored; server snapshots `~/profile-snapshots/` never touch git.
- `pm clear` allowed only for variant `test`. KRON = crontab on this server (an existing scheduler process there will run `bing.sh` lines).
- No project-wide linters/suites in tasks; run only the named checks.

---

### Task 1: Server driver environment (uiautomator2 venv)

**Files:**
- Create on server: `~/rewards-farmer-main/.venv/` (never in git)
- Modify: `.gitignore` (add `.venv/`)

**Interfaces:**
- Produces: `~/rewards-farmer-main/.venv/bin/python` with `uiautomator2` importable. Task 4 calls it `$PY`.

- [x] **Step 1: venv + install**

```bash
ssh piotr.wrotny@10.17.103.115 'cd ~/rewards-farmer-main && python3 -m venv .venv && .venv/bin/pip install -q uiautomator2'
```

`ensurepip` missing on distro python → `sudo apt-get install -y python3.14-venv`; last-resort fallback `python3.12 -m venv` (all later steps unchanged).

- [x] **Step 2: Prove it drives the live container**

```bash
ssh piotr.wrotny@10.17.103.115 'cd ~/rewards-farmer-main && .venv/bin/python -c "import uiautomator2 as u2; d=u2.connect(\"127.0.0.1:5555\"); print(d.info[\"displayWidth\"], d.info[\"displayHeight\"])"'
```

Expected: `720 1280`.

- [x] **Step 3: Branch sync on server.** `git -C ~/rewards-farmer-main remote -v && git -C ~/rewards-farmer-main pull`. If no remote for this branch exists: deploy via `git -C . archive bing-server-flow src | ssh piotr.wrotny@10.17.103.115 'tar -x -C ~/rewards-farmer-main'` and record the deploy method in `AGENTS.md` § Mobile flow.

- [x] **Step 4: Commit** `.gitignore` += `.venv/` → `chore: server venv ignored`.

---

### Task 2: Driver CLI cutover — `--profile` + `--only`, exit codes 0/2/3

**Files:**
- Modify: `src/bing_mobile_flow.py`
- Modify: `AGENTS.md` § Mobile flow; `docs/bing-mobile-flow.md` (artifact paths)

**Interfaces:**
  - `--profile NAME` (default `test`) → evidence `artifacts/NAME/{screenshots,ui}` (replaces `--mode dev|prod`; dir `test` replaces `dev`)
  - `--only full|search|rewards|read-to-earn|screenshot` (default `full`)
  - `--debug/--no-debug`, default: ON iff `profile == "test"`
  - `--clear` with a non-`test` profile → exit 3, message
  - exits: 0 success incl. terminal `wall`/`done`; 2 flow failure; 3 infra (`InfraError`)

- [x] **Step 1: Evidence dirs per profile.** Replace `mode_dirs` block:

```python
ART_DIR = os.path.join(ROOT, "artifacts")  # artifacts/<profile>/{screenshots,ui}

def profile_dirs(profile):
    base = os.path.join(ART_DIR, profile)
    return os.path.join(base, "screenshots"), os.path.join(base, "ui")
```

`__init__(self, serial, debug=False, query="hello world", profile="test")` — replace the `mode` param with `profile`; `self.profile = profile`; `self.shot_dir, self.ui_dir = profile_dirs(profile)`; drop `self.mode`; `run()` banner prints `profile=`. Note `clear_app_data(self, server)` keeps taking `server` as its argument (main passes `args.server`).

- [x] **Step 2: Split `run()` into `to_home()` + `run_only()`** (keep `full` behavior byte-identical to today):

```python
def to_home(self):
    """Launch + settle at home with dialogs handled. Shared by every --only."""
    self.launch()
    self.shot("after-launch")
    if self.dismiss_fre():
        log("FRE dismissed")
    end = time.time() + 40
    while time.time() < end:
        self.accept_permissions()
        self.dismiss_popups()
        if ACT_HOME in self.focus() and self.d(resourceId=SEARCH_BOX).exists:
            self.shot("home-ready")
            return
        if ACT_CAMERA in self.focus():
            self.recover_camera()
        time.sleep(1)
    self.shot("home-timeout")
    raise RuntimeError(f"never reached home; focus={self.focus()}")

def screenshot_step(self):
    name = self.shot("screenshot")  # shot() returns the file basename
    return {"state": "home", "articles_read": 0, "screenshot": name}

def rewards_tail(self, iterations):
    """Rewards-page tail extracted verbatim from old run() (lines ~403-425)."""
    if not self.open_rewards():
        self.shot("rewards-page-unexpected")
        log(f"WARNING: rewards page focus={self.activity()} (continuing anyway)")
    state, card = self.rewards_state()
    self.shot(f"rewards-state-{state}")
    log(f"rewards state: {state}")
    if state != "rte":
        if state == "wall":
            log("LOGGED-OUT SIGN-IN WALL — read-to-earn needs an account (prod path).")
        return {"state": state, "articles_read": 0}
    self.tap(card, "read-to-earn-card")
    time.sleep(8)
    self.shot("read-to-earn-feed")
    return {"state": state, "articles_read": self.article_loop(iterations)}

def run_only(self, only, iterations):
    self.to_home()
    if only == "screenshot":
        return self.screenshot_step()
    if only == "search":
        serp = self.search_and_results()
        if not self.ensure_home():
            raise RuntimeError("home not reachable after search")
        return {"state": "searched", "serp": serp, "articles_read": 0}
    # 'rewards' and 'read-to-earn' go straight to the Rewards page; 'full'
    # does the search first (today's exact sequence).
    if only == "full":
        serp = self.search_and_results()
        log(f"search results BrowserActivity opened: {serp}")
        if not self.ensure_home():
            raise RuntimeError("home not reachable after search")
    return self.rewards_tail(iterations)
```

- [x] **Step 3: `InfraError`, `main()` argparse cutover + exit-code mapping.** Add near the top of the file (after imports): `import json` (not imported today) and `class InfraError(RuntimeError): pass`. Change `check_serial()`'s two `sys.exit("ERROR: …")` calls to `raise InfraError(...)`. Replace everything from `p.add_argument("--debug"…)` to `main()`'s end:

```python
p.add_argument("--profile", default="test", help="profile variant (test|prod_1|prod_2|...)")
p.add_argument("--only", default="full", choices=("full", "search", "rewards", "read-to-earn", "screenshot"))
p.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None,
               help="screenshot every action (default: on for profile=test)")
p.add_argument("--clear", action="store_true", help="pm clear (profile=test only)")
args = p.parse_args()
debug = args.debug if args.debug is not None else args.profile == "test"
flow = None
try:
    check_serial(args.serial)
    if args.clear and args.profile != "test":
        print("[FATAL] --clear only allowed for profile=test", file=sys.stderr)
        sys.exit(3)
    flow = BingMobileFlow(args.serial, debug, args.query, profile=args.profile)
    if args.clear:
        flow.clear_app_data(args.server)
    res = flow.run_only(args.only, args.iters)
    print(json.dumps({"profile": flow.profile, **res}, ensure_ascii=False))
    sys.exit(0)
except InfraError as e:
    print(f"[FATAL] infra: {e}", file=sys.stderr)
    sys.exit(3)
except (u2.exceptions.DeviceError, u2.exceptions.RPCError,
        subprocess.SubprocessError, RuntimeError) as e:
    if flow is not None:
        flow.shot("failed")
    print(f"[FATAL] {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(2)
```

Delete the old `--mode`/`--debug default True` args and the old `run()` body (keep `article_loop`, `candidate_articles`, `rewards_state`, `open_rewards`, `search_and_results`, dialog helpers untouched).

- [x] **Step 4: Guard test (cheap, no device):**

```bash
python src/bing_mobile_flow.py --serial none --profile prod_2 --clear; echo "rc=$?"
```

Expected: `rc=3` message `--clear only allowed for profile=test` (fails before any device I/O because the check precedes `BingMobileFlow()`).

- [x] **Step 5: Live smoke on `test`** (tunnel 15555 open; volume `test` = today's dev volume on 5555 — see Task 3 Step 1 for the one-time layout): `python src/bing_mobile_flow.py --serial 127.0.0.1:15555 --server piotr.wrotny@10.17.103.115 --profile test --only screenshot` → exit 0, `artifacts/test/screenshots/NN-screenshot.png` exists. Then `--only full` once; expect exit 0 and `state=wall` (fresh test) or `rte`+`articles_read`.

- [x] **Step 6: Docs + commit.** Update `AGENTS.md` § Mobile flow commands and `docs/bing-mobile-flow.md` artifact-path lines to `artifacts/<profile>/`. Commit: `feat: profile variants in mobile driver (--profile/--only, exit 0/2/3)`.

---

### Task 3: One-time server layout (variants tree + `test` volume)

**Files:**
- Server only: `~/redroid-variants/test/`, `~/redroid-variants/prod_2/`, `~/profile-snapshots/test.tar.gz`

**Interfaces:**
- Produces: volume dirs Task 4 mounts; `test.tar.gz` snapshot Task 5 copies locally.

- [x] **Step 1: Freeze current anonymous volume as `test`.** prod_2 currently lives in `~/redroid-data`; the untouched anonymous copy is `~/redroid-data-dev-loggedout-20260901`:

```bash
ssh piotr.wrotny@10.17.103.115 'set -e
mkdir -p ~/redroid-variants
mv ~/redroid-data-dev-loggedout-20260901 ~/redroid-variants/test
mv ~/redroid-data ~/redroid-variants/prod_2
docker stop -t 30 redroid
docker run --rm -v /home/piotr.wrotny:/host busybox sh -c "tar -C /host/redroid-variants/test -czf /host/profile-snapshots/test.tar.gz . && mkdir -p /host/redroid-variants/prod_2_ok && tar -C /host/redroid-variants/prod_2 -czf /host/profile-snapshots/prod_2.tar.gz ."
docker run --rm --volume ~/redroid-variants/prod_2:/data --publish 127.0.0.1:5555:5555 --publish 127.0.0.1:5037:5037 --detach --name redroid --privileged redroid/redroid:14.0.0-latest androidboot.redroid_gpu_mode=guest androidboot.redroid_net_ndns=2 androidboot.redroid_net_dns1=172.20.0.41 androidboot.redroid_net_dns2=172.20.0.42'
```

Note `docker stop -t 30 redroid` before `mv` — moving a live volume corrupts it. `rm -f redroid` is safe instead (container will be recreated by `bing.sh use`).

- [x] **Step 2: Layout verification** — `docker inspect -f '{{range .Mounts}}{{.Source}}{{end}}' redroid` prints `/home/piotr.wrotny/redroid-variants/prod_2`; `adb connect 127.0.0.1:5555 && adb -s 127.0.0.1:5555 shell getprop sys.boot_completed` = `1`.

- [x] **Step 3:** Server snapshots now: `prod_2.tar.gz` (re-pack canonical copy), `test.tar.gz`. Record paths in `AGENTS.md` § Mobile flow (layout paragraph). No git change (paths doc only).

---

### Task 4: `bing.sh` — server entrypoint (use/current/status/run/clear/snapshot)

**Files:**
- Create: `bing.sh` (repo root; runs on server from `~/rewards-farmer-main`)
- Test: `tests/test_bing.sh` (plain-bash asserts, no device)

**Interfaces:**
- Consumes: Task 1 `$PY` (`~/rewards-farmer-main/.venv/bin/python`), Task 2 driver CLI, Task 3 volume layout.
- Produces: cron/interactive contract:
  - `./bing.sh use <profile>` — recreate `redroid` on `~/redroid-variants/<profile>`, wait boot, print `active=<profile>`
  - `./bing.sh current` — print `active=<profile>` (from container mount source basename)
  - `./bing.sh status` — containers up? variants list, current, last log per profile
  - `./bing.sh run <full|search|rewards|read-to-earn|screenshot> [--profile P] [--iters N] [--debug|--no-debug]` — default profile: current active; maps driver exit 0/2/3 to own exit
  - `./bing.sh clear [--profile P]` — driver `--clear`; driver-side guard is the law
  - `./bing.sh snapshot <profile>` — freeze factory volume → `~/profile-snapshots/<profile>.tar.gz` (force-stop→sync→stop→tar→start)
- Locking: `flock /tmp/bing-5555.lock` for run/use/clear (5556 for snapshot). Log: `logs/bing-<profile>-<action>-$(date +%Y%m%d-%H%M%S).log` (driver stdout+stderr via `tee`).

- [x] **Step 1: Write failing guard tests** `tests/test_bing.sh`:

```bash
#!/usr/bin/env bash
set -u
fail=0
chk() { if [ "$2" != "$3" ]; then echo "FAIL $1: got '$2' want '$3'"; fail=1; else echo "ok $1"; fi }
# 1) no args -> usage exit 2
./bing.sh >/dev/null 2>&1; chk usage $? 2
# 2) unknown subcommand -> exit 2
./bing.sh bogus >/dev/null 2>&1; chk bogus $? 2
# 3) run without container reachable is infra error -> exit 3 (serial unreachable)
MOCK_ADB_FAIL=1 ./bing.sh run screenshot --profile test >/dev/null 2>&1; rc=$?
[ "$MOCK_ADB_FAIL" = 1 ] && [ "$rc" != 0 ] && echo "ok run-fails-nonzero" || chk run-fail "$rc" 3
# 4) clear refuses unknown profile before touching device
./bing.sh clear --profile no_such_profile >/dev/null 2>&1; chk clear-unknown $? 3
exit $fail
```

- [x] **Step 2: Run — expect all FAIL (file missing).** `bash tests/test_bing.sh`

- [x] **Step 3: Implement `bing.sh`:**

```bash
#!/usr/bin/env bash
# Bing mobile flows: one entrypoint for interactive use and server cron.
# Profiles are unpacked /data volumes: ~/redroid-variants/<profile>
set -u -o pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
IMG=redroid/redroid:14.0.0-latest
PROPS=(androidboot.redroid_gpu_mode=guest androidboot.redroid_net_ndns=2
       androidboot.redroid_net_dns1=172.20.0.41 androidboot.redroid_net_dns2=172.20.0.42)
PY="$ROOT/.venv/bin/python"
DRIVER="$ROOT/src/bing_mobile_flow.py"
VAR="$HOME/redroid-variants"; SNAP="$HOME/profile-snapshots"
ADB="${ADB:-adb}"; LOGS="$ROOT/logs"; mkdir -p "$LOGS"
serial() { [ "$1" = factory ] && echo 127.0.0.1:5556 || echo 127.0.0.1:5555; }
die() { echo "$*" >&2; exit "${2:-2}"; }

current() { docker inspect -f '{{range .Mounts}}{{.Source}}{{end}}' redroid 2>/dev/null | xargs -r basename; }

wait_boot() { local s; s="$(serial prod)"
  for _ in $(seq 1 40); do sleep 3
    [ "$($ADB -s "$s" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && return 0
  done; return 1; }

ensure_container() { local p="$1" v="$VAR/$p"
  [ -d "$v" ] || die "no variant $p (known: $(ls "$VAR" 2>/dev/null | tr '\n' ' '))" 3
  if [ "$(current)" = "$p" ] && docker inspect -f '{{.State.Running}}' redroid 2>/dev/null | grep -q true; then
    $ADB connect "$(serial prod)" >/dev/null 2>&1 || true; return 0
  fi
  docker rm -f redroid >/dev/null 2>&1 || true
  docker run --rm -d --name redroid --privileged -v "$v:/data" \
    -p 127.0.0.1:5555:5555 -p 127.0.0.1:5037:5037 "$IMG" "${PROPS[@]}" >/dev/null \
    || die "docker run failed" 3
  $ADB connect "$(serial prod)" >/dev/null 2>&1 || true
  wait_boot || die "boot timeout on variant $p" 3
}

cmd="${1:-}"; shift || true
case "$cmd" in
  use) p="${1:?profile}"; exec 9>/tmp/bing-5555.lock; flock 9
       [ -d "$VAR/$p" ] || die "no variant $p" 3
       ensure_container "$p"; echo "active=$p" ;;
  current) echo "active=$(current || echo none)" ;;
  status) docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'redroid' || echo "no redroid containers"
       echo "variants: $(ls "$VAR" 2>/dev/null | tr '\n' ' ')"
       echo "active: $(current || echo none)"
       ls -1t "$LOGS"/bing-*.log 2>/dev/null | head -5 ;;
  run) action="${1:?full|search|rewards|read-to-earn|screenshot}"; shift
       prof=""; iters=6; dbg=""
       while [ $# -gt 0 ]; do case "$1" in
         --profile) prof="$2"; shift 2;; --iters) iters="$2"; shift 2;;
         --debug|--no-debug) dbg="$1"; shift;; *) die "unknown flag $1" 2;; esac; done
       [ -n "$prof" ] || prof="$(current)" || die "no active profile; pass --profile" 3
       exec 9>/tmp/bing-5555.lock; flock 9
       ensure_container "$prof"
       ts="$(date +%Y%m%d-%H%M%S)"; log="$LOGS/bing-$prof-$action-$ts.log"
       args=("$DRIVER" --serial "$(serial prod)" --profile "$prof" --only "$action" --iters "$iters")
       [ -n "$dbg" ] && args+=("$dbg")
       "$PY" "${args[@]}" 2>&1 | tee "$log"; rc=${PIPESTATUS[0]}
       echo "log=$log rc=$rc" ;;
  clear) prof=""; while [ $# -gt 0 ]; do case "$1" in --profile) prof="$2"; shift 2;; *) die "unknown flag" 2;; esac; done
       [ -n "$prof" ] || prof="$(current)" || die "no active profile; pass --profile" 3
       exec 9>/tmp/bing-5555.lock; flock 9
       [ "$prof" = test ] || die "clear only allowed for profile test" 3
       ensure_container "$prof"
       "$PY" "$DRIVER" --serial "$(serial prod)" --profile "$prof" --only screenshot --clear; rc=$?
       echo "clear rc=$rc"; exit $rc ;;
  snapshot) p="${1:?profile name to save}"
       exec 9>/tmp/bing-5556.lock; flock 9
       docker ps --format '{{.Names}}' | grep -qx redroid-factory || die "factory not running" 3
       $ADB -s 127.0.0.1:5556 shell am force-stop com.microsoft.bing
       $ADB -s 127.0.0.1:5556 shell sync; sleep 3
       docker stop -t 30 redroid-factory >/dev/null
       docker run --rm -v "$HOME:/host" busybox sh -c "tar -C /host/profile-factory-data -czf /host/profile-snapshots/$p.tar.gz ." \
         || die "tar failed" 3
       docker start redroid-factory >/dev/null
       ls -la "$SNAP/$p.tar.gz" ;;
  *) sed -n '2,3p' "$0"; echo "usage: bing.sh use|current|status|run|clear|snapshot" >&2; exit 2 ;;
esac
```

- [x] **Step 4: Pass tests** (test 4 hits `die` before device; test 3 exercises `--only screenshot` path — MOCK hook: honor env `MOCK_ADB_FAIL=1` by `export ADB="sh -c 'exit 1' #"` in the test; if too fragile, drop to asserting nonzero rc only):

```bash
bash tests/test_bing.sh   # all ok, exit 0
```

- [x] **Step 5: Deploy to server + self-heal smoke.** After pushing: `ssh piotr.wrotny@10.17.103.115 'cd ~/rewards-farmer-main && git pull && chmod +x bing.sh'`. Cold start test — container on prod_2, `./bing.sh use test && ./bing.sh current` (expect `active=test`, boot ~30 s); `./bing.sh run screenshot --profile test` → `rc=0`, new log, screenshot under `artifacts/test/`; `./bing.sh use prod_2` returns.

- [x] **Step 6: Commit** `bing.sh`, `tests/test_bing.sh`, docs touch: `feat: bing.sh profile orchestration (use/run/clear/snapshot)`.

---

### Task 5: Factory tooling + registry + local snapshot copies

**Files:**
- Create: `scripts/factory.ps1`
- Create: `profiles/README.md` (registry table)
- Modify: `.gitignore` (ensure `profiles/*` + `!profiles/README.md` + `profile-snapshots/`)
- Modify: `AGENTS.md` (§ Mobile flow: bing.sh + factory usage)

**Interfaces:**
- Consumes: `bing.sh snapshot <name>` on server (Task 4).
- Produces: `factory.ps1 login <name>` (tunnel + scrcpy), `factory.ps1 save <name>` (snapshot + pull + reset factory to test baseline).

- [x] **Step 1: `scripts/factory.ps1`:**

```powershell
param([Parameter(Position=0)][string]$Cmd, [Parameter(Position=1)][string]$Name)
$Server = "piotr.wrotny@10.17.103.115"
$Adb = "bin/platform-tools/adb.exe"; $Scrcpy = "bin/scrcpy/scrcpy.exe"
function Ensure-Tunnel($local,$remote) {
  if (Get-NetTCPConnection -LocalPort $local -State Listen -EA SilentlyContinue) { return }
  Start-Process -WindowStyle Hidden ssh -ArgumentList "-N","-L","${local}:127.0.0.1:${remote}",$Server
  Start-Sleep 2 }
switch ($Cmd) {
  login {
    Ensure-Tunnel 15556 5556
    & $Adb connect 127.0.0.1:15556 | Out-Null
    # reset factory to clean baseline so each profile starts from a known state
    ssh $Server "adb -s 127.0.0.1:5556 shell pm clear com.microsoft.bing"
    Write-Host ">> scrcpy: log into the Microsoft account for profile '$Name' (agent never sees credentials)"
    & $Scrcpy -s 127.0.0.1:15556 --window-title "bing-factory login: $Name"
  }
  save {
    Ensure-Tunnel 15556 5556
    ssh $Server "cd ~/rewards-farmer-main && ./bing.sh snapshot $Name"
    New-Item -ItemType Directory -Force profile-snapshots | Out-Null
    scp "${Server}:profile-snapshots/$Name.tar.gz" "profile-snapshots/"
    ssh $Server "adb -s 127.0.0.1:5556 shell pm clear com.microsoft.bing"
    Write-Host "saved $Name (server snapshot + local copy); factory reset to baseline"
  }
  default { Write-Host "usage: factory.ps1 login|save <profile-name>"; exit 2 }
}
```

- [x] **Step 2: New variant from snapshot (server one-liner documented in AGENTS.md):**

```bash
ssh piotr.wrotny@10.17.103.115 'p=prod_3; mkdir -p ~/redroid-variants/$p && docker run --rm -v /home/piotr.wrotny:/host busybox tar -C /host/redroid-variants/$p -xzf /host/profile-snapshots/$p.tar.gz && cd ~/rewards-farmer-main && ./bing.sh use $p'
```

(`use` mounts it; `snapshot` never deletes prior snapshots — overwrite only same-name.)

- [x] **Step 3: `profiles/README.md` registry** — table: name / kind / account / snapshot server path / local copy / notes. Rows: `test`, `prod_2`. Rule line: snapshots are whole `/data` volumes; restore via Task-5-Step-2 one-liner. `.gitignore` additions if missing: `profile-snapshots/`.

- [x] **Step 4: `AGENTS.md`**: replace mobile section commands with `bing.sh` + `factory.ps1` contract (one screen). Commit: `feat: factory.ps1, profile registry, local snapshot copies`.

---

### Task 6: Cron wiring (KRON) + docs

**Files:**
- Create: `cron/README.md` (crontab lines to paste into the server scheduler)
- Modify: `AGENTS.md` (pointer)

**Interfaces:**
- Consumes: `bing.sh run <action> --profile P` contract.
- Produces: exact crontab snippet; the server scheduler (existing process) stays the executor — we only add its job lines.

- [x] **Step 1:** Write `cron/README.md`:

```cron
# /home/piotr.wrotny/rewards-farmer-main — bing mobile flows (server-local KRON)
0 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run full --profile prod_2 >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
30 7 * * * /home/piotr.wrotny/rewards-farmer-main/bing.sh run full --profile test   >> /home/piotr.wrotny/rewards-farmer-main/logs/cron.log 2>&1
```

Stagger profiles so flock never queues; times are placeholders until prod flow is mapped — mark as such.

- [x] **Step 2:** User pastes into their existing scheduler UI/crontab (agent MUST NOT install crontab without user go). Commit `docs: cron snippet for bing.sh`.

---

### Task 7: End-to-end acceptance (the whole point)

- [x] **Step 1:** `./bing.sh current` → correct active profile; `use test` → `run full --profile test --no-debug` → exit 0, terminal state `wall` in JSON; `use prod_2` → `run screenshot --profile prod_2` → exit 0 (no dialogs on warm signed-in app).
- [x] **Step 2:** Round-trip UI proof: `run screenshot` artifacts — `artifacts/test/.../NN-screenshot.png` shows anonymous home; same file for `prod_2` shows signed-in home (pixel-diff > threshold; eyeball).
- [x] **Step 3:** Kill container mid-nothing: `docker rm -f redroid && ./bing.sh run screenshot --profile test` → self-heal (recreate+boot+run) exit 0.
- [x] **Step 4:** `./bing.sh clear --profile prod_2` → exit 3 (prod data intact: `run rewards --profile prod_2` afterwards still signed in).
- [x] **Step 5:** Commit `test: profile-variant acceptance checks` + close-out notes in `AGENTS.md`.
