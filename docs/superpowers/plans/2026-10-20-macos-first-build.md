# Fetchmunk: pierwszy działający build macOS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> for inline execution, or superpowers:subagent-driven-development if selected
> by the user. Implement task-by-task and track the checkboxes.

**Goal:** Zbudować lokalną aplikację macOS z dołączonym Pythonem i gallery-dl,
która przyjmuje publiczny link, pobiera pliki, zachowuje kolejkę i pokazuje wynik.

**Architecture:** SwiftUI komunikuje się z koordynatorem Python przez JSON Lines.
Koordynator zapisuje stan w SQLite i uruchamia pojedynczego pracownika gallery-dl.
GUI nie implementuje logiki pobierania ani klasyfikacji wyniku.

**Tech Stack:** SwiftUI/AppKit, Swift Package Manager, Python 3.13,
SQLite, gallery-dl, PyInstaller `onedir`, pytest.

**Spec:** [MVP](../../design/mvp.md),
[protokół v1](../../design/protocol-v1.md).

Status: plan do przeglądu. Nie wykonano zadań implementacyjnych.

## Global Constraints

- macOS jako pierwsze wydanie: Swift, SwiftUI i potrzebne integracje AppKit.
- Windows i Linux później: C# i Avalonia, wspólna implementacja GUI.
- Wspólny lokalny backend Python, korzystający z gallery-dl.
- Brak własnych ekstraktorów i własnego silnika pobierania.
- Maksymalna wiadomość: 1 MiB w UTF-8, łącznie z LF.
- Normalne zatrzymanie ma limit 5 sekund; później kończymy proces przymusowo.
- Cele: gotowe pole adresu do 1 s, potwierdzenie komendy do 250 ms bez sieci,
  postęp najwyżej 4 razy/s. To cele do pomiaru, nie gwarancje.
- Runtime i zależności wewnątrz `.app`; żadnego instalowania przez użytkownika.
- Pierwszy build: arm64, deployment target macOS 13.0. Test na obecnym systemie
  nie dowodzi zgodności z minimalną wersją.
- Bez logowania, odczytu cookies, nowych silników, wtyczek i usług sieciowych
  aplikacji w tym etapie.
- Każdy krok zmieniający zachowanie: test odtwarzający wymaganie, FAIL,
  implementacja, PASS. Nie testować samego istnienia plików źródłowych.
- Commity tylko z jawną listą plików danego zadania, bez dodawania obcych zmian.

## Zakres tego planu i dalsze etapy

Ten plan realizuje publiczne pobieranie, podstawową odporność, GUI oraz lokalne
pakowanie. Nie oznacza gotowości do publicznego wydania.

Oddzielne plany po zakończeniu:

1. Obsługa sesji dla listy serwisów wskazanych przez użytkownika, wraz z testem
   ograniczenia cookies do domen i bezpieczeństwa cache.
2. Podpis Developer ID, notaryzacja, Sparkle, aktualizacja danych oraz komplet
   materiałów licencyjnych i źródeł do wydania.
3. GUI Avalonia i dystrybucja Windows/Linux.

Brak certyfikatu nie blokuje lokalnego buildu podpisanego ad hoc.
Brak uzgodnionej licencji blokuje publiczną dystrybucję, nie lokalne testy.
Nie ogłaszać `browser_auth` ani gotowych aktualizacji w pierwszym buildzie.

## Stan środowiska

Sprawdzone 2026-10-20: arm64, macOS 27.0.1, Xcode w
`/Applications/Xcode.app/Contents/Developer`, Swift 6.4, Python systemowy 3.15.
Nie zainstalowano zależności projektu i nie sprawdzono certyfikatów.

Do budowania wybrać izolowany CPython 3.13; dokładny patch, źródło pobrania
i checksum zapisać w `packaging/toolchain.json` w zadaniu 1.
gallery-dl 1.32.17 jest kandydatem na pin znalezionym w metadanych PyPI.
Przed przypięciem sprawdzić pobrany artefakt i jego API; aktualizacja kandydata
jest dopuszczalna, ale musi mieć zapisany powód i test integracyjny.
Wersje PyInstaller i zależności przechodnich zamrozić z hashami w lockfile,
na podstawie faktycznie rozwiązanego środowiska, nie zgadywać numerów.

