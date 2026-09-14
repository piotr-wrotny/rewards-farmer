# Profile accounts (display name + email)

Extracted 2026-09-14 from `artifacts/<profile>/ui/*profile-menu*.xml` dumps — the
profile-menu header renders the Microsoft account display name with the e-mail in
the node directly below (`sa_profile_account_info`). NO login needed; re-extract
with the snippet at the bottom of this file.

| profile | e-mail | account display name | source dump |
|---------|--------|----------------------|-------------|
| domena1-prod | domena-1@agregat-streszczen.pl | Marek Michałowski | 47-profile-menu.xml |
| domena2-prod | domena-2@agregat-streszczen.pl | Michael Kwasniewski | 49-profile-menu.xml |
| domena3-prod | domena-3@agregat-streszczen.pl | Brown E Lsa | 42-profile-menu.xml |
| domena4-prod | domena-4@agregat-streszczen.pl | Kamil Kraskivos | 23-profile-menu.xml |
| domena5-prod | domena-5@agregat-streszczen.pl | Wñy Terros | 03-profile-menu.xml |
| domena6-prod | domena-6@agregat-streszczen.pl | Yest Podry | 13-profile-menu.xml |
| domena7-prod | domena-7@agregat-streszczen.pl | Kris Karosky | 50-profile-menu.xml |
| domena8-prod | domena-8@agregat-streszczen.pl | Uzo Kerry | 03-profile-menu.xml (re-provisioned 2026-09-14) |
| domena9-prod | domena-9@agregat-streszczen.pl | Mario Kuszyński | 03-profile-menu.xml (2026-09-14) |
| domena10-prod | domena-10@agregat-streszczen.pl | Kamil Kużyński | 03-profile-menu.xml (2026-09-14) |
| domena11-prod | domena-11@agregat-streszczen.pl | Evelin Krosi | 03-profile-menu.xml (2026-09-14) |
| prod_1 | piotrwro01@gmail.com | Piotr Wrotny | 42-profile-menu.xml |
| prod_2 | 616piotrek@gmail.com | Piotr W | 03-profile-menu.xml (name truncated in dump) |
| test | — | — (never signed in) | |

Caveats:

- Display names are whatever was typed at account creation — several domena
  accounts have deliberately messy values (`Wñy Terros`, `Brown E Lsa`).
- **Authoritative identity check remains the e-mail text** (see `profiles/README.md`
  status rows: names confirmed "dumpem"). domena12-prod ODPUSZCZONY 2026-09-14
  (login never performed; volume still on server, see registry row).
- These are the mobile (Bing app) identities. The web Edge profiles map to the
  same Microsoft accounts, so no separate table.

## Re-extract (on the server)

```bash
python3 - << 'PY'
import glob, os, re
base = os.path.expanduser("~/rewards-farmer-main/artifacts")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
for prof in sorted(os.listdir(base)):
    dumps = glob.glob(os.path.join(base, prof, "ui", "*profile-menu*.xml"))
    if not dumps:
        continue
    f = max(dumps, key=os.path.getmtime)
    texts = re.findall(r'text="([^"]+)"', open(f, encoding="utf-8", errors="replace").read())
    email = next((t for t in texts if EMAIL.fullmatch(t)), None)
    name = texts[texts.index(email) - 1] if email and email in texts and texts.index(email) else None
    print(prof, "|", email, "|", name)
PY
```
