# Fetchmunk — projekt protokołu GUI ↔ backend v1

Status: v1 jest zaimplementowana dla zadań; rozszerzenia `paged_jobs` i `history_search` dodano 2026-10-21. Metody `auth.*` pozostają planowane i zwracają `dependency_unsupported`.
Powiązany dokument: [MVP i architektura](mvp.md).

## Transport i wersjonowanie

- Dwa potoki: GUI pisze na stdin backendu i czyta stdout.
- UTF-8, jeden obiekt JSON na linię zakończoną LF. Nowe linie wewnątrz
  wartości są escapowane przez serializer JSON.
- stdout zawiera wyłącznie protokół. stderr to ograniczona i zredagowana
  diagnostyka, nigdy wyjście gallery-dl przekazywane bez kontroli.
- Maksymalna wiadomość: 1 MiB w UTF-8, łącznie z LF.
- GUI i backend czytają potoki asynchronicznie; nie wykonują blokującego
  oczekiwania na wątku interfejsu.
- Niepoprawny JSON lub przekroczony limit kończy sesję jako `protocol_error`,
  z kontrolowanym zatrzymaniem pracownika.
- Każda wiadomość ma `protocol: 1` oraz `type`.
- Nieznana wersja główna blokuje pracę. Nieznane pola są ignorowane.
  Nieznana komenda zwraca błąd, nieznane zdarzenie można pominąć.

Identyfikatory to nieprzezroczyste ciągi, generowane jako UUID.
Czas to RFC 3339 w UTC. Liczniki to nieujemne liczby całkowite.
Brak znanej wartości oznacza `null`, nigdy umowne zero lub `-1`.

## Uruchomienie

Pierwszą wiadomością jest `hello` backendu:

```json
{"protocol":1,"type":"hello","session_id":"session-1","backend_version":"0.1.0","engine_version":"pinned-version","capabilities":["jobs","paged_jobs","history_search"]}
```

Wartości wersji w przykładzie są ilustracyjne, a nie wybranymi wydaniami.
`capabilities` informuje o funkcjach backendu, nie o gwarantowanym działaniu
każdego serwisu. `browser_auth` ogłaszamy tylko, gdy implementacja jest dostępna.

GUI sprawdza wersję, wysyła `session.initialize` z absolutnymi ścieżkami
`data_dir` i `default_destination`, a potem `jobs.snapshot`.
Backend nie wykonuje zadań przed inicjalizacją. Brak `hello` przez 10 s
oznacza nieudany start; GUI kończy proces i pozwala ponowić.

## Komendy i odpowiedzi

Przykład żądania:

```json
{"protocol":1,"type":"request","id":"request-1","method":"jobs.create","params":{"operation_id":"operation-1","url":"https://example.org/gallery/123","destination":"/Users/example/Downloads/Fetchmunk"}}
```

Przykład odpowiedzi:

```json
{"protocol":1,"type":"response","id":"request-1","result":{"job_id":"job-1","revision":1}}
```

Przykład błędu komendy:

```json
{"protocol":1,"type":"response","id":"request-1","error":{"code":"invalid_url","message_key":"error.invalid_url","retryable":false}}
```

Odpowiedź zawiera dokładnie jedno z pól `result` lub `error`. `id` koreluje
odpowiedź z żądaniem. Sukces `jobs.create` oznacza trwałe przyjęcie zadania,
nie sukces pobierania ani potwierdzenie dostępności zdalnego źródła.

| Metoda | Parametry poza `operation_id` | Wynik |
|---|---|---|
| `session.initialize` | `data_dir`, `default_destination` | `schema_version`, `queue_enabled` |
| `jobs.create` | `url`, `destination` | `job_id`, `revision` |
| `jobs.get` | `job_id` | pełne zadanie |
| `jobs.snapshot` | opcjonalne `cursor`, `limit` 1–100, `filter`, `anchor`, `query` | `snapshot_id`, `at_seq`, `jobs`, `next_cursor`, `previous_cursor` |
| `jobs.summary` | brak | `total`, `active`, `history`, `completed`, `failed`, `cancelled`, `current_job`, `queue_enabled`, `at_seq` |
| `jobs.cancel` | `job_id` | aktualne pełne zadanie |
| `jobs.retry` | `job_id` | aktualne pełne zadanie z nową próbą |
| `queue.set_enabled` | `enabled` | `queue_enabled` |
| `auth.set_browser` | `job_id`, `browser`, `profile`, `consent: true` | `auth_ref` |
| `auth.clear` | `job_id` | `cleared` |
| `app.shutdown` | `reason`: `quit` albo `update` | `accepted` |

