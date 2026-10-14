# Stabilizacja runów — 2026-10-14

## Kontekst i kwalifikacja problemu

Dzisiejsze incydenty zakwalifikowano jako:

1. **Web code defect** — crash klasyfikatora błędów (`task_failure_report` /
   `ElementNotReady`), niezależny od logowania kont.
2. **Mobile runtime instability** — przejściowe problemy sesji/home-state
   (`home screen not reachable`, sporadyczne rozłączenia), a nie problem
   tożsamości profili.

Po poprawkach i rerunach profile docelowe domknięto do `120/120`.

## Decyzja wdrożeniowa (od jutra)

### Mobile

- Przejście z **3 slotów na 2 sloty** (`redroid` + `redroid-b`).
- Stałe przypisanie profili do slotów (pinning).
- Harmonogram startuje **rano**.

### Web

- Poranny przebieg `run_daily.sh` (normalny zbiór zadań).
- Dodatkowy przebieg **wieczorny** pod claim:
  `run_task.sh bonus_points <profile>`.

## Oczekiwany efekt

- Mniej jednoczesnych sesji mobile => mniej niestabilności runtime.
- Lepsza separacja i powtarzalność slotów.
- Web rano + wieczorem ma domykać odbiory punktów (`claim points`) tego samego dnia.
