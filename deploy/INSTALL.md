# Read to Earn (Bing mobile) — pakiet wdrożeniowy dla Windows 10 VM (172.25.19.51)

## Co robi ten przepływ
Automatyzuje (jak użytkownik, przez UI) aplikację Bing na emulatorze Android:
1. Bing → ikona **Apps** (prawy dolny róg) → **Rewards**
2. Kliknięcie aktywnej karty **Read to earn** (`Read to earn, , N out of 30 points earned`)
3. Otwiera się lista artykułów; czyta do 5 unikatowych artykułów na sesję
   (pomija **filmy** — plakietka czasu `m:ss` — i **reklamy** — `Ad` w opisie karty)
4. Wraca do ścieżki Rewards → Read to earn i powtarza, aż klik w Read to earn
   **przestanie otwierać listę artykułów** (stan końcowy: tekst
   `Read to earn, 30 points earned` bez klikalnej karty)
5. Stan końcowy = zamknięcie **wszystkich kart** przeglądarki Bing (zero otwartych kart)

## Pliki w pakiecie
| plik | rola |
|---|---|
| `read_to_earn.py` | cały przepływ (uiautomator2) |
| `requirements.txt` | zależności Pythona |
| `INSTALL.md` | ta instrukcja |

## Co zainstalować na VM (kolejność)
1. **Python 3.11+** (64-bit) — https://www.python.org/downloads/
   podczas instalacji zaznacz *Add python.exe to PATH*.
2. **Android SDK platform-tools** (adb) — https://developer.android.com/tools/releases/platform-tools
   rozpakuj np. do `C:\platform-tools` i dodaj do PATH (lub zapamiętaj ścieżkę).
3. **Emulator Androida** z maszyną typu Pixel 8 + **zalogowany profil w aplikacji Bing**
   (tak jak na stacji źródłowej). Opcje:
   - Android Studio → Device Manager → Pixel 8 (API 34+ zalecane),
   - Bing (com.microsoft.bing) zalogowany na konto Microsoft z Rewards.
4. W wierszu poleceń (w katalogu pakietu):
   ```bat
   python -m pip install -r requirements.txt
   python -m uiautomator2 init
   ```
   (`uiautomator2 init` wgrywa assistanta na emulator — raz na urządzenie.)

## Konfiguracja adb (jeśli emulator stoi na INNEJ maszynie niż VM)
Na maszynie z emulatorem: `adb -a -P 5037 nodaemon server` (nasłuch w sieci).
Na VM: `set ADB_SERVER_SOCKET=tcp:<IP-hostu>:5037` przed uruchomieniem.
Jeśli emulator stoi na VM — nic nie konfiguruj.

## Uruchomienie
```bat
python read_to_earn.py emulator-5554
```
- `emulator-5554` — domyślny serial emulatora; zmień wg `adb devices`.
- Zakończenie: skrypt sam się zatrzymuje, gdy Read to earn jest wyczerpane,
  i zamyka wszystkie karty. Log w konsoli; można przekierować: `>> run.log 2>&1`.

## Planowanie (opcjonalnie)
Harmonogram zadań Windows:
```bat
schtasks /create /tn "ReadToEarn" /tr "C:\pkg\read_to_earn.bat" /sc daily /st 09:00
```

## Znane ryzyka (z testów lokalnych)
- ANR „Process system isn't responding" przy masowym zamykaniu kart — po restarcie
  emulatora znika; skrypt nie klikna tego dialogu (nie jest częścią przepływu).
- Klik w zły element „Rewards" otwierał wyszukiwarkę — przepływ używa stabilnej
  ścieżki Apps → Rewards (nie kafelek).
- Deduplikacja artykułów działa na tytuł karty; tytuły są stabilne w obrębie sesji.
