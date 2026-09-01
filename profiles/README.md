# Profile registry

Named credential variants for the Bing mobile flow. A profile = an unpacked Android
`/data` volume at `~/redroid-variants/<name>` on the server + a snapshot
`~/profile-snapshots/<name>.tar.gz` (whole volume; uid-perfect; **server-only — never
commit profile data**, see `.gitignore`). Switch: `./bing.sh use <name>`. Create:
`scripts/factory.ps1 login <name>` (scrcpy, user logs in — agent never sees
credentials) then `factory.ps1 save <name>`. New variant from snapshot:

```bash
ssh piotr.wrotny@10.17.103.115 'p=<name>; mkdir -p ~/redroid-variants/$p && docker run --rm -v /home/piotr.wrotny:/host busybox sh -c "mkdir -p /host/redroid-variants/$p && tar -C /host/redroid-variants/$p -xzf /host/profile-snapshots/$p.tar.gz" && cd ~/rewards-farmer-main && ./bing.sh use $p'
```

| name | kind | account | snapshot | status |
|------|------|---------|----------|--------|
| test | anonymous | — | `test.tar.gz` | rebuilt 2026-09-01 from factory baseline (`pm clear` + `cp -a`); `bing.sh clear` allowed |
| prod_2 | signed-in | 616piotrek@gmail.com | `prod_2.tar.gz` | VERIFIED working 2026-09-01 (home/rewards/tab-switch, `docs/bing-mobile-flow.md` § WORKING STATE) |
| prod_1 | signed-in | TBD | — | to be created via factory after prod_2 e2e port |

Snapshot hygiene: verify every snapshot with `tar -tzf <f> | grep system/packages.xml`
and size > 100 MB before trusting it (`docs/re-droid-gotchas.md` #2). NEVER `chown` a
volume (#1).
