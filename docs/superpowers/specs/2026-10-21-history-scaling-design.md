# Historia bez limitu 1000 zadań — projekt kolejnego etapu

Status: zatwierdzony przez użytkownika 2026-10-21; wdrażany według planu history-scaling. Wyniki faktycznych kontroli zawiera raport weryfikacji.

## Cel i granice

Fetchmunk ma zachować płynny start i obsługę anulowania także przy dużej historii. Usuwamy sztuczny limit 1000 zapisanych zadań, ale nie obiecujemy nieograniczonych zasobów: zużycie dysku nadal zależy od liczby rekordów, a pamięć aplikacji ma zależeć od wielkości strony, nie całej historii. Istniejące zadania, próby, operation_id i katalogi pobrań pozostają zachowane.

Etap obejmuje istniejącą aplikację macOS i backend Python. Logowanie, dodatkowe silniki, aktualizacje oraz Windows/Linux pozostają osobnymi etapami.

## Potwierdzone problemy obecnej implementacji

- `JobStore.all_jobs()` deserializuje całą historię. Korzystają z tego start, odzyskiwanie zadań, scheduler i migawki.
- `SnapshotStore` przechowuje do czterech pełnych kopii zadań w RAM.
- `AppModel.refresh()` odczytuje wszystkie strony i dodaje wszystkie zadania do tablicy. Obecne stronicowanie ogranicza rozmiar wiadomości IPC, a nie pamięć GUI.
- Liczniki i filtrowanie w Swift korzystają z całej tablicy. Samo usunięcie MAX_JOBS byłoby regresją.

## Rozważone rozwiązania

1. Podwyższenie limitu — mała zmiana, ale odsuwa ten sam problem. Odrzucone.
2. SQLite z indeksami, spójnymi odczytami stron i ograniczoną listą w GUI — rekomendowane. Wykorzystuje istniejącą bazę i nie wymaga nowej usługi.
3. Nowa warstwa bazy/ORM lub osobny serwis — większa migracja bez korzyści dla obecnego produktu. Odrzucone.

## Proponowane zachowanie GUI

- Istniejące zakładki Wszystkie, W kolejce i Historia pozostają.
- Jednorazowo widoczna jest strona do 100 zadań. Przyciski „Nowsze” i „Starsze” zastępują automatyczne pobieranie całej historii. To celowa propozycja UX do zatwierdzenia.
- Bieżące pobieranie pozostaje widoczne w osobnej sekcji nad listą, także podczas przeglądania starszej historii. Nie jest przechowywana cała kolejka poza widoczną stroną.
- Liczniki pochodzą z backendu i dotyczą wszystkich rekordów, a nie załadowanej strony.
- Nowe zadanie otwiera najnowszą stronę. Zmiany podczas przeglądania starszej strony nie przestawiają jej automatycznie; pojawia się informacja „Lista została zaktualizowana” z odświeżeniem.
- Postęp widocznego aktywnego zadania aktualizuje się na żywo. Akcje anulowania i ponawiania zawsze sprawdzają bieżący stan w backendzie, nawet jeśli wiersz pochodzi ze starszej migawki.
- Wygaśnięcie migawki zachowuje widoczną stronę; próba przejścia dalej odświeża ją w pobliżu jej klucza sortowania, z czytelnym komunikatem. Nie uruchamia pętli odczytu całej historii.

## Baza i scheduler

Migracja schematu 1 → 2 jest transakcyjna i zachowuje istniejący JSON zadania oraz tabele operations/attempts. Dodaje indeksowane pola stanu, czasu utworzenia i trwałej kolejności kolejki. Nowe zadanie i retry otrzymują nowy numer kolejki; aktualizacja postępu go nie zmienia. Nie używamy zmieniającego się rowid jako kontraktu FIFO.

Scheduler wybiera jedno queued przez indeksowane zapytanie z LIMIT 1. Start używa EXISTS; odzyskiwanie odczytuje tylko stany aktywne, partiami. Liczniki stanów są utrzymywane transakcyjnie wraz ze zmianą zadania; nie wymagają ponownego skanowania całej historii przy każdym zdarzeniu postępu.

