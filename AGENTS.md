# Fetchmunk — informacje dla agentów

## Czym jest ten projekt

Fetchmunk to planowana aplikacja desktopowa do pobierania galerii i mediów z internetu, korzystająca z **gallery-dl jako silnika pobierania**.

Obietnica produktu: **instalujesz aplikację, wklejasz link, klikasz „Pobierz” i masz pliki**.

Odbiorcą jest zwykły użytkownik, który nie chce obsługiwać terminala, instalować Pythona, konfigurować Dockera ani pisać plików JSON. Wygoda instalacji i pierwszego pobrania jest równie ważna jak sam interfejs.

Repozytorium: https://github.com/rtcoder/fetchmunk — publiczne.

## Ustalony kierunek

- Nie piszemy własnego silnika pobierania ani własnych ekstraktorów dla stron. Wykorzystujemy gallery-dl.
- Fetchmunk odpowiada za doświadczenie użytkownika: instalację, interfejs, konfigurację silnika, zarządzanie zadaniami i prezentację wyników oraz błędów.
- Pierwsza wersja powstaje na macOS. Windows i Linux są kolejnym etapem.
- Podstawowa ścieżka działania ma działać bez ręcznych konfiguracji i instalowania zależności przez użytkownika.
- Ustawienia domyślne mają wystarczać do typowego pobierania. Opcje zaawansowane nie powinny utrudniać pierwszego użycia.
- Interfejs ma być estetyczny, czytelny i dopracowany. Sam formularz uruchamiający komendę CLI nie realizuje ambicji projektu.
- Komunikaty o problemach mają mówić, co się stało i co użytkownik może zrobić. Surowe logi mogą być dostępne jako szczegóły diagnostyczne.

## Dlaczego powstaje Fetchmunk

Istnieją już GUI korzystające z gallery-dl, lecz według przeglądu użytkownika nie zapewniają oczekiwanego doświadczenia „klik i masz”:

- GalleryDL Beyond: brak gotowego buildu na macOS.
- gallery-dl GUI od NaxonM: brak gotowych buildów.
- GDownloader: nieodpowiadający użytkownikowi wygląd i konieczność ręcznej konfiguracji; ciekawa obsługa dodatkowych silników.
- Media Downloader: problem z buildem na Maca; interesujący system wtyczek.
- gdluxx: przydatne opcje, lecz wdrożenie webowego GUI i konfiguracja środowiska stanowią próg wejścia.

To obserwacje z rozmowy inicjującej projekt, a nie stale aktualizowany audyt konkurencji. Przewagą Fetchmunk ma być dopracowany produkt gotowy do użycia przez osobę nietechniczną.

## Kandydaci do zakresu — jeszcze nie zatwierdzona specyfikacja

- Kolejka pobierania i historia zadań.
- Czytelny postęp i możliwość zarządzania zadaniami.
- Wybór katalogu docelowego.
- Wygodna obsługa konfiguracji i uwierzytelniania wymaganych przez gallery-dl.
- Przygotowanie silnika i jego aktualizacje bez ręcznych komend.
- Gotowe pakiety instalacyjne dla obsługiwanych systemów.

Obsługa yt-dlp, spotDL oraz system wtyczek to ewentualne przyszłe rozszerzenia, a nie zatwierdzony zakres pierwszej wersji.

## Zatwierdzony stos i podział odpowiedzialności

Decyzja z 2026-10-20:

- **macOS:** Swift i SwiftUI; AppKit tam, gdzie wymaga tego integracja z systemem.
- **Windows i Linux:** C# i Avalonia, ze wspólną implementacją GUI dla obu systemów.
- **Wspólny backend:** Python, niezależny od frameworków GUI, korzystający z gallery-dl jako silnika.
- Frontendy odpowiadają za prezentację i integracje systemowe. Wspólną logikę zadań oraz integrację z gallery-dl utrzymujemy w backendzie, bez powielania jej w Swift i C#.
- Backend działa lokalnie i jest dostarczany wraz z aplikacją, interpreterem Pythona i wymaganymi zależnościami. Użytkownik nie instaluje środowiska osobno.
- Wybór stosu jest zatwierdzony, ale nie oznacza istniejącej implementacji ani zatwierdzenia szczegółowego MVP.

## Co pozostaje do ustalenia

Pozostają do ustalenia szczegóły architektury: protokół komunikacji frontendów z backendem, model procesów, sposób integracji z gallery-dl, przechowywanie danych oraz model dystrybucji i aktualizacji. Nie ustalono licencji, monetyzacji, minimalnych wersji systemów, obsługiwanych architektur procesora ani szczegółowego MVP i listy testowanych źródeł.

Nie traktuj propozycji z tego pliku jako istniejącej implementacji lub zatwierdzonego planu. Przed implementacją uzgodnij zakres i kluczowe decyzje techniczne z użytkownikiem. Nie wybieraj technologii wyłącznie dlatego, że jest popularna lub łatwa do szybkiego prototypowania — oceń instalację, rozmiar aplikacji, integrację z silnikiem i utrzymanie na docelowych platformach.

## Zasady pracy

- Zachowuj gallery-dl jako źródło logiki pobierania; unikaj dublowania jego funkcjonalności.
- Nie zakładaj, że funkcje takie jak pauza, wznowienie lub procentowy postęp są jednakowo dostępne dla wszystkich źródeł. Najpierw zweryfikuj możliwości silnika.
- Nie dodawaj nieuzgodnionych funkcji, kont, usług chmurowych czy dodatkowych silników pobierania.
- Nie zapisuj cookies, tokenów, haseł ani prywatnej konfiguracji użytkownika w repozytorium lub logach diagnostycznych.
- Rozróżniaj funkcje planowane i działające w kodzie oraz dokumentacji.
- Sprawdzaj zmiany odpowiednio do ich zakresu. Informuj konkretnie, co zostało zweryfikowane, a czego nie sprawdzono.
- Z użytkownikiem komunikuj się po polsku, bezpośrednio i technicznie precyzyjnie. Najpierw wynik lub konkret, potem potrzebny kontekst. Bez zbędnych wstępów i korporacyjnego języka.
