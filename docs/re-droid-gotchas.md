# ReDroid operational gotchas (evidence-backed)

Operational rules for the server containers (`redroid` 127.0.0.1:5555,
`redroid-factory` 127.0.0.1:5556). Every rule here was learned from a real incident on
this server; dates and evidence paths included so future-me can re-verify cheaply.

## 1. NEVER `chown -R` an Android `/data` volume — breaks keystore2 permanently

**Incident 2026-09-01.** After moving variant volumes (`docker stop` → `mv`), host-side
ownership looked "wrong" (uid `1000` vs my AD uid), so I ran
`docker run --rm -v ~:/host busybox chown -R 1000:1000 ~/redroid-variants`. Every boot
afterwards crash-looped: `User #0: state=BOOTING` forever despite `sys.boot_completed=1`,
`mCurrentFocus=null`, uiautomator2 dies with `LaunchUiAutomatorError`.

**Mechanism (logcat, container `redroid`):**

```
keystore2: [SQLITE3] 14: cannot open (persistent.sqlite)
keystore2: panicked at 'Failed to ...': unable to open database:
           file:/data/misc/keystore/persistent.sqlite
```

`/data/misc/keystore/*` belongs to Android uid **1017 (keystore)**. `chown -R 1000:1000`
took it away → keystore2 panics at every start → its binder service never stays
registered → `system_server` NPEs in
`KeyStore2.getService → SyntheticPasswordManager.unlockLskfBasedProtector →
UserController.finishUserBoot` (same shape as AOSP b/256734080, redroid-doc #143) →
init respawns zygote → infinite crash-loop. `sys.boot_completed=1` lies: it is set
before the crash path.

**Diagnosis sequence that found it** (keep this order):
1. `adb shell dumpsys activity users | grep "User #0"` → `BOOTING` = dead system_server,
   NOT a slow boot.
2. `adb logcat -b crash -d | grep -c FATAL` → >1 = crash-loop, restarts are pointless.
3. `adb logcat -d | grep keystore2` → SQLITE 14 / panic = ownership or DB corruption.

**Fix (verified, ~20 s):** restore the volume from the pre-`chown` snapshot tar —
`rm -rf variant && tar -xzf snapshot.tar.gz`. tar preserves Android uids 1:1, which is
exactly why snapshots are the recovery primitive. `prod_2` healed on first boot after
that (`state=RUNNING_UNLOCKED`, Bing signed-in intact).

**Rules:**
- Volume copy/move primitives: `cp -a` or tar (uid-preserving). NEVER `chown`, NEVER
  rsync without `-a`. Extraction as root preserves the original uids — verified: the
  restored `misc/keystore` stayed uid 1017 with zero post-processing.
- Host-side "wrong ownership" inside `/data` is EXPECTED and correct — Android is a
  multi-uid OS; Docker mounts need path access, not content ownership.
- Recovery from a broken volume: restore the snapshot tar (uid-perfect). A tar taken
  AFTER a chown is poisoned — treat it as unusable.
- `pm clear` (via adb, inside Android) is the only sanctioned data wipe for `test`.

## 2. A `tar` as root can silently SKIP content — verify archives, always

Same incident, second trap: `tar -C variant -czf test.tar.gz .` as root produced
`tar: empty archive` (exit status was masked by the shell chain). Root bypasses read
permission bits — the skip came from elsewhere (mid-move state), but the point stands:
**after every snapshot run `tar -tzf` and assert it lists known paths**
(e.g. `misc/keystore`, `system/packages.xml`) and size > 100 MB. A "successful" snapshot
that is empty converts a restore into a factory reset.

## 3. DNS boot props (netd) — unchanged rule

`androidboot.redroid_net_ndns=2 androidboot.redroid_net_dns1=172.20.0.41
androidboot.redroid_net_dns2=172.20.0.42` are required; without `ndns` netd ignores the
DNS props and every SERP is `ERR_NAME_NOT_RESOLVED` (verified on production runs).

## 4. Host adb server owns 5037 — do not publish container 5037

`docker run -p 127.0.0.1:5037:5037` fails with `address already in use` once the host
`adb server` is up (it binds 5037 eagerly). We never needed it: clients use
`adb connect 127.0.0.1:5555` (the device's own adbd). Publish only 5555/5556.

## 5. After recreating a container, adb caches the old endpoint

Following `docker rm -f` + re-run, existing `adb connect` states go stale
(`device offline` / `error: closed`). Fix: `adb disconnect <serial>` then
`adb connect <serial>`; worst case `adb kill-server`. Symptom seen 2026-09-01 after
each variant switch.

## 6. Boot health check that actually means something

`sys.boot_completed=1` is NOT sufficient (see #1). The only reliable ready check:

```bash
adb -s 127.0.0.1:5555 shell dumpsys activity users | grep -q "state=RUNNING_UNLOCKED"
```

`bing.sh` waits on this (user RUNNING) before declaring a variant ready.


## 7. NEW PROFILE SEEDING — permissions AND keystore both matter (2026-09-09)

Adding a variant (e.g. `domena3-prod`) on a server where `~/redroid-variants` is
owned by a DIFFERENT uid (here `1000 oczosa-adml` vs AD login `piotr.wrotny`):

1. `~/redroid-variants` itself is NOT writable by the login user → `mkdir` fails
   with plain EPERM (NOT a chown issue — dir is 755, uid 1000). `sudo` exists
   (AD group) but needs a password + PTY; scripted ssh CANNOT authenticate —
   the OPERATOR runs the seeding commands by hand.
2. **Seeding source = the FACTORY volume** (`~/redroid-variants/factory` —
   pristine, never pm-cleared, no logged-out flags). NOT `test` (carries
   pm-cleared/FRE state), NEVER a prod volume (clones a signed-in account —
   registry contamination). Alternative: factory snapshot tar (`sudo tar -xzf
   ~/profile-snapshots/<snap>.tar.gz -C ~/redroid-variants/<profile>`).
3. **Commands (uid-preserving, see #1):**
   ```bash
   sudo mkdir -p ~/redroid-variants/<profile>
   sudo chown <login-user> ~/redroid-variants/<profile>   # empty dir, pre-cp: safe
   sudo cp -a ~/redroid-variants/factory/. ~/redroid-variants/<profile>/
   ```
   NO chown inside the copied tree — cp -a preserves Android uids
   (keystore 1017 etc.). chown of the empty top dir BEFORE cp is safe.
4. Then `./bing.sh use <profile>` recreates the container on that volume;
   `./run_task.sh login_check <profile>` must return rc 2 (sign-in wall =
   logged-out-fresh) before the owner logs in via noVNC/scrcpy.
5. After login: `login_check` rc 0, registry row in `profiles/README.md`
   updated (account, date, verified tasks).

Anti-patterns (all hit 2026-09-09):
- scripted `ssh -t` sudo password entry — impossible, don't try;
- seeding from `test/` (pm-cleared state pollutes the prod profile);
- plain `cp` without `-a` (loses Android uids → keystore2 panic per #1);
- `chown` of anything inside a variant volume (see #1, breaks boot).

## 8. AD-login uid (63904568) inside `/data/system` = watchdog kill-loop (2026-10-27)

**Incident.** After a host-side file operation as the AD login user, both worker slots
booted into `User #0: state=BOOTING` forever; `system_server_watchdog` killed
`system_server` every ~102 s (`/data/system/dropbox/system_server_watchdog@*.txt.gz`).
Main-thread stack at kill: `JobSchedulerService.onBootPhase → CountDownLatch.await`
(the persistent-data latch never fires because `system_server`, uid 1000, cannot write
`/data/system/job` — it was `drwx------ 63904568:1000`). Same class of symptom as #1
but a DIFFERENT mechanism: keystore2 was healthy; the blocked service was JobScheduler.
Collateral log lines to look for: `DiscreteRegistry: Failed to create DiscreteRegistry
directory`, `Failed to chmod(/data/system/appops/discrete)`, `Failed to chmod
(/data/system/locksettings.db)`, `BatteryStatsHistory: Failed to create directory`.

**Scope of damage (2026-10-27 scan).** EVERY grid volume had 263–653 files under
`/data/system` owned by the AD uid (job, appops, dropbox, users/*.xml, package_cache,
locksettings.db, …), damage in `system_de/0`, `system_ce/0`, `misc_ce/0`, `/data/misc`
(keystore, apexdata/com.android.tethering/netstats, bootstat, gatekeeper, ethernet…),
and in app trees (on d5–d8 even `data/com.microsoft.bing` top-level, uid swapped to the
AD uid while gid 10087 stayed). Some damaged volumes still farmed fine for days —
damage only breaks boot when it hits a directory a boot-critical service must write
(mode 0700 + wrong uid = EACCES for the service).

**Second and third crash layer (same boot).** After unblocking JobScheduler the boot
advanced and revealed: (a) `system_server_crash` NPE in `FileRotator` ←
`NetworkStatsService.buildRecorder` — with `netstats_store_files_in_apexdata` the real
data dir is `/data/misc/apexdata/com.android.tethering/netstats` (was `63904568`),
NOT `/data/system/netstats`; (b) native `ipconfigstore` SIGABRT (`FORTIFY: fwrite:
null FILE*`) ← unwritable `/data/misc/ethernet`/apexdata ethernet. Both fixed by the
same uid repair. Lesson: iterate — restart, read the NEW dropbox entry, fix that
layer; the first watchdog stack is not the only damage.

**Diagnosis.** Root container mount, correct path (variant dir IS `/data`):
`docker run --rm -v ~/redroid-variants:/host:ro busybox find /host/<p>/system -user 63904568`.
Note the earlier false-negative trap: mounting whole `$HOME` and looking under
`redroid-variants/<p>/data/...` finds nothing when the layout is `redroid-variants/<p>/system`
(variant root = `/data`), and a host-uid scan misses `0700` subtrees entirely.
BusyBox `find` has NO `-uid` predicate — use `-user <uid>`.

**Fix (verified same day; slots reached `RUNNING_UNLOCKED`, no snapshot rollback).**
Three passes, all uid-targeted, groups preserved, then `docker restart <slot>`:
```bash
# 1) /data/system — all owned by system(1000); blind uid swap is safe here:
docker run --rm -v $HOME/redroid-variants:/host busybox sh -c \
  'find /host/<p>/system -user 63904568 -exec chown -h 1000 {} +'
# 2) system_de / system_ce / misc_ce — system-user trees: uid -> 1000
# 3) /data/misc — MIXED per-service uids (keystore 1017, bluetooth 1002, webview
#    shared_relro 1037, installd 0, …). NEVER blind-swap; take uid:gid per path from
#    a CLEAN reference volume (r_domena_* here): stat the same relpath, chown to
#    that uid:gid; fallback map only for paths missing in the ref.
docker restart <slot>   # then poll: dumpsys activity users | grep "User #0"
```
This is a RECORD-EXCEPTION to rule #1: it reverses accidental ownership corruption
back to Android's own uids, entry-by-entry from a scan — NOT a blanket `chown -R`.
NEVER extend it to app trees (`data/com.microsoft.bing` etc., per-app uids) unless the
gid is already intact and the uid is verified per volume (d5–d8 app damage was left
as-is: gid 10087 preserved + group-rwx modes kept those profiles functional — the
farm earned points on exactly these volumes 25–26.10). Full-volume recovery
primitive remains the uid-perfect snapshot tar (#1/#2).

**Prevention.** Do not run host-side file operations (`tar`, `cp`, editors, deploy
scripts) directly inside `~/redroid-variants/*` as the AD login. Stage outside the
variant tree; snapshot/restore via the docker+tar recipes in `profiles/README.md`.

## 9. Same incident also WIPED app data — sign-ins are the real casualty (2026-10-27)

**Finding.** Beyond the uid damage (#8), the host-side operation destroyed
`/data/data/com.microsoft.bing` trees: prod_1, prod_2, d4, d9, d10, d11 have EMPTY
 trees (3 entries: dirs only); d1/d2/d3 trees were deleted and rebuilt FRESH on first
boot after the incident (every file mtime = today, zero files older than 2 days);
d5-d8 trees were untouched (historical files + intact `.live.com` cookies). The
farmer's visible symptom: Rewards page renders the sign-in wall ("Hi, Welcome to
Microsoft Rewards!" / menu says "Tap to sign in"), tiles never populate, the driver
logs `daily_points=None->None` yet can still exit `DONE state=daily_done` — a FALSE
terminal. Treat any run with `daily_points=None` as unverified, never as success.

**Login check without booting (host, per volume):**
`docker run --rm -v ~/redroid-variants/<p>:/v:ro busybox sh -c "grep -ac live.com
/v/data/com.microsoft.bing/app_webview/Default/Cookies; find /v/data/com.microsoft.bing -type f | wc -l"`
— hit count >0 AND tree in the thousands = signed in; 0 hits AND small/empty tree =
lost account. Authoritative app uid per volume: `/v/system/packages.list` (field 2).

**Recovery.** Restore the whole volume from the uid-perfect snapshot tar
(recipe in `profiles/README.md`); Microsoft points live server-side, so an old device
snapshot loses nothing on the account — it only reverts device-local state. Keep the
damaged tree as `<p>.damaged-<date>` alongside until the restored profile is verified
`state=rte` (never `wall`). Volumes with intact logins (d5-d8) must NOT be restored.

**After any restore or first boot post-repair, verify BOTH gates before trusting a
daily run:** (1) network — `docker exec <slot> sh -c "ip route show table eth0"`
shows the default route and `dumpsys connectivity` reports `IS_VALIDATED` (Android
policy routing lives in table `eth0`, so `main`-table emptiness is NORMAL; ping is
ICMP-blocked — test TCP via `echo -e "HEAD / HTTP/1.0\n" | toybox nc -w 4 <ip> 80`);
(2) login — `./bing.sh run rewards --iters 0 --profile P` must print
`state=rte`/`state=done`, never `state=wall`.

**Screen sleep trap.** While idle-debugging (>30 min) the display sleeps
(`mWakefulness=Asleep`, `mCurrentFocus=null`, uiautomator `dump empty` — driver dies
with "never reached home"). Cron runs never hit it because they start right after a
container boot. Set `settings put global stay_awake 1` per volume (it persists in the
volume; re-check after restores — a restored snapshot reverts it).