`session.initialize` jest dozwolone raz na sesję i nie wymaga `operation_id`.
Odczyty również go nie wymagają. Pozostałe komendy mutujące go wymagają.

Backend zapisuje klucz operacji, treść żądania i wynik mutacji w jednej
transakcji. Powtórzenie tej samej operacji daje ten sam wynik; użycie klucza
z innymi parametrami zwraca `operation_conflict`.
Rejestr obejmuje całą v1 bez automatycznego wygaszania. Zmiana tej polityki
wymaga określenia okresu bezpiecznych ponowień.
`app.shutdown` jest idempotentne w sesji; po restarcie GUI nie odtwarza go.

`jobs.cancel` dla zakończonego zadania jest bezpiecznym no-op.
`jobs.retry` działa tylko dla `failed`, `partial`, `cancelled`, `interrupted`,
`needs_auth`; dla innych stanów zwraca `invalid_state`.
Ustawienie przeglądarki nie rozpoczyna transferu — GUI osobno wywołuje retry.

Timeout komendy po 5 s nie oznacza, że mutacja się nie wykonała.
GUI ponawia z tym samym `operation_id` albo pobiera stan. Nie tworzy
automatycznie drugiego zadania.

## Model zadania

Wymagane pola:

- `job_id`, `revision`, `attempt` (od 1), `state`.
- `url`: pełny adres zadania, przeznaczony tylko do prywatnego stanu aplikacji.
- `display_url`: adres z usuniętymi danymi uwierzytelnienia, query i fragmentem.
- `destination`, `output_dir`: absolutne ścieżki.
- `created_at`, `updated_at`, `auth_ref` (może być `null`).
- `downloaded`, `skipped`, `failed_files`: liczniki bieżącej próby.
- `current_file`: `null` lub obiekt `name`, `bytes_done`, `bytes_total`,
  `bytes_per_second`. Nieznany rozmiar i szybkość to `null`.
- `wait_until`: czas wznowienia znany silnikowi lub `null`.
- `error`: `null` lub kod, klucz komunikatu, `retryable`, `action`.

`revision` rośnie przy każdej opublikowanej zmianie zadania.
Retry zwiększa `attempt`, zeruje liczniki bieżącej próby i zachowuje poprzednią
próbę w bazie. GUI nie sumuje ich bezpośrednio: ten sam plik mógł wystąpić
w więcej niż jednej próbie.

URL przyjmujemy tylko jako HTTP/HTTPS, bez danych logowania w części authority.
Nie przyjmujemy argumentów CLI, wyrażeń Pythona ani dowolnego JSON config.
GUI ogranicza wyświetlanie danych źródła do tekstu; nie renderuje ich jako HTML.

## Stany i wynik

```text
queued → extracting → downloading → completed / partial / failed / empty
                     ↘ waiting → extracting / downloading
extracting / downloading / waiting → needs_auth
queued → cancelled
extracting / downloading / waiting → cancelling → cancelled
aktywny stan + zamknięcie lub awaria → interrupted
failed / partial / cancelled / interrupted / needs_auth → queued (nowa próba)
```

To skrót graficzny. `extracting` może zakończyć się bez fazy `downloading`;
`waiting` może wystąpić w obu fazach. `cancelling` po awarii może stać się
`interrupted`. `needs_auth` może zostać anulowane bez uruchomienia pracownika.

`waiting` oznacza oczekiwanie wewnątrz silnika, np. na jego retry.
Nie uruchamiamy drugiej, konkurencyjnej pętli ponowień w koordynatorze.
`queue_enabled: false` blokuje rozpoczynanie kolejnych zadań; nie jest pauzą
aktywnego transferu. Świeża instalacja zaczyna z kolejką włączoną.
Po restarcie z zachowanymi zadaniami kolejka jest wyłączona do decyzji użytkownika.

Reguły wyniku:

- `completed`: silnik zakończył bez błędów i co najmniej jeden plik został
  pobrany lub świadomie pominięty jako istniejący.
- `empty`: brak wyników i brak błędu. Brak dostępu nie jest pustą galerią.
- `partial`: próba ma ukończone/pominięte pliki i błąd, który nie został naprawiony.
- `failed`: błąd bez ukończonych/pominiętych plików w tej próbie.
- `needs_auth`: rozpoznany problem uwierzytelnienia; zachowujemy liczniki
  także wtedy, gdy wcześniej pobrano część plików.
