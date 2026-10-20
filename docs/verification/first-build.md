# Pierwszy lokalny build — 2026-10-20

Działa samodzielna aplikacja SwiftUI dla macOS arm64, z Pythonem i gallery-dl wewnątrz bundle. Nie jest to jeszcze publiczne wydanie pełnego MVP.

## Środowisko i pomiary

- Apple M4 Max, 128 GiB RAM, macOS 27.0.1 (26A434).
- Python 3.13.16, python-build-standalone build 20261013; gallery-dl 1.32.17; PyInstaller 6.22.3. SHA-256 libpython zapisany w `packaging/toolchain.json`.
- `du -sh`: aplikacja około 26 MiB, DMG około 15 MiB.
- Handshake zamrożonego backendu: 0,501 s z katalogu builda, 0,328 s z zamontowanego DMG. Pomiar od uruchomienia procesu do odebrania hello; nie jest pomiarem czasu do narysowania GUI ani benchmarkiem zimnego startu.
- Bezczynność po otwarciu GUI z jednym ukończonym zadaniem: suma RSS GUI + backend 160,1 MiB; pojedyncza próbka `ps`, CPU 0,0%. RSS może podwójnie liczyć współdzielone strony. Pamięci podczas długiego transferu jeszcze nie zmierzono.

## Potwierdzone

- 45 testów backendu PASS: rzeczywisty adapter gallery-dl z kontrolowanymi odpowiedziami HTTP, częściowy wynik, pomijanie, błędy, literalne ścieżki, IPC, SQLite/idempotencja, migawki, kolejka i cykl życia procesów.
- 11 testów Swift PASS: ramki, handshake, rozłączenie, równoległe zapisy, timeout/retry, rewizje, bufor zmian i deadline zamknięcia.
- Regresja ręcznego retry po dwóch timeoutach została dodatkowo sprawdzona przez chwilowe przywrócenie nowego UUID: test wtedy FAIL; po przywróceniu poprawki PASS.
- Smoke test finalnego bundle: hello, inicjalizacja, prawdziwe pobranie z kontrolnego serwera HTTP, zgodność bajtów, brak duplikatu operacji, poprawne zakończenie. Tymczasowy cwd ze spacjami/Unicode, `PATH=/usr/bin:/bin`, bez konfiguracji użytkownika.
- Ten sam smoke test PASS bezpośrednio z DMG zamontowanego tylko do odczytu. Potwierdza niezależność od pierwotnej ścieżki `.app`.
- `codesign --verify --deep --strict`: PASS. Podpis ad hoc, nie Developer ID.
- Wszystkie 5 plików Mach-O w bundle mają deployment target <= macOS 13. Runtime Homebrew wymagający macOS 27 został odrzucony i zastąpiony przenośnym runtime. Kontrola jest częścią builda.
- GUI uruchomione: stan „Silnik gotowy”, zachowana historia po restarcie. W poprzednim przebiegu GUI pobrało lokalny plik PNG i odrzuciło nieprawidłowy URL. Ciemny wygląd sprawdzony wizualnie, pole URL obsłużone klawiaturą.

## Wynik przeglądu i decyzje wykonawcze

Przegląd wykazał cztery istotne problemy; wszystkie zostały zaadresowane:

1. Ścieżki wybrane przez GUI traktujemy literalnie. Adapter wyłącza rozwijanie zmiennych tylko dla dwóch własnych ścieżek: wyjścia i archiwum. Testy obejmują `$HOME`, `${HOME}`, Unicode, spacje i metaznaki. Adapter działa w osobnym procesie i przywraca nadpisaną funkcję silnika.
2. Nierozstrzygnięte utworzenie zadania zachowuje parametry i operation_id. Kolejne kliknięcie sprawdza poprzednie zgłoszenie, zamiast tworzyć nowe. Komunikat wyjaśnia to użytkownikowi.
3. Deadline zamknięcia 10 s obejmuje wysłanie komendy, timeouty i oczekiwanie na zakończenie.
4. Obecna implementacja migawek nadal kopiuje historię do pamięci. Lokalny build ma jawny limit 1000 zadań, egzekwowany przed utworzeniem nowego zadania oraz przy otwieraniu większej bazy. Powtórzenie zatwierdzonej operacji nadal działa na limicie. Przed publicznym wydaniem potrzebne są migawki na dysku, SQL dla schedulera i zarządzanie historią. Nie usuwamy historii automatycznie.

Backend jest zagnieżdżonym PyInstaller BUNDLE w `Contents/Helpers/FetchmunkBackend.app`; płaski onedir nie przechodził poprawnej walidacji podpisu zasobów. Podpisywane są pliki i pakiety od wewnątrz; `--deep` służy wyłącznie weryfikacji.

## Niewykonane lub poza zakresem

- Uruchomienie na rzeczywistym macOS 13, Intel i czystym komputerze bez narzędzi deweloperskich. Kontrola Mach-O nie zastępuje tych testów.
- Pełne testy żywych serwisów, sesji/cookies i źródeł wymagających logowania. Brak GUI uwierzytelniania; `auth.*` zwraca `dependency_unsupported`.
- VoiceOver z odsłuchem, jasny motyw, ręczny test 1000 wierszy oraz pomiar pamięci podczas transferu. Drzewo dostępności widoczne, ale nie stanowi pełnego audytu.
- „Pokaż pliki” wywołane w GUI; wizualne potwierdzenie Findera nie powiodło się z powodu błędu ScreenCaptureKit.
- Publiczna licencja Fetchmunk, komplet notices i obowiązków dystrybucji zależności, Developer ID, hardened runtime/notaryzacja oraz aktualizacje — wymagane przed publicznym wydaniem.
- C#/Avalonia i dostosowanie backendu do Windows/Linux nie zostały zaimplementowane.

Artefakty lokalne: `dist/Fetchmunk.app`, `dist/Fetchmunk-local-arm64.dmg`. Źródła na gałęzi `codex/macos-first-build`; bez publikacji ani merge do głównej gałęzi.
