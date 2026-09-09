# Profile login procedure (web + mobile)

End-to-end run for adding a new credential profile — the procedure executed for
`domena1-prod` on 2026-09-09 (web `login_check` signed_in VERIFIED). One profile name
= one Microsoft account, provisioned **separately** in each flow; the agent never sees
credentials, the user types them into the GUI. Registry: `profiles/README.md`.

Both logins are interactive and can run in parallel; everything before and after them
is scripted. `<p>` below = profile name (e.g. `domena1-prod`).

## 0. Prep (agent)

- Repo state pushed/deployed (server dir is NOT a git checkout — deploy with:
  `git archive HEAD <files> | ssh piotr.wrotny@10.17.103.115 'tar -x -C ~/rewards-farmer-main'`).
- Server reachable, `redroid` + `redroid-factory` containers up (`./bing.sh status`);
  factory exposes adb on 127.0.0.1:5556 (tunneled by factory.ps1 to local 15556).
- Ask the user WHICH Microsoft account the profile is (registry wants the email).

## 1. Mobile login (user types into scrcpy)

1. Agent (Windows dev machine, repo root):
   `powershell -ExecutionPolicy Bypass -File scripts/factory.ps1 login <p>`
   — clears the factory app data (`pm clear`), opens scrcpy "bing-factory login: <p>".
2. User: in the Bing app sign in (profile tab shows the account), handle any prompts,
   then close the scrcpy window (Ctrl+C / X — normal).
3. Agent: `powershell -ExecutionPolicy Bypass -File scripts/factory.ps1 save <p>`
   — gates on a UI login probe (`bing_mobile_flow --only rewards --iters 0`; `wall` or
   rc!=0 aborts, snapshot NEVER taken on a dud), then `bing.sh snapshot <p>`
   (force-stop → sync → docker stop → tar → restart) and copies the snapshot locally;
   factory volume is reset to baseline for the next profile.
4. Agent — create the variant from the snapshot (root-owned dirs, extract via docker):
   ```bash
   ssh piotr.wrotny@10.17.103.115 'p=<p>; docker run --rm -v /home/piotr.wrotny:/host busybox sh -c "mkdir -p /host/redroid-variants/$p && tar -C /host/redroid-variants/$p -xzf /host/profile-snapshots/$p.tar.gz"'
   ```
5. Verify signed-in on the variant: `ssh ... 'cd ~/rewards-farmer-main && ./bing.sh run rewards --profile <p> --iters 0 --no-debug'`
   → rc 0 and no `state=wall`. Snapshot hygiene rules: `docs/re-droid-gotchas.md` #1/#2.

Notes from 2026-09-09: scrcpy `audio/opus NAME_NOT_FOUND` on redroid is cosmetic
(no audio HAL) — video+input work. If the app bounces to the launcher right after a
session, the driver's home ready-check (back-recovery loop) handles it; don't trust a
"Microsoft Rewards missing" abort until a fresh launch confirms it — profile-menu taps
can fire before the menu layer renders.

> **2026-09-09 (d3):** nowa, prostsza ścieżka variant-direct login (krok 1b niżej)
> + pełna procedura dodawania profilu z podziałem ról agent/operator:
> `docs/profile-provisioning-mobile.md` (definiuje właściwy flow — ten plik
> zostaje jako referencja ścieżki fabrycznej).

### 1b. Variant-direct login (d3 path, 2026-09-09) — alternative to §1

Used when the variant volume already exists (seeded from factory per
`docs/re-droid-gotchas.md` §7) and login happens DIRECTLY on the variant, not on
factory. Trade-off: skips factory.ps1 save-gate, so the agent MUST take a manual
safety snapshot right after login.

1. Agent: seed volume + `./bing.sh use <p>` (port 5555), open Bing, tap the
   profile button (`bing_mobile_flow --only screenshot` opens home; one
   `sa_profile_button` tap opens the sign-in surface).
