# Dodawanie nowego profilu produkcyjnego (mobile, ReDroid) — procedura krok po kroku

> Wypracowane 2026-09-09 przy domena3-prod. Uzupełnia `docs/re-droid-gotchas.md`
> §7 (zasady) i `docs/profile-login-procedure.md` (web). Ta notatka: DOKŁNE
> komendy i podział ról (agent ↔ operator).

## Role
- **Operator (Ty)** — jedyne zadania: komendy sudo na serwerze + ręczny login
  w Bing przez scrcpy. Nic więcej.
- **Agent** — wszystko inne: seed weryfikacja, kontener, snapshoty, weryfikacja
  loginu, mapowanie, przepływ.

## Komunikacja agent ↔ operator
Agent **podaje komendy do wklejenia** i czeka na „wykonane". NIE próbuje sam
sudo przez ssh (wymaga hasła + PTY — niemożliwe w skrypcie). Przy logowaniu:
agent **nie dotyka urządzenia** (żadnych adb/flow) dopóki operator nie napisze
„zalogowane" — współbieżne tapnięcia psują oba procesy.

## Procedura

### 1. Seed wolumenu (OPERATOR, na serwerze)
Źródło ZAWSZE factory volume (nie `test`! nie prod!):
```bash
sudo mkdir -p ~/redroid-variants/<profil>
sudo chown <login-user> ~/redroid-variants/<profil>     # pusty katalog: bezpieczne
sudo cp -a ~/redroid-variants/factory/. ~/redroid-variants/<profil>/
```
(`cp -a` zachowuje uid-y Androida — keystore 1017 itd. NIGDY chown wewnątrz.)

### 2. Start kontenera (AGENT)
```bash
cd ~/rewards-farmer-main && ./bing.sh use <profil>   # port 5555
./bing.sh current                                     # active=<profil>
./bing.sh status                                      # user: RUNNING
```

### 3. Login (OPERATOR)
Agent otwiera Bing + menu profilu (driver, np. `--only screenshot` +
tap `sa_profile_button`). Operator:
```
# terminal 1 (tunel):
ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
# terminal 2 (okno ekranu):
bin\platform-tools\adb.exe connect 127.0.0.1:15555
bin\scrcpy\scrcpy.exe -s 127.0.0.1:15555
```
KLUCZOWE: najpierw `adb connect`, potem scrcpy — inaczej scrcpy nie widzi
urządzenia. W oknie scrcpy operator loguje się na konto (menu profilu Bing
otwarte przez agenta przed przekazaniem).
**Po zalogowaniu operator ZAMYKA tunel** — agent dalej pracuje serwerowo
(serial 127.0.0.1:5555), tunel niepotrzebny.

### 4. Weryfikacja loginu (AGENT — tekstowo, nie screenshotem)
```bash
adb -s 127.0.0.1:5555 shell uiautomator dump /sdcard/ui.xml
adb -s 127.0.0.1:5555 shell cat /sdcard/ui.xml | grep -o 'domena-3@[^"]*'
# obecny email + 'Total points' + brak 'Sign in' = logged in.
```
(lub `./bing.sh run rewards --profile <p> --iters 1 --no-debug`, rc 0, bez wall)

### 5. SNAPSHOT BEZPIECZNOŚCI (AGENT) — ZANIM cokolwiek ruszy flow
```bash
cd ~/rewards-farmer-main
docker stop redroid
docker run --rm -v $HOME:/host busybox sh -c \
  'tar -C /host/redroid-variants/<profil> -czf /host/profile-snapshots/<profil>-signedin.tar.gz .'
tar -tzf ~/profile-snapshots/<profil>-signedin.tar.gz | grep -c .   # >1000
docker start redroid
```
UWAGA: `./bing.sh snapshot <nazwa>` mrozi FACTORY wolumen — NIE ten profil.
Do backupu świeżo zalogowanego profilu: powyższy ręczny tar (kontener stop!).

### 6. Rejestr (AGENT)
Update `profiles/README.md`: konto, data, snapshot, zweryfikowane zadania.

## Lekcje z domena3-prod (2026-09-09)
- ~/redroid-variants może należeć do innego uid (tu 1000 `oczosa-adml`) —
  mkdir bez sudo padnie EPERM; to NIE jest problem chown wolumenu.
- `flock /tmp/bing-5555.lock` trzymają martwe joby — sprawdzaj
  `fuser /tmp/bing-5555.lock` + `ps -fp <pid>` przed kill (łatwo ubić własne
  sondy); lock-free warunkiem jakiejkolwiek pracy na 5555.
- Po `docker stop/start redroid` adb wymaga reconnect (gotchas #5).
