# Proof of Concept — ReDroid Bing Mobile (transferable artifacts)

Ten folder jest samowystarczalnym pakietem do przeniesienia w inne repozytorium.
Zawiera wszystko, czego potrzebujesz, żeby odtworzyć środowisko i przemapować
przepływy UI z Android Emulatora na ReDroid.

## Struktura

```
Proof-Of-Concept-Artifacts/
├── README.md                        ← ten plik
├── docs/
│   ├── runtime-info.md              ← host, obraz, APK, tuner network
│   ├── bing-compatibility.md        ← rozróżnienie CN vs global build
│   ├── ui-inspection.md             ← co Bing eksponuje w UI hierarchy
│   └── poc-results.md               ← pełny decision log PoC
├── scripts/                         ← gotowe wrappery ADB (Windows)
│   ├── connect.ps1
│   ├── screenshot.ps1
│   ├── ui-dump.ps1
│   ├── tap.ps1
│   ├── text.ps1
│   ├── back.ps1
│   └── bing-flow-example.ps1        ← referencyjny przepływ end-to-end
├── ui/                              ← surowe XML dump (UI hierarchy)
└── screenshots/                     ← dowody wizualne (android home, FRE, Bing home, search)
```

## Szybki start (na docelowym hoście x86_64 z Dockerem)

```bash
# 1. Binder (wymaga sudo, tylko raz)
sudo modprobe binder_linux devices=binder,hwbinder,vndbinder
sudo mkdir -p /dev/binderfs && sudo mount -t binder binder /dev/binderfs
echo binder_linux | sudo tee /etc/modules-load.d/binder.conf

# 2. ReDroid
docker run -d --name redroid --privileged -p 127.0.0.1:5555:5555 \
  -v ~/redroid-data:/data redroid/redroid:14.0.0-latest \
  androidboot.redroid_gpu_mode=guest \
  androidboot.redroid_net_ndns=2 \
  androidboot.redroid_net_dns1=172.20.0.41 \
  androidboot.redroid_net_dns2=172.20.0.42

# 3. ADB przez tunel SSH (z maszyny developerskiej)
ssh -N -L 15555:127.0.0.1:5555 user@host &
adb connect 127.0.0.1:15555

# 4. Locale en-US (żeby Bing był po angielsku)
adb -s 127.0.0.1:15555 shell "setprop persist.sys.locale en-US; setprop ctl.restart zygote"
```

## Bing — kluczowe fakty do przeniesienia przepływów

- **Package:** `com.microsoft.bing`
- **Wersja użyta w PoC:** `34.0.440821002` (global, arm64-v8a, działa na ReDroid x86_64 dzięki ARM translation w obrazie `redroid/redroid:14.0.0-latest`)
- **Launcher activity:** `com.microsoft.sapphire.app.main.SapphireMainActivity`
- **Główny ekran:** `com.microsoft.sapphire.app.main.MainSapphireActivity`
- **FRE (first-run):** `com.microsoft.sapphire.features.firstrun.BingAppGlobalFreActivity` — trzeba kliknąć "Maybe later", żeby dojść do home
- **Wyszukiwanie:** tap na `sa_search_box` → wpisz tekst → `KEYCODE_ENTER` → otwiera `com.microsoft.sapphire.app.browser.BrowserActivity`

## Semantyczne selektory (resource-id), które działały w UI dump

Home screen (MainSapphireActivity):
- `com.microsoft.bing:id/sa_search_box` — pole wyszukiwania
- `com.microsoft.bing:id/sa_hp_header_search_box` — nagłówek
- `com.microsoft.bing:id/sa_hp_feed_container` — feed
- `com.microsoft.bing:id/sa_profile_button` — profil

Content-desc (dostępne dla UIAutomator/Appium):
- `Home`, `Search`, `Copilot`, `Rewards`, `Profile`, `Tabs`, `Apps`,
  `Camera`, `Camera search`, `Image Creator`, `Trending`,
  `Voice search`, `Wallpapers`

## Mapowanie Android Emulator → ReDroid

Twoje istniejące przepływy z Android Emulatora powinny działać 1:1, pod warunkiem że:
- korzystają z semantic selectors (resource-id / content-desc / accessibility id), a nie absolutnych współrzędnych;
- nie polegają na `Play Store` (nie ma GMS w ReDroid — Bing instalowany z APK);
- nie testują funkcji zależnych od `Play Integrity` (Bing nie wymagał, uruchomił się bez problemu).

Współrzędne ekranu (720x1280 w tym PoC) mogą się różnić od emulatora —
**używaj selektorów, nie współrzędnych**.

## Ocena gotowości do przemapowania przepływów

**TAK — jesteśmy w stanie poruszać się po Bing:**
- uruchamianie, przejście FRE, home screen — automatycznie ✓
- wpisanie zapytania w search box ✓ (tekst widoczny w UI dump)
- nawigacja do wyników (BrowserActivity) ✓
- UI dump z bogatym zestawem resource-id i content-desc ✓
- screenshoty ✓
- persistence (restart kontenera nie traci stanu apki) ✓

**Rozwiązane (2026-09-01):** DNS przez `androidboot.redroid_net_ndns=2` + `dns1/dns2`
(same dns1/dns2 bez `ndns` netd ignoruje). Kontener z siecią: SERP ładuje się w webview.
Szczegóły: `docs/runtime-info.md` § Naprawa DNS.
