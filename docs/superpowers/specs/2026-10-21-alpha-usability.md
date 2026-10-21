# Alpha usability — zakres zatwierdzony zgodą in blanco

Użytkownik zlecił zaplanowanie kolejnych 50 zadań, samodzielne wykonanie prac,
commit/push na końcu i otwarcie folderu z gotową aplikacją. Ten etap poprawia
lokalny produkt macOS bez dodatkowych silników, usług, kont ani sekretów.

Historia: wyszukiwanie dosłownego tekstu po display_url/output_dir, maksymalnie
200 znaków; filtry all/active/history/completed/failed/cancelled. failed obejmuje
failed/partial/interrupted/needs_auth, cancelled tylko cancelled. Odczyty nadal
mają maksymalnie 100 rekordów, stałą liczbę migawek i podpisane kursory; cursor
wiąże filtr i zapytanie. Wyszukiwanie może skanować bazę, nie wczytuje jej w RAM.
Globalne liczniki niezależne od bieżącego wyszukiwania.

GUI: jawne wyszukiwanie przyciskiem/Return, szczegóły zadania, bezpieczny raport
kopiowany tylko na żądanie (bez URL, ścieżek, nazw plików i sekretów), czytelny
postęp bajtowy, klawiatura, ustawienia wyglądu i katalogu. Nie otwieramy stron
ani nie czytamy schowka automatycznie. Nie dodajemy usuwania plików/historii.

Dystrybucja: pakiet informacji licencyjnych zależności wygenerowany z metadata,
manifest wersji, checksums; brak deklaracji zakończenia audytu prawnego ani
wyboru licencji projektu. Notaryzacja i aktualizator pozostają osobnym etapem.

Każdy punkt planu ma konkretny wynik w kodzie, dokumentacji lub weryfikacji.
Nie oznaczamy testu żywych stron, czystej instalacji ani VoiceOver jako wykonanych
na podstawie testów syntetycznych. Build nadal macOS arm64, minimum deklarowane13.
