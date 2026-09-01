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
DNS props and every SERP is `ERR_NAME_NOT_RESOLVED` (see
Proof-Of-Concept-Artifacts/docs/runtime-info.md).

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