- `cancelled` i `interrupted`: zachowują wyniki częściowe, nie udają sukcesu.

Sukces zatwierdzony przed anulowaniem pozostaje sukcesem. Jeśli anulowanie
przyjęto wcześniej, późny komunikat pracownika nie zmienia go na ukończenie.
Koordynator serializuje te decyzje i akceptuje zdarzenia tylko dla aktualnej próby.

## Zdarzenia i synchronizacja

```json
{"protocol":1,"type":"event","session_id":"session-1","seq":12,"event":"job.changed","data":{"job_id":"job-1","revision":2}}
```

`job.changed` jest powiadomieniem o zmianie; GUI pobiera aktualny obiekt przez
`jobs.get`, łącząc serię powiadomień w jeden odczyt. Odpowiedzi ze starszą
rewizją są ignorowane. Na aktualizacje bieżącego postępu przeznaczamy
maksymalnie cztery powiadomienia na sekundę; zmiany stanów wysyłamy od razu.

Inne zdarzenia: `queue.changed` z `queue_enabled`, `backend.stopping` z powodem.
`seq` rośnie w ramach `session_id`. Luka oznacza potrzebę pobrania migawki.
Zmiana sesji unieważnia poprzedni licznik i wymaga nowej inicjalizacji.

Pierwsze `jobs.snapshot` tworzy niezmienną migawkę z watermarkiem `at_seq`.
Cursor jest nieprzezroczysty i wiąże kolejne strony z tą samą migawką.
Migawka wygasa po 60 s; `snapshot_expired` wymaga rozpoczęcia od nowa.
Backend ogranicza stronę także bajtowo, aby zmieścić limit wiadomości.

GUI buforuje powiadomienia o `seq > at_seq` podczas pobierania stron.
Po wczytaniu migawki odświeża wskazane zadania przez `jobs.get`.
Bufor przechowuje najwyższą rewizję dla identyfikatora, nie każdą zmianę.
Przekroczenie limitu 1000 identyfikatorów wymusza nową migawkę.
Nie przewidujemy odtwarzania historycznego strumienia zdarzeń.

Przy backpressure koordynator scala powiadomienia postępu.
Jeżeli nie może dostarczyć odpowiedzi lub zmiany stanu przez 5 s, zamyka
sesję i zatrzymuje pracownika. Nie odkłada wiadomości w nieograniczonej kolejce.

## Błędy i uwierzytelnianie

Kody domenowe: `unsupported_url`, `auth_required`, `auth_expired`,
`access_denied`, `rate_limited`, `network_error`, `disk_full`,
`permission_denied`, `engine_error`, `dependency_unsupported`.
Kody protokołu/komend: `invalid_url`, `invalid_params`, `not_found`,
`invalid_state`, `operation_conflict`, `snapshot_expired`, `protocol_error`.

`action`: `retry`, `authenticate`, `check_destination`, `update_app` albo `none`.
Frontend tłumaczy `message_key`; nie analizuje komunikatów tekstowych silnika.
Niepewna diagnoza nie może być przedstawiona jako pewna przyczyna.
`retryable` oznacza sensowność ponowienia, nie polecenie automatycznego retry.

`auth.set_browser` przyjmuje wyłącznie nazwę obsługiwanej przeglądarki i profil.
Backend weryfikuje wartości i wyznacza domeny z obsługi źródła.
Nie wolno logować payloadów protokołu. `auth_ref` nie zawiera sekretu.

Przesyłanie haseł, tokenów i plików cookies nie jest częścią kontraktu v1.
Jeżeli lista źródeł wymusi takie metody, kontrakt wymaga jawnego rozszerzenia.

## Zakończenie i testy kontraktu

`app.shutdown` najpierw blokuje kolejkę, utrwala zamiar zatrzymania i odpowiada
`accepted`. Potem zatrzymuje pracownika, utrwala wynik, zamyka bazę i kończy
proces. Odpowiedź nie jest potwierdzeniem zakończenia procesu.
GUI czeka na jego wyjście; po 10 s wymusza zakończenie i nie instaluje
aktualizacji, dopóki procesy oraz blokada danych nie zostaną zwolnione.

Wymagane scenariusze w przyszłej implementacji:

- podział jednej linii między wiele odczytów; kilka linii w jednym odczycie;
- Unicode, escapowane nowe linie, błędny JSON, przekroczenie limitu;
- obca wersja protokołu i nieznane pola;
- powtórzona mutacja po utracie odpowiedzi i po restarcie;
- aktualizacje podczas stronicowania, luka `seq`, stara rewizja;
- wyścig ukończenia z anulowaniem, zdarzenia poprzedniej próby;
- awaria każdego z trzech procesów i brak osieroconych transferów;
- częściowy sukces, pusta galeria, same pominięte pliki i wygasła sesja;
- brak sekretów w logach i nieograniczonego buforowania postępu.