2. Operator — two terminals:
   ```
   # T1 (tunnel, keep open during login):
   ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
   # T2 (device window; adb connect FIRST or scrcpy sees nothing):
   bin\platform-tools\adb.exe connect 127.0.0.1:15555
   bin\scrcpy\scrcpy.exe -s 127.0.0.1:15555
   ```
3. Operator signs in, then says done AND CLOSES THE TUNNEL — the agent keeps
   working server-side (serial 127.0.0.1:5555), no tunnel needed after login.
4. AGENT IS HANDS-OFF during login: no adb/flow calls on 15555 (concurrent taps
   corrupt both the sign-in and the flow). Verify lock-free first:
   `flock -n /tmp/bing-5555.lock true` (stale probe jobs hold it — `fuser` + `ps`).
5. Verify TEXTUALLY (not screenshots):
   `adb -s 127.0.0.1:5555 shell uiautomator dump` → email present + `Total points`,
   no `Sign in`. (or `./bing.sh run rewards --profile <p> --iters 1`, rc 0, no wall)
6. **Safety snapshot (variant-direct, NOT bing.sh snapshot — that freezes
   factory):**
   ```bash
   docker stop redroid
   docker run --rm -v $HOME:/host busybox sh -c \
     'tar -C /host/redroid-variants/<p> -czf /host/profile-snapshots/<p>-signedin.tar.gz .'
   tar -tzf ~/profile-snapshots/<p>-signedin.tar.gz | grep -c .   # >1000
   docker start redroid
   ```

## 2. Web login (user types into noVNC)

1. Agent (server): `cd ~/rewards-farmer-main && ./web_login.sh <p>`
   — creates `edge-profiles/<p>` (fresh user-data-dir), copies `visual-search-asset.jpg`
   into it, starts the login-mode container (`START_EDGE_ON_BOOT=1`, noVNC on 6080),
   refuses if any automation container is up (one volume, one Chrome).
2. Tunnel for the user: `ssh -N -L 6080:127.0.0.1:6080 piotr.wrotny@10.17.103.115`
   — open `http://localhost:6080/vnc.html` → Connect.
3. User: inside that Edge, sign in to Microsoft at **bing.com AND rewards.bing.com**
   (both), accept the EU consent banner if shown, confirm the Rewards dashboard shows
   points, then say done.
4. Agent: `docker rm -f rewards-web-login`, then verify:
   `./run_task.sh login_check <p>` → log must end `state=signed_in`, rc 0
   (rc 2 = wall → redo §2.3). Probe = earn-tab renders / no sign-in redirect.

## 3. Register + cron (agent)

- `profiles/README.md`: one row per profile (account email, mobile snapshot, status).
- Cron (`cron/README.md` is the ledger; install by editing `crontab -e` ON the server):
  - mobile: `0 <H> * * * ~/rewards-farmer-main/bing.sh run read-to-earn --profile <p> --iters 60 >> ~/rewards-farmer-main/logs/cron.log 2>&1`
    — stagger ≥ 1 h from other bing lines (flock `/tmp/bing-5555.lock` serialises, but
    stagger keeps runtimes predictable; RTE ≈ 6 min/10 articles).
  - web: `<M> <H> * * * ~/rewards-farmer-main/run_daily.sh <p> >> ~/rewards-farmer-main/logs/cron.log 2>&1`
    — NEVER overlapping another web run (the flow kills all image containers first);
    existing web cron is 01:30 `default`, so named profiles go later (e.g. 03:30).
- Back up crontab before touching it: `crontab -l > ~/crontab.backup-$(date +%Y%m%d)`.

## Exit codes / verification matrix

| check | command | pass |
|-------|---------|------|
| mobile signed-in | `bing.sh run rewards --profile <p> --iters 0` | rc 0, no `state=wall` |
| web signed-in | `./run_task.sh login_check <p>` | rc 0, `state=signed_in` |
| snapshot intact | `tar -tzf <f> \| grep system/packages.xml` (plain grep!) | match, > 100 MB |
