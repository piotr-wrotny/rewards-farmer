# Ręczne tworzenie nowych profili na serwerze (operator-only)

Ten runbook jest dla operatora, który chce samodzielnie wygenerować nowe profile
(`domena12+`) bez udziału agenta przy samym procesie logowania.

Zakres:

- tworzenie **mobile variants** (`~/redroid-variants/<profil>`)
- tworzenie **web profili** (`~/rewards-farmer-main/edge-profiles/<profil>`)
- minimalna weryfikacja, że profil jest gotowy do późniejszego spięcia w cron

> Uwaga: profile zawierają dane kont. Nie kopiuj ich do repo i nie wrzucaj do git.

---

## 1) Przygotowanie nazw i mapy kont

Przygotuj listę nazw, np.:

`domena12-prod ... domena23-prod`

I osobną mapę: `profil -> email konta Microsoft`.

---

## 2) Mobile: utworzenie wariantu z czystego seeda

Na serwerze (operator, konto `piotr.wrotny`):

```bash
for p in domena12-prod domena13-prod domena14-prod domena15-prod domena16-prod domena17-prod domena18-prod domena19-prod domena20-prod domena21-prod domena22-prod domena23-prod; do
  sudo mkdir -p ~/redroid-variants/$p
  sudo chown -R 1000:1000 ~/redroid-variants/$p
  sudo cp -a ~/redroid-variants/test/. ~/redroid-variants/$p/
done
```

Potem dla KAŻDEGO profilu osobno:

```bash
cd ~/rewards-farmer-main
./bing.sh use <profil>
./bing.sh status
```

Status musi pokazać działający kontener i użytkownika Android `RUNNING`.

---

## 3) Mobile: ręczne logowanie konta (scrcpy)

1. Tunnel:
```bash
ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
```
2. Lokalnie:
```powershell
bin\platform-tools\adb.exe connect 127.0.0.1:15555
bin\scrcpy\scrcpy.exe -s 127.0.0.1:15555
```
3. Zaloguj konto Microsoft w Bing.
4. Zamknij scrcpy i tunnel.

Weryfikacja po loginie:

```bash
cd ~/rewards-farmer-main
./bing.sh run rewards --profile <profil> --iters 0 --no-debug
```

Oczekiwane: `rc=0`, bez `state=wall`.

---

## 4) Mobile: snapshot bezpieczeństwa po loginie

Po każdym poprawnym loginie wykonaj backup:

```bash
docker stop redroid
docker run --rm -v $HOME:/host busybox sh -c \
  'tar -C /host/redroid-variants/<profil> -czf /host/profile-snapshots/<profil>-signedin.tar.gz .'
docker start redroid
```

Kontrola archiwum:

```bash
tar -tzf ~/profile-snapshots/<profil>-signedin.tar.gz | grep system/packages.xml >/dev/null
ls -lh ~/profile-snapshots/<profil>-signedin.tar.gz
```

---

## 5) Web: utworzenie profilu i ręczne logowanie

Dla każdego profilu:

```bash
cd ~/rewards-farmer-main
./web_login.sh <profil>
```

To utworzy `edge-profiles/<profil>` i podniesie noVNC (6080). Następnie:

1. Tunnel:
```bash
ssh -N -L 6080:127.0.0.1:6080 piotr.wrotny@10.17.103.115
```
2. Otwórz `http://localhost:6080/vnc.html`
3. Zaloguj konto Microsoft w Edge (bing + rewards.bing.com)
4. Zamknij kontener logowania:
```bash
docker rm -f rewards-web-login-<profil>
```

Weryfikacja:

```bash
cd ~/rewards-farmer-main
./run_task.sh login_check <profil>
```

Oczekiwane: `rc=0`, `state=signed_in`.

---

## 6) Rejestr profili (co zapisać, żeby później spiąć cron)

Dla każdego nowego profilu zapisz:

- nazwa profilu
- email konta
- snapshot mobile (`<profil>-signedin.tar.gz`)
- wynik `bing.sh run rewards --iters 0` (rc + state)
- wynik `run_task.sh login_check` (rc + state)

To wystarcza, żeby potem bezpiecznie dodać profile do harmonogramu.

---

## 7) Najczęstsze pułapki

- Nie używaj `bing.sh snapshot` dla prod profili — to snapshot factory, nie aktualnego wariantu.
- Nie rób `chown` wewnątrz już zalogowanych wolumenów profili.
- Nie uruchamiaj dwóch loginów web równolegle.
- Dla mobile: jeden profil naraz na porcie 5555 podczas logowania.
