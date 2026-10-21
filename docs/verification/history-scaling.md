# Historia bez limitu 1000 zadań — weryfikacja 2026-10-21

Zaimplementowano indeksowaną bazę schema2, migawki SQLite WAL i stronicowany model SwiftUI. GUI utrzymuje do 100 rekordów bieżącej strony oraz oddzielne aktywne zadanie. Liczniki dotyczą całej bazy. Historia na dysku nadal rośnie; nie ma obietnicy nieograniczonej pojemności dysku.

## Wyniki automatyczne

- Backend: **59 testów PASS**.
- Swift: **19 testów PASS**.
- Migracja: backup prywatny (0600), zachowanie jobs/operations/attempts, odrzucenie błędnej składni i struktury rekordów przed zatwierdzeniem schematu, rollback po błędzie i nieudanym backupie.
- Strony: stabilne odczyty podczas aktualizacji, obie strony nawigacji, remisy dat, limit bajtów, wygasanie/ewikcja, niepoprawne kursory/filtry, wymuszenie checkpointu po przekroczeniu budżetu WAL.
- Kolejka: brak skanowania całej historii; retry na końcu FIFO; idempotencja zachowana także przy błędzie uruchomienia po zatwierdzonym create. Błędy zapisu/checkpointu zatrzymują kolejkę i mają komunikat GUI.
- Swift: ograniczona liczba obiektów, ignorowanie spóźnionej strony innego filtra, odświeżenie przy luce zdarzeń, anchor po wygaśnięciu, globalne liczniki, ochrona przed starym summary nadpisującym nowsze zdarzenie.
- Zamrożony backend z `.app`, izolowany PATH/cwd i baza schema1 z 100 000 rekordów: **PASS**, migracja + initialize **0,738 s**, odczyt kolejnej i poprzedniej strony PASS; RSS procesu **50,36 MiB**.

## Artefakty

- Finalne `.app` i DMG przebudowane po poprawkach przeglądu: około 26 MiB / 15 MiB.
- Smoke test `.app`: PASS, hello 0,691 s; pobranie rzeczywistych bajtów HTTP, idempotencja, summary i snapshot schema2 oraz zakończenie procesu.
- Ten sam smoke test z zamontowanego DMG tylko do odczytu: PASS, hello 0,452 s. Obraz odmontowany po teście.
- `codesign --verify --deep --strict`: PASS (ad hoc). Wszystkie 5 Mach-O mają deployment target <= macOS13; to nie test uruchomienia na macOS13.
- `git diff --check`: PASS.

## Powtarzalny benchmark

Polecenie deweloperskie: `backend/.venv/bin/python scripts/benchmark_history.py`.
Każda wielkość bazy działa w osobnym procesie i katalogu tymczasowym. Sprzęt:
Apple M4 Max, 128 GiB RAM, macOS 27.0.1, Python 3.13.16.

| Pomiar | 1000 zadań | 100 000 zadań |
|---|---:|---:|
| Migracja + initialize | 8,82 ms | 725,65 ms |
| Mediana odczytu strony | 4,55 ms | 4,69 ms |
| Najwolniejsza strona | 5,11 ms | 5,82 ms |
| Anulowanie podczas odczytów | 1,27 ms | 1,40 ms |
| RSS koordynatora po teście | 29,89 MiB | 35,62 MiB |
| Szczyt alokacji Python dla odczytu stron | 0,38 MiB | 0,42 MiB |

Odczytano wszystkie rekordy bez zatrzymywania poprzednich stron w pamięci.
`EXPLAIN QUERY PLAN` potwierdził indeksy dla schedulera, all i history;
bez pełnego skanu jobs i tymczasowego sortowania.

Pomiar stron działa z tracemalloc, więc obejmuje jego narzut. RSS obejmuje
proces koordynatora, a nie GUI. Anulowanie wykorzystuje kontrolowanego
workera, mierzy reakcję koordynatora podczas odczytów i **nie** jest pomiarem
zatrzymania rzeczywistego transferu sieciowego. To pojedynczy lokalny przebieg,
nie gwarancja czasów na dowolnym komputerze.

## Przegląd i poprawki

Niezależny przegląd znalazł dwie uwagi Important, bez Critical/Minor.
Obie odtworzono testami FAIL i poprawiono do PASS:

1. Walidacja struktury historycznych rekordów przed commit migracji. Poprawny składniowo JSON bez wymaganych pól nie zmienia już schematu na 2.
2. Obsługa błędu SQLite/OSError także w schedulerze, checkpointach i callbackach workera. Już zatwierdzone create zwraca swój wynik, slot aktywnego workera zostaje zwolniony, kolejka zatrzymana, a GUI dostaje przyczynę.

Dodatkowo wykryto i poprawiono przypadek pustej strony przy odświeżeniu
kotwicy (można wrócić do nowszych rekordów) oraz wyścig starego summary
z nowszym zdarzeniem zatrzymania kolejki.

Decyzja wykonawcza: zastąpiono `Process.waitUntilExit()` powiadomieniem
`terminationHandler` rejestrowanym przed startem. Pełny test wcześniej
zawiesił się w waitUntilExit — potwierdzone próbką stosu xctest. Izolowany
test szybkich wyjść przechodził także przed poprawką, więc nie traktujemy
go jako deterministycznego odtworzenia tego konkretnego wyścigu. Obecny
zestaw testuje szybkie wyjścia, handshake timeout, rozłączenie i deadline.
Ryzyko zmiany: cykl życia procesu wymaga dalszej obserwacji w użyciu aplikacji.

## Migracja użytkownika i ograniczenia

Przed zmianą schema1→2 aplikacja zapisuje `state-before-v2.sqlite` obok
`state.sqlite`, domyślnie w `~/Library/Application Support/Fetchmunk`.
Wcześniejszy build odrzuci schema2; powrót do niego wymaga odtworzenia kopii
przy zamkniętej aplikacji. Kopia nie zawiera późniejszych operacji.
Nie zmieniamy katalogów pobranych plików.

Ręczny test natywnego GUI na dużej bazie **nie został wykonany**:
automatyczna kontrola uprawnień zablokowała uruchomienie samodzielnie
skompilowanego „Fetchmunk History QA.app” jako niezweryfikowanego programu.
Przygotowany host używa prywatnej bazy 100 000 fikcyjnych rekordów w build.
Wysłano pytanie o zgodę; bez odpowiedzi nie ponawiamy startu ani nie
uruchamiamy go inną drogą. Testy modelu Swift i zamrożonego backendu
przechodzą, lecz nie zastępują wizualnego sprawdzenia przycisków i pinowania.

Nadal niewykonane: rzeczywisty macOS13, czysta maszyna, VoiceOver i pomiar
GUI podczas transferu. Podpis ad hoc pozostaje lokalny; brak notaryzacji,
logowania, automatycznych aktualizacji i klientów Windows/Linux.
