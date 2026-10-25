# Katalog ekstraktorów dostarczonych silników

Wygenerowano z przypiętych zależności backendu: **gallery-dl 1.32.17 — 1035 klas ekstraktorów**, **yt-dlp 2026.10.21 — 1754 klasy ekstraktorów**. JSON jest formatem maszynowym, TXT zawiera ten sam katalog do przeglądania. Liczba klas nie oznacza liczby serwisów: jeden serwis może mieć wiele ekstraktorów.

Każdy rekord zawiera identyfikator, klasę, moduł, wzorce URL i dostępne przykłady, korzenie oraz domeny zaobserwowane w tych przykładach/korzeniach. Gallery-dl używa nazwy klasy jako jednoznacznego ID i dodatkowo podaje kategorię/podkategorię; yt-dlp podaje `IE_NAME`. Przykłady są deklaracjami/testowymi URL-ami silnika, nie odczytem historii przeglądarki.

**To nie jest pełna enumeracja domen ani gwarancja sprawnego pobierania.** Wzorce zawierają alternatywy, wildcardy i serwisy samo-hostowane. GenericIE może przyjmować adresy spoza zestawu przykładów. Przykłady mogą być nieaktualne; nie są testowane przez sieć. Wpis bez przykładu nadal pozostaje w katalogu. Tabela nie deklaruje, że każda funkcja silnika została wystawiona w GUI Fetchmunk.

Regeneracja z katalogu repozytorium, po przygotowaniu backendowego środowiska z przypiętymi zależnościami:

```sh
backend/.venv/bin/python scripts/export_supported_sources.py
backend/.venv/bin/python -m unittest discover -s scripts/tests -p test_source_export.py
```

Skrypt importuje wyłącznie metadane klas z zainstalowanych pakietów, bez tworzenia instancji ekstraktorów, ładowania konfiguracji użytkownika ani wykonywania pobrań. Nie uruchamia przeglądarek i nie czyta cookies. Pełne klasy yt-dlp są ładowane zamiast wersji lazy, aby zachować URL-e testowe. Deterministyczne ziarno generatora losowego stabilizuje przykłady wybierane przez niektóre moduły przy imporcie; wcześniejszy stan generatora jest przywracany. Uruchamiaj generator jako osobny proces, przed importowaniem silników w tym procesie.

Eksport nie zawiera znacznika czasu. Sortowanie rekordów i pól listowych pozwala porównywać zmiany pomiędzy wersjami. Test porównuje cały wygenerowany katalog z zapisanymi plikami i blokuje połączenia socket podczas zbierania danych. Po aktualizacji silnika należy ponownie wygenerować pliki i zaktualizować wersje/liczby w tym README.
