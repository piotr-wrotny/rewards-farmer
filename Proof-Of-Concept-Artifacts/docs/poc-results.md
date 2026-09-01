# PoC Results — ReDroid Bing Mobile

Data: 2026-09-01

## Host
Architecture: x86_64
OS: Ubuntu 26.04 LTS (kernel 7.0.0-22-generic)
Docker: 29.4.1
Spec: 8 vCPU / 15 GB RAM

## Android Runtime
ReDroid image: `redroid/redroid:14.0.0-latest` (amd64)
Android version: 14 (SDK 34)
ABI: x86_64 primary; arm64-v8a dostępne przez ARM translation

## Binder
Status: wymagał ręcznej konfiguracji (modprobe + binderfs mount + modules-load.d)
Evidence: `ls /dev/binderfs` → binder, hwbinder, vndbinder; po tym boot = OK.
Bez binderfs: boot-loop identyczny jak na Raspberry Pi (rasb) — system_server/surfaceflinger SIGSEGV.

## ADB
Status: ✅ działa (przez SSH tunnel 15555→127.0.0.1:5555)
Evidence: `adb devices` → `127.0.0.1:15555 device`; `sys.boot_completed=1`

## Display
scrcpy: NIE testowany w tej sesji (PoC korzystał z screencap + uiautomator dump)
Evidence: screenshoty w `screenshots/`

## Bing installation
Status: ✅
Package: `com.microsoft.bing`
Version: 34.0.440821002 (global, arm64-v8a)
Evidence: `pm list packages | grep bing` → `package:com.microsoft.bing`; install "Success"

## Bing launch
Status: ✅
Evidence: `MainSapphireActivity` focus po starcie; home screen z search box, Copilot, Rewards; screenshot `screenshots/03-bing-interaction.png`

## UI hierarchy
Status: ✅
Resource IDs available: YES (sa_search_box, sa_hp_*, sa_profile_button…)
Accessibility labels: YES (content-desc: Home, Search, Copilot, Rewards…)
WebView detected: YES (edge_web_view; treść web zablokowana brakiem DNS)
Evidence: `ui/window-fre3.xml` (home), `ui/window-search.xml`

## Programmatic actions (ADB)
Status: ✅ tap, swipe, text, ENTER, BACK, HOME — wszystkie wykonane w tej sesji
Evidence: przepływ search (tap→text→ENTER→BrowserActivity) w `ui/window-search.xml`, `ui/window-results.xml`

## Appium
Status: NIE testowany (poza zakresem tej sesji; baza UI jest gotowa — patrz ui-inspection.md)

## Persistence
Application persistence: ✅ (install przetrwał `docker restart`)
Application-data persistence: ✅ (FRE state zachowany — po restarcie Bing startuje do home, bez onboardingu)

## Limitations
1. **Brak DNS w kontenerze** — webview: `ERR_NAME_NOT_RESOLVED`; treści web nie ładują się. Host ma HTTP egress (bing.com→200), ICMP blokowany. Fix: redroid boot props `net.dns` (niezweryfikowane).
2. Bing wymaga APK **arm64-v8a** (global); armeabi-v7a-only nie działa (DeprecatedAbiDialog).
3. scrcpy nieweryfikowany (display przez screencap tylko).
4. GMS nieobecne — Bing działa bez, ale flows wymagające logowania MS niesprawdzone.

## Recommendation

**CONDITIONAL GO**

Infrastruktura (ReDroid + ADB + UI automation + persistence) = PASS.
Bing compatibility = PASS (global arm64 build uruchamia się, jest po angielsku, automatable).
Blokada: DNS w kontenerze (web content) — fix identyfikowany, nieszwedzony.
