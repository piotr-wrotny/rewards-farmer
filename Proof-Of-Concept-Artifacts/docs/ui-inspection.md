# UI Inspection — Bing 34.0.440821002 na ReDroid 14

Metoda: `adb shell uiautomator dump` → `adb pull` → analiza XML.
Surowe dumpy w `ui/` (nazwy: `window-fre3.xml` = home, `window-search.xml` = wpisywanie, `window-results.xml` = BrowserActivity).

## Home screen (`MainSapphireActivity`)

Bogata hierarchia, **semantic resource IDs obecne** — dobra baza pod automatyzację:

### Resource IDs (com.microsoft.bing:id/)
| ID | Rola |
|---|---|
| `sa_search_box` / `sa_hp_header_search_box` | pole wyszukiwania |
| `sa_hp_feed_container`, `sa_hp_scroll_content` | feed newsowy |
| `sa_profile_button` | profil |
| `glance_card_container`, `tv_glance_card_description` | karty skrótów |
| `edge_web_view` | webview (treści web wewnątrz home) |
| `recyclerView`, `container`, `action_bar_root` | struktura |

### Content-desc (Appium: accessibility id)
`Home`, `Search`, `Copilot`, `Rewards`, `Profile`, `Tabs`, `Apps`, `Camera`, `Camera search`, `Image Creator`, `Trending`, `Voice search`, `Wallpapers`

## Przepływ wyszukiwania (zweryfikowany ręcznie przez ADB)

1. `input tap` na bounds `sa_search_box` (w 720x1280: ~[32,674][688,818])
2. `input text "hello"` — tekst widoczny w UI dump
3. `input keyevent 66` (ENTER)
4. → otwiera się `com.microsoft.sapphire.app.browser.BrowserActivity` z webview

## Ocena pod automatyzację (Appium/UIAutomator2)

| Kryterium | Status |
|---|---|
| Resource IDs | ✅ bogate, stabilne nazwy |
| Accessibility labels | ✅ na głównych kontrolkach (content-desc) |
| WebView w hierarchy | ✅ (`edge_web_view`); zawartość webview widoczna jako tekst tylko po załadowaniu — **blokada: brak DNS w kontenerze** |
| Współrzędne vs selektory | **Selektory preferowane** — rozdzielczość 720x1280 może różnić się od emulatora |
| OCR/vision potrzebne? | Nie dla podstawowej nawigacji |

## Wskazówki do przenoszenia przepływów z Android Emulatora

- Mapuj `AndroidEmulator` resource-id 1:1 — Bing używa tego samego `com.microsoft.bing:id/*` niezależnie od runtime.
- Jeśli przepływ używa `ui.Selector(resourceId=...)` / Appium `-android uiautomator` — powinien działać bez zmian.
- Jeśli używa współrzędnych — przemapuj z dumpów w `ui/` (rozmiar ekranu kontenera: 720x1280, density 160).