## Rozszerzenie paged_jobs (2026-10-21)

Nowy frontend wymaga capability `paged_jobs`. Filtr snapshot: `all` (domyślny),
`active` (stany aktywne + queued + needs_auth) lub `history` (pozostałe).
Porządek: created_at malejąco, a przy remisie job_id malejąco. Kursory są
nieprzezroczyste i przypisane do migawki oraz filtra; nie należy ich parsować.
`anchor: [created_at, job_id]` rozpoczyna nową migawkę od rekordu o kluczu
nie większym od podanego, przydatne po snapshot_expired. Nie łączymy anchor
z cursor w GUI. Liczniki summary dotyczą całej bazy; current_job jest pełnym
bieżącym zadaniem albo null.

Backend używa maksymalnie czterech transakcji odczytu WAL, TTL60s. Budget WAL
64MiB jest progiem unieważniania migawek i próby checkpointu, nie ścisłym
limitem rozmiaru pliku. GUI pobiera jedną stronę, nie iteruje po next_cursor
automatycznie. Przerwa w zdarzeniach odświeża summary i widoczną stronę.

Błąd zapisu/checkpointu zatrzymuje kolejkę i może wysłać `queue.changed`
z `queue_enabled: false` oraz `error.code`. Zatwierdzone wcześniej jobs.create
zachowuje wynik i operation_id; błąd późniejszego uruchomienia zadania nie
cofa zapisanego zgłoszenia. Migracja schema1→2 waliduje rekordy i tworzy backup.


## Rozszerzenie history_search (2026-10-21)

Backend ogłasza capability `history_search`. `jobs.snapshot` przyjmuje także:

- `filter: "completed"`: wyłącznie stan completed;
- `filter: "failed"`: stany failed, partial, interrupted i needs_auth;
- `filter: "cancelled"`: wyłącznie stan cancelled;
- `query`: opcjonalny string, maksymalnie 200 znaków Unicode, bez NUL.
  Wartość null i inne typy dają `invalid_params`. Brak query przy tworzeniu
  migawki oznacza pusty string, czyli brak ograniczenia tekstowego.

Wyszukiwanie sprawdza dosłowny podciąg w `display_url` lub `output_dir`,
bez rozróżniania wielkości liter (Unicode casefold, np. Straße ↔ STRASSE).
Nie przeszukuje pełnego `url`, a więc query/fragment URL pozostają poza
zakresem wyszukiwania. `%`, `_`, apostrof i backslash są zwykłymi znakami.
Tekst nie jest przycinany, tokenizowany ani normalizowany do NFC/NFD.
Filtr stanu i zapytanie tekstowe są łączone warunkiem AND.

Migawka zachowuje filtr oraz oryginalny query przez cały okres życia.
Podpisany cursor wskazuje tę niezmienną migawkę. Przy kontynuacji można
pominąć filter/query (zgodność ze starszym klientem); podane wartości muszą
być dokładnie zgodne z migawką, inaczej backend zwraca `invalid_params`.
Różna wielkość liter w query również jest niedopasowaniem, mimo identycznych
wyników wyszukiwania. Nowy query wymaga nowej migawki. Sortowanie, anchor,
limity stron i odczyt spójny podczas zmian bazy działają jak dla paged_jobs.

`jobs.summary` dodaje globalne `failed` i `cancelled`, z tymi samymi zbiorami
stanów co nowe filtry. Liczniki nigdy nie zależą od bieżącego query/filtra.
`needs_auth` należy jednocześnie do active i failed: te kategorie nie tworzą
rozłącznego podziału; total nadal równa się active + history.

Wyszukiwanie działa w SQLite po rekordach kandydujących, bez kopiowania
historii do pamięci Pythona. Strony active/history używają indeksu bucket/created_at; pozostałe strony
wymuszają indeks created_at/id i filtrują stany podczas uporządkowanego
skanowania, bez tymczasowego sortowania historii. Sprawdzenie istnienia
następnej strony może użyć indeksu state. Dowolny podciąg wymaga skanowania
pól JSON kandydatów i może
być wolniejszy dla dużej historii. RAM stron i cache odczytu pozostaje
ograniczony. Nie zmienia to schematu bazy (wersja 2).