Przed migracją powstaje prywatna kopia SQLite przez API backup. Niepowodzenie nie usuwa oryginału. Starszy build odrzuca nowszy schemat zgodnie z dotychczasową zasadą; rollback wymaga odtworzenia kopii, nie uruchomienia starszej aplikacji na schemacie 2.

## Migawki i protokół

Zachowujemy JSONL, rozmiar ramki 1 MiB, idempotencję operacji i limit 100 rekordów na stronę. Rozszerzenie jest sygnalizowane capability `paged_jobs`; nowy frontend wymaga go przed inicjalizacją widoku.

`jobs.snapshot` otrzymuje filtr `all`, `active` lub `history`, deterministyczny porządek (created_at, job_id) oraz oba kursory: next_cursor i previous_cursor. Odpowiedź zachowuje snapshot_id i at_seq. Brak filtra odpowiada all. Istniejące pola i komendy pozostają dostępne. Osobne `jobs.summary` zwraca liczniki i bieżące zadanie.

Migawka to osobna transakcja odczytu SQLite w trybie WAL, nie lista obiektów Python. Granica odczytu jest ustalana pod blokadą koordynatora razem z at_seq; potem strony czytamy przez niezależne połączenie. Zapytania korzystają z indeksów i kursorów opartych o klucze, bez OFFSET rosnącego z numerem strony.

Maksymalnie cztery migawki, ważne 60 s, tak jak dotychczas. Zamknięcie, wygaśnięcie i zastąpienie migawki kończy jej transakcję. Długie odczyty mogą zatrzymać checkpoint WAL, dlatego budżet pliku WAL wynosi 64 MiB: po przekroczeniu unieważniamy migawki i próbujemy checkpointu. To próg działania, nie obietnica ścisłego limitu fizycznego pliku. Brak miejsca daje kontrolowany błąd, nie utratę zapisanych zadań.

Frontend trzyma bieżącą stronę, najwyżej jedną przygotowaną stronę sąsiednią i aktywne zadanie. Odpowiedzi z wcześniejszego filtra lub poprzedniej generacji odświeżenia są ignorowane. Przerwa w numeracji zdarzeń odświeża summary i widoczną stronę; nie ładuje całej historii.

## Kryteria odbioru

- Migracja zachowuje zadania, próby i idempotencję; jej przerwanie nie zostawia połowicznego schematu.
- Testy 100 000 syntetycznych rekordów: pierwsza/ostatnia strona, identyczne daty, przejście w obie strony, TTL, ewikcja, współbieżne zmiany, filtr i limit bajtów.
- Testy pokazują, że scheduler i zwykły odczyt strony nie deserializują całej tabeli; sprawdzamy również plan zapytań SQLite.
- Testy GUI: limit liczby załadowanych obiektów, liczniki globalne, zmiana filtra podczas odpowiedzi, wygaśnięcie migawki i brak skoku przy napływie zdarzeń.
- Pomiar 1000 i 100 000 rekordów: RSS, czas gotowości, opóźnienie odczytu strony i anulowania podczas przeglądania historii. Wyniki zapisujemy; usunięcie limitu dopiero po wykazaniu ograniczonego użycia pamięci i przejściu regresji.
- Nowy build .app/DMG, smoke test rzeczywistego pobrania, kontrola Mach-O i podpisów jak poprzednio.

## Kolejność realizacji po zatwierdzeniu

1. Migracja i indeksowane operacje bazy; regresje FIFO/idempotencji.
2. Migawki SQLite, summary, walidacja kursorów, TTL i budżet WAL.
3. Stronicowany model SwiftUI i testy wyścigów odświeżania.
4. Pomiar dużej historii, usunięcie limitu 1000, przebudowa i raport.

Użytkownik zatwierdził jawną nawigację po stronach poleceniem „dzialaj”. Zmiana nie dodaje zależności produktu.
