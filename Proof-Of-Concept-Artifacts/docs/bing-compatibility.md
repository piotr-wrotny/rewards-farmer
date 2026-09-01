# Bing Compatibility — CN vs Global Build

## Jak rozpoznać chiński build (CN) bez instalacji

1. **versionCode zaczyna się od `211`** (np. `2110003561`) = CN. Globalne mają inny pattern (np. `440821002`).
2. **`unzip -p <apk> AndroidManifest.xml | grep -c 'cn.bing.com'`** — CN: >0; global: 0.
3. **Launch activity** (`aapt`/`pm dump`):
   - CN: `com.microsoft.sapphire.features.firstrun.ChinaAppFreActivity` (umowa 用户协议及隐私保护)
   - Global: standardowy FRE `BingAppGlobalFreActivity`, potem `MainSapphireActivity`
4. CN build zawsze po chińsku — zmiana locale urządzenia NIE pomaga (zasoby w buildzie).

## Co się zmieściło na ReDroid x86_64

| Wersja | ABI w APK | Wynik |
|---|---|---|
| 32.6.2110003561 (CN) | arm64-v8a | Instaluje się, działa, ale po chińsku — **odrzucony** |
| 34.0.440821001 (global) | armeabi-v7a (32-bit) | DeprecatedAbiDialog "not compatible" — **nie działa** |
| **34.0.440821002 (global, APKPure)** | **arm64-v8a** | **Działa** — FRE po angielsku, home OK |

Wniosek: ReDroid 14 x86_64 (ten obraz) ma ARM translation dla **arm64-v8a**, ale nie dla armeabi-v7a. Wybieraj APK z `lib/arm64-v8a/`.

## Zachowanie na ReDroid

- Instalacja bez GMS: OK (`adb install`), Bing nie wymagał Play Services do startu.
- FRE (first-run): permission dialog (notifications) → "Try AI tools" ekran → "Maybe later" → home.
- Bez logowania: home screen w pełni funkcjonalny (search box, Copilot, Rewards widoczne).
- Persistence: instalacja + FRE state przeżywają `docker restart` (wolumen `/data`).