Źródła:
[gallery-dl PyPI](https://pypi.org/pypi/gallery-dl/json),
[PyInstaller requirements](https://pyinstaller.org/en/stable/requirements.html).

## Review Focus

- Nazwy Unicode, spacje i metaznaki w ścieżkach nie zmieniają argumentów procesu
  ani docelowego katalogu — zadania 1, 5 i 6.
- Zewnętrzna konfiguracja gallery-dl nie może zmienić zachowania aplikacji
  ani uruchomić poleceń użytkownika — zadanie 1.
- Powtórzone kliknięcie po timeout nie tworzy drugiego zadania, a awaria
  nie zamienia częściowego pobrania w sukces — zadania 3 i 4.
- Powolny odbiorca i długa historia nie powodują nieograniczonego RAM
  ani blokady przy anulowaniu — zadania 2, 4 i 5.
- Zabicie GUI lub koordynatora nie zostawia działającego transferu;
  uruchomienie z Findera nie wymaga środowiska terminala — zadania 4 i 6.

## Struktura

```text
backend/
  pyproject.toml
  requirements.lock
  src/fetchmunk_backend/
    __main__.py          # wejście coordinator/worker
    models.py            # Job, WorkerRequest, WorkerEvent, WorkerResult
    engine.py            # adapter gallery-dl, bez schedulerów
    wire.py              # ramkowanie i walidacja IPC
    store.py             # SQLite, operacje idempotentne, próby
    service.py           # komendy, kolejka, maszyna stanów
    supervisor.py        # cykl życia pracownika
    snapshots.py         # niezmienne stronicowane migawki
    diagnostics.py       # redakcja i ograniczanie logów
  tests/                 # pliki wymienione w zadaniach
macos/
  Package.swift
  Sources/Fetchmunk/
    FetchmunkApp.swift
    BackendClient.swift
    ProtocolModels.swift
    AppModel.swift
    MainView.swift
    JobRow.swift
    AppLifecycle.swift
  Tests/FetchmunkTests/
packaging/
  backend.spec
  toolchain.json
  Info.plist
scripts/
  build_backend.sh
  build_macos.sh
  smoke_bundle.py
docs/verification/first-build.md
```

## Task 1: rzeczywisty adapter i zamrożony backend

**Files:** utworzyć `backend/pyproject.toml`, `backend/requirements.lock`,
`backend/src/fetchmunk_backend/{__init__,__main__,models,engine}.py`,
`backend/tests/test_engine.py`, `packaging/{backend.spec,toolchain.json}`,
`scripts/build_backend.sh`, `.gitignore`.

**Interfaces:** `WorkerRequest(job_id: str, attempt: int, url: str,
output_dir: Path, archive_path: Path)`; `WorkerEvent(kind: str, data: dict)`;
`WorkerResult(downloaded: int, skipped: int, failed_files: int,
error_code: str | None)`.
`run_download(request: WorkerRequest, emit: Callable[[WorkerEvent], None])
-> WorkerResult`. Worker przyjmuje pojedyncze żądanie na stdin i emituje JSON;
pełnego protokołu GUI jeszcze nie udaje.

- [ ] Utworzyć izolowane środowisko, pin runtime i lock zależności; zapisać
  dokładne wersje. Pakiety wykonawcze bez yt-dlp i FFmpeg.
- [ ] Napisać testy `test_download_real_engine`, `test_skips_existing_file`,
  `test_partial_result`, `test_ignores_user_config`, `test_unicode_destination`.
  Używać istniejącego ekstraktora gallery-dl z kontrolowanymi odpowiedziami
  HTTP, bez nowego ekstraktora. Sprawdzić bajty pliku i liczniki, nie tylko exit code.
- [ ] Uruchomić `backend/.venv/bin/python -m pytest backend/tests/test_engine.py -q`;
  potwierdzić FAIL z braku implementacji.
- [ ] Zaimplementować adapter do API pobranej wersji, izolowaną konfigurację,
  archiwum i mapowanie zdarzeń. Nie kopiować downloadera upstream.
  Nie przekazywać surowych logów do `emit`.
- [ ] Powtórzyć testy; wymagać PASS.
- [ ] Zbudować `onedir` przez `scripts/build_backend.sh`; uruchomić zamrożony
  worker z roboczego katalogu ze spacjami i bez Pythona w PATH. Test musi pobrać
  kontrolowany plik i potwierdzić załadowanie dynamicznych ekstraktorów.
- [ ] Commit: `feat: add bundled gallery-dl worker`.

## Task 2: transport IPC i uzgodnienie sesji

**Files:** `backend/src/fetchmunk_backend/{wire,diagnostics}.py`,
modyfikacja `__main__.py`, `backend/tests/{test_wire,test_diagnostics}.py`.

**Interfaces:** `FrameDecoder.feed(chunk: bytes) -> list[dict]`,
`encode_frame(message: dict) -> bytes`, `ProtocolError`,
`redact_diagnostic(message: str) -> str`.
Tryb koordynatora emituje `hello` i wymaga `session.initialize`;
nie ogłasza `jobs`, dopóki komendy nie są gotowe.

- [ ] Testy ramki dokładnie 1048576 bajtów i przekraczającej limit o 1,
  wielobajtowego Unicode podzielonego między odczyty, wielu ramek naraz,
  błędnego JSON, tablicy zamiast obiektu, nieznanej wersji i EOF w połowie ramki.
- [ ] Testy redakcji tokenów i URL-i z query; limit logów 10 MiB łącznie.
- [ ] Uruchomić `backend/.venv/bin/python -m pytest backend/tests/test_wire.py backend/tests/test_diagnostics.py -q`;
  potwierdzić FAIL.
- [ ] Zaimplementować walidację typów wymaganych pól, bez dopuszczenia
  `bool` jako numeru wersji, i strumieniowy dekoder z ograniczeniem bufora.
  stderr odseparować od stdout.
- [ ] Powtórzyć testy; wymagać PASS.
- [ ] Commit: `feat: define bounded backend IPC transport`.

## Task 3: trwałe zadania i idempotentne operacje

**Files:** `backend/src/fetchmunk_backend/{store,snapshots}.py`,
rozszerzenie `models.py`, `backend/tests/{test_store,test_snapshots}.py`.

**Interfaces:** `Job` zawiera wszystkie pola z modelu protokołu.
`JobStore.open(data_dir: Path) -> JobStore`;
`apply_operation(operation_id: str, method: str, params: dict,
mutate: Callable[[sqlite3.Connection], dict]) -> dict`;
`get_job(job_id: str) -> Job`; `recover_interrupted() -> None`.
`SnapshotStore.create(jobs: list[Job], at_seq: int) -> dict`;
`page(cursor: str, limit: int) -> dict`.

- [ ] Testy powtórzenia operacji po ponownym otwarciu bazy, konfliktu parametrów,
  rollbacku błędu, zachowania starych prób, blokady drugiej instancji i odmowy
  otwarcia nowszego schematu.
- [ ] Testy niezmiennej migawki podczas mutacji, limitu 100 rekordów,
  wygaśnięcia po 60 s oraz ograniczenia strony rozmiarem ramki.
- [ ] Uruchomić `backend/.venv/bin/python -m pytest backend/tests/test_store.py backend/tests/test_snapshots.py -q`;
  potwierdzić FAIL.
- [ ] Zaimplementować SQLite z transakcyjnym zapisem operacji i wyniku.
  Krótki identyfikator katalogu rozwiązywać z kontrolą kolizji; nie używać
  surowego URL jako nazwy katalogu. Zapisywać zmiany stanów, a postęp checkpointować.
- [ ] Powtórzyć testy; wymagać PASS.
- [ ] Commit: `feat: persist jobs and idempotent commands`.

## Task 4: scheduler i nadzór nad pracownikiem

**Files:** `backend/src/fetchmunk_backend/{service,supervisor}.py`,
modyfikacja `__main__.py`, `backend/tests/{test_service,test_supervisor}.py`,
`backend/tests/fixtures/worker.py`.

**Interfaces:** `JobService.handle(request: dict) -> dict`,
`WorkerSupervisor.start(request: WorkerRequest) -> None`,
`stop(reason: str, grace_seconds: float = 5.0) -> None`.
Supervisor dostarcza `WorkerEvent` i `WorkerResult` do serwisu.
Serwis jest jedynym miejscem rozstrzygania stanów i rewizji.

- [ ] Testy FIFO, pojedynczego pracownika, anulowania, retry z nową próbą,
  wyścigu cancel/complete, ignorowania starej próby, częściowego sukcesu,
  pustego wyniku, samych pominiętych plików i braku automatycznego wznowienia.
- [ ] Testy procesowe: EOF GUI, zabicie koordynatora, zawieszony worker,
  zatrzymanie po 5 s, wolny odbiorca i brak osieroconego procesu.
- [ ] Uruchomić `backend/.venv/bin/python -m pytest backend/tests/test_service.py backend/tests/test_supervisor.py -q`;
  potwierdzić FAIL.
- [ ] Zaimplementować wszystkie komendy v1 poza `auth.*`; te zwracają
  `dependency_unsupported`. Ogłaszać `capabilities: ["jobs"]`.
  Pozwolić na odczyty podczas transferu i ograniczyć postęp do 4 zdarzeń/s.
- [ ] Przy utracie kanału rodzica zatrzymać pracownika przez niezależny
  monitor potoku. Nie opierać tego wyłącznie na obsłudze wyjątków rodzica.
- [ ] Powtórzyć testy; następnie uruchomić cały zestaw backendu.
- [ ] Commit: `feat: coordinate downloads and recover interrupted jobs`.

## Task 5: klient Swift i używalne GUI

**Files:** `macos/Package.swift`, wszystkie pliki `macos/Sources/Fetchmunk`
z drzewa powyżej, `macos/Tests/FetchmunkTests/{BackendClientTests,AppModelTests}.swift`.

**Interfaces:** `actor BackendClient` z
`start(executableURL: URL) async throws`,
`request(method: String, params: JSONValue) async throws -> JSONValue`,
`events: AsyncStream<BackendEvent>`, `shutdown() async throws`.
`JSONValue`, `BackendEvent`, `Job` to typy `Codable` w `ProtocolModels.swift`.
`@MainActor AppModel` utrzymuje widoczne zadania i stan połączenia,
nie rozstrzyga wyników silnika.

- [ ] Testy dekodowania ramek, rozłączenia, handshake po 10 s, timeoutu komendy
  po 5 s, użycia tego samego operation_id po timeout, ignorowania starej rewizji,
  migawki przy równoległych zdarzeniach i bufora 1000 identyfikatorów.
- [ ] Uruchomić `swift test --package-path macos`; potwierdzić FAIL.
- [ ] Zaimplementować klienta z asynchronicznymi potokami i bez `waitUntilExit`
  na głównym wątku. Ścieżkę procesu ustalać z bundle, nie z PATH ani cwd.
- [ ] Zaimplementować pole URL, wybór katalogu, listę zadań, liczniki,
  anulowanie, retry, „Kontynuuj kolejkę” i „Pokaż pliki”. Brak procentu
  całej galerii, brak przycisków logowania i aktualizacji w tym buildzie.
- [ ] Zaimplementować menu, ponowne otwarcie okna i potwierdzenie zakończenia
  przy aktywnym zadaniu. Limit shutdown GUI: 10 s.
- [ ] Powtórzyć `swift test --package-path macos`; wymagać PASS.
- [ ] Ręcznie sprawdzić klawiaturę, VoiceOver, jasny/ciemny wygląd, 1000 zadań
  i katalog ze spacjami/Unicode. Zapisać rzeczywiste wyniki, nie deklaracje.
- [ ] Commit: `feat: add native macOS download interface`.

## Task 6: kompletna lokalna aplikacja i DMG

**Files:** `packaging/Info.plist`, `scripts/{build_macos.sh,smoke_bundle.py}`,
`docs/verification/first-build.md`, modyfikacja `README.md`, `.gitignore`.

**Interfaces:** `scripts/build_macos.sh` tworzy
`dist/Fetchmunk.app` oraz `dist/Fetchmunk-local-arm64.dmg`.
`scripts/smoke_bundle.py --app PATH` kończy się kodem 0 tylko po sprawdzeniu
handshake, prawdziwego pobrania kontrolnego i zakończenia procesów.

- [ ] Napisać smoke test uruchamiający backend z bundle w tymczasowym cwd,
  z ograniczonym PATH i bez zależności od repozytorium.
  Uruchomić go przed buildem; oczekiwać czytelnego błędu braku artefaktu.
- [ ] Zbudować Swift release i backend onedir; umieścić kod, biblioteki i zasoby
  w poprawnych lokalizacjach bundle. Podpisać elementy od wewnątrz ad hoc.
  Nie używać `codesign --deep` jako zamiennika prawidłowego podpisywania.
- [ ] Utworzyć DMG przez `hdiutil`; oznaczyć go jako lokalny build bez notaryzacji.
- [ ] Uruchomić smoke test, `codesign --verify --deep --strict dist/Fetchmunk.app`
  i aplikację z Findera. Sprawdzić działanie po przeniesieniu `.app`.
- [ ] Zmierzyć czas startu, rozmiar DMG i `.app`, pamięć wszystkich procesów
  w bezczynności i podczas transferu. Zapisać sprzęt, system, wersje i metodę.
- [ ] Test minimalnego macOS i czystej maszyny wpisać jako „niewykonany”,
  jeśli środowisko nie jest dostępne. Brak notaryzacji nie może być opisany
  jako gotowy instalator dla publicznego użytkownika.
- [ ] Uzupełnić README: co działa, czego brak, jak budować i testować.
- [ ] Commit: `build: package self-contained macOS application`.

## Końcowa weryfikacja i przegląd

- [ ] `backend/.venv/bin/python -m pytest backend/tests -q` — PASS.
- [ ] `swift test --package-path macos` — PASS.
- [ ] `scripts/build_macos.sh` — `.app` i lokalny DMG.
- [ ] `python3 scripts/smoke_bundle.py --app dist/Fetchmunk.app` — PASS.
- [ ] `git diff --check` — brak błędów.
- [ ] Przegląd całej zmiany: protokół, cykl życia procesów, sekrety,
  przypadki awarii, komplet zależności i brak nieuzgodnionych funkcji.
- [ ] Raport końcowy z linkiem do lokalnego artefaktu i listą niewykonanych
  kontroli. Publiczny release pozostaje osobnym etapem.

## Samokontrola planu

- Interfejsy adaptera → supervisor → service → Swift mają jawne typy i właścicieli.
- Model protokołu, limity i timeouty pochodzą ze specyfikacji.
- Pięć klas ryzyka z Review Focus ma przypisane testy.
- Logowanie, aktualizacje, publiczne podpisy i inne systemy są jawnie poza tym
  etapem, a nie pominięte w deklaracji gotowego MVP.
- Minimalny system i wydajność wymagają pomiaru; lokalny toolchain nie stanowi
  dowodu zgodności.

## Stan wykonania 2026-10-20

Lokalna aplikacja i DMG zostały zbudowane i uruchomione. Oryginalne checklisty powyżej pozostają zapisem planu; rzeczywiste wyniki, odstępstwa oraz niewykonane testy manualne znajdują się w [raporcie weryfikacji](../../verification/first-build.md). Nie wszystkie kontrole jakości publicznego wydania zostały wykonane.
