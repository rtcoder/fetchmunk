# Fetchmunk — propozycja MVP i architektury

Data: 2026-10-20. Status: projekt do przeglądu, nie opis działającego kodu.

## Cel i zatwierdzone decyzje

Użytkownik instaluje aplikację, wkleja link, klika „Pobierz” i otrzymuje pliki.
Nie instaluje Pythona, nie uruchamia terminala i nie edytuje konfiguracji.

Zatwierdzony stos:

- macOS jako pierwsze wydanie: Swift, SwiftUI i potrzebne integracje AppKit.
- Windows i Linux później: C# i Avalonia, wspólna implementacja GUI.
- Wspólny lokalny backend Python, korzystający z gallery-dl.
- Brak własnych ekstraktorów i własnego silnika pobierania.

Pozostałe decyzje w tym dokumencie są propozycją. Wybór stosu nie zatwierdza
automatycznie szczegółów MVP.

## Zakres pierwszego wydania

1. Jedno główne okno: pole adresu, katalog docelowy, przycisk „Pobierz”,
   lista zadań oraz dostęp do ustawień.
2. Jeden adres HTTP/HTTPS na zadanie. Wklejenie nie uruchamia sieci automatycznie.
3. Trwała kolejka FIFO; jeden aktywny proces pobierania.
4. Historia, anulowanie, ponowienie i otwarcie katalogu wynikowego.
5. Wyniki: ukończono, ukończono częściowo, nic nie znaleziono, błąd,
   anulowano albo przerwano.
6. Licznik plików i postęp bieżącego pliku, gdy dostępny.
7. Czytelne błędy z akcją użytkownika.
8. Wykorzystanie sesji przeglądarki dla uzgodnionych i przetestowanych źródeł.
9. Podpisany, notaryzowany DMG oraz aktualizowanie kompletnej aplikacji.

Poza MVP: pauza, harmonogramy, pobieranie po zamknięciu aplikacji,
przeglądarka multimediów, miniatury wymagające dodatkowej ekstrakcji,
edytor dowolnej konfiguracji gallery-dl, yt-dlp, spotDL, wtyczki,
konta Fetchmunk, synchronizacja i usługi chmurowe.

Windows i Linux nie są częścią pierwszego wydania. Współdzielenie backendu
przygotowuje te platformy, ale nie oznacza ich przetestowania.

## Przebieg użytkownika

### Pierwsze uruchomienie

- Aplikacja pokazuje główne okno bez kreatora.
- Domyślny katalog: systemowy katalog pobrań z podkatalogiem `Fetchmunk`.
  GUI ustala go przez API systemowe; backend otrzymuje absolutną ścieżkę.
- GUI uruchamia backend i uzgadnia wersję protokołu.
- Awaria startu daje komunikat i możliwość ponowienia; pole pobierania
  pozostaje nieaktywne do uzyskania gotowości.
- Brak odczytu cookies, pobierania runtime i aktualizacji blokującej start.

### Dodawanie i pobieranie

- „Pobierz” tworzy zadanie z kopią wybranego katalogu docelowego.
- Zmiana domyślnego katalogu nie przenosi wcześniejszych zadań.
- Backend sprawdza format URL, obsługę przez ekstraktor i możliwość zapisu.
- Zadanie przechodzi przez kolejkę, odczyt źródła i pobieranie.
- GUI pokazuje np. „Pobrano 18, pominięto 2”. Nie wymyśla całkowitej liczby.
- W MVP nie wykonujemy pełnego skanowania galerii tylko po to, aby uzyskać
  mianownik paska postępu.
- „Pokaż pliki” otwiera właściwy katalog w Finderze. Backend zwraca ścieżkę,
  a GUI wykonuje akcję systemową.

### Nazwy i ponowienia

Każde zadanie dostaje własny katalog pod wybraną lokalizacją, z krótkim
identyfikatorem zadania. W nim gallery-dl zachowuje własne reguły podkatalogów
i nazw. Ponowienie używa tego samego katalogu i archiwum silnika.

Archiwum pobrań jest ograniczone do zadania. Nie obiecujemy globalnej deduplikacji
między różnymi zadaniami. Nie nadpisujemy ukończonych plików wymuszoną opcją.
Pliki `.part` pozostają do ewentualnego wznowienia przez silnik.
Archiwum nie stanowi gwarancji odtworzenia plików usuniętych później ręcznie.

### Zamykanie

Zamknięcie okna na Macu nie kończy aplikacji. Wybranie „Zakończ”, gdy istnieje
aktywne zadanie, pokazuje wybór: wróć albo zatrzymaj i zakończ.
Zadanie otrzymuje stan `interrupted`, a pozostała kolejka zostaje zachowana.
Po ponownym uruchomieniu kolejka wymaga naciśnięcia „Kontynuuj kolejkę”.
Nie wznawiamy transferów bez wiedzy użytkownika.

## Podział odpowiedzialności

```text
SwiftUI / Avalonia
    │ JSON Lines przez stdin/stdout
    ▼
Backend Python — koordynator
    ├── kolejka i maszyna stanów
    ├── SQLite: zadania, próby, ustawienia
    ├── mapowanie wyników i błędów
    └── proces roboczy Python
            └── adapter → gallery-dl
```

GUI prezentuje stan, przechowuje sekrety przez API systemowe i realizuje dialogi,
menu, otwieranie katalogów oraz aktualizację aplikacji. Nie ustala kolejności
zadań, nie interpretuje logów gallery-dl i nie rozstrzyga wyniku pobierania.

Koordynator jest jedynym autorem bazy danych aplikacji. Pracownik używa
oddzielnego archiwum/cache silnika; nie zapisuje bezpośrednio stanu kolejki.
Jedna instancja koordynatora na katalog danych, zabezpieczona blokadą.

Pracownik działa poza procesem koordynatora: zablokowana ekstrakcja nie może
uniemożliwić odczytu kolejki ani anulowania. Kod adaptera nie odtwarza
mechanizmów sieciowych gallery-dl.

GUI uruchamia koordynator bez powłoki. Koordynator uruchamia pracownika.
Zamknięcie potoku przez GUI oznacza zatrzymanie pracownika i zakończenie backendu.
Pracownik musi reagować także na utratę kanału koordynatora; test awarii procesu
rodzica sprawdza, czy transfer nie zostaje osierocony.

Normalne zatrzymanie ma limit 5 sekund; później kończymy proces przymusowo.
Przed wymuszonym zakończeniem nie deklarujemy, że plik został ukończony.
Sposób sygnalizacji jest zależny od systemu i wymaga osobnych testów.

## Dane i odporność

- SQLite i ustawienia: katalog danych aplikacji użytkownika.
- Sekrety: systemowy magazyn, na macOS Keychain. W SQLite tylko niejawny identyfikator.
- Cache gallery-dl: wydzielony katalog, z ograniczonym dostępem. Przed wydaniem
  należy sprawdzić, czy wybrana konfiguracja nie utrwala sesji w postaci jawnej.
- Logi: lokalne, rotowane; maksymalnie 10 MiB łącznie jako budżet projektowy.
- Logi nie zawierają cookies, nagłówków autoryzacji, haseł ani pełnych URL-i.
  URL potrzebny do ponowienia jest prywatną daną zadania, nie diagnostyką.
- Strumienie i logi silnika nie są automatycznie przepisywane do logu aplikacji.
- Nie usuwamy pobranych plików przy anulowaniu ani czyszczeniu historii.
- Po awarii aktywne próby zostają oznaczone `interrupted`. Nie odtwarzamy
  zakończenia tylko na podstawie istnienia pliku na dysku.
- Migrujemy bazę przy aktualizacji z kopią zapasową. Starszy backend odmawia
  zapisu do nieobsługiwanej nowszej wersji schematu.

## Uwierzytelnianie i źródła

Lista źródeł priorytetowych wymaga odpowiedzi użytkownika. Nie deklarujemy
pełnej obsługi logowania do wszystkich serwisów gallery-dl.

Proponowana ścieżka: „Wymagane logowanie” → wybór obsługiwanej przeglądarki
i profilu → świadoma zgoda na użycie sesji → ponowienie.
Wczytanie sesji ograniczamy do domen potrzebnych danemu ekstraktorowi.
Jeżeli ograniczenie nie jest dostępne lub wiarygodne, wymaga to osobnej
decyzji dla tego źródła, zamiast cichego odczytu całego profilu.

W MVP nie przechowujemy własnej kopii całej bazy cookies przeglądarki.
Backend zapamiętuje wyłącznie wybór profilu; odczyt wykonuje pracownik.
Import cookies, formularze haseł i OAuth nie wchodzą automatycznie do zakresu.
Jeżeli priorytetowe źródło ich wymaga, należy dopisać jego konkretny przepływ.

Stan `needs_auth` blokuje dane zadanie, ale nie resztę kolejki.
HTTP 403 sam w sobie nie wystarcza do sklasyfikowania problemu jako logowania.
Nieznana przyczyna daje `access_denied` z uczciwym komunikatem.

## Pakowanie i aktualizacje

Propozycja pierwszego celu: Apple Silicon, macOS 13+. Wersję minimalną
potwierdzamy po próbie pakowania; Intel wymaga odrębnej decyzji.

- Python, adapter, przypięte gallery-dl i zależności są wewnątrz `.app`.
- Propozycja pakowania backendu: PyInstaller `onedir`.
- Build jawnie dołącza dynamiczne ekstraktory, zasoby i certyfikaty TLS.
- Aplikacja nie uruchamia `pip`, nie korzysta z systemowego Pythona ani
  prywatnej konfiguracji gallery-dl użytkownika.
- Backend i GUI są wydawane razem. Brak samodzielnego `gallery-dl --update`.
- Wszystkie wymagane biblioteki i procesy są podpisane; kompletny pakiet
  przechodzi notaryzację i test Gatekeepera po pobraniu.
- Propozycja aktualizatora macOS: Sparkle, podpisane archiwa i statyczny appcast.
  Instalacja aktualizacji dopiero po zatrzymaniu backendu i zamknięciu bazy.
- Aktualizatory Windows/Linux dobieramy na etapie ich wdrożenia.

Licencja produktu nie została zatwierdzona. Wydanie blokuje brak sprawdzenia
zgodności zależności i realizacji obowiązków GPL gallery-dl. Projekt protokołu
nie jest sposobem na automatyczne wyłączenie obowiązków licencyjnych.

## Etapy i kryteria odbioru

1. **Weryfikacja dystrybucji i adaptera:** minimalna `.app` z dołączonym silnikiem
   pobiera publiczną galerię na czystym Macu; odczyt wyniku, anulowanie,
   podpisanie i notaryzacja działają. Mierzymy rozmiar, start i RAM.
2. **Backend i kontrakt:** trwała kolejka, poprawne stany, awaria pracownika,
   przerwanie GUI, powtórzone komendy i odtwarzanie migawki.
3. **GUI macOS:** pełna ścieżka od wklejenia do Findera, obsługa klawiatury,
   VoiceOver, jasny/ciemny motyw i długa historia bez blokowania interfejsu.
4. **Źródła i sesje:** testy uzgodnionych serwisów, wygasła sesja, odmowa dostępu,
   limity, częściowe wyniki i kontrola diagnostyki pod kątem sekretów.
5. **Wydanie:** czysta instalacja bez Pythona, aktualizacja między dwoma
   podpisanymi buildami, zachowanie danych, komplet licencji i źródeł.

W testach logiki używamy kontrolowanego pracownika; testy integracji uruchamiają
prawdziwe gallery-dl na kontrolowanych odpowiedziach HTTP. Testy żywych stron
są osobną kontrolą wydania, bo nie są deterministyczne.

Cele do pomiaru, nie obecne wyniki: gotowe pole adresu do 1 s od startu na
referencyjnym Macu; potwierdzenie komendy do 250 ms bez operacji sieciowej;
aktualizacje postępu najwyżej 4 razy/s; brak cyklicznego odpytywania w bezczynności.
Pomiar RAM obejmuje GUI, backend i wszystkie procesy pomocnicze.

## Fakty i założenia

Sprawdzone 2026-10-20:

- gallery-dl dokumentuje JSON z ekstrakcji, wypisywanie zdarzeń, archiwum pobrań,
  odczyt cookies i wyłączenie domyślnej konfiguracji:
  [opcje CLI](https://gdl-org.github.io/docs/options.html).
- Dokumentacja opisuje `.part`, wznowienie niepełnych transferów i postęp pliku.
  Nie stanowi to gwarancji wznowienia każdego źródła:
  [konfiguracja](https://gdl-org.github.io/docs/configuration.html).
- PyInstaller dołącza interpreter i zależności:
  [pakowanie](https://pyinstaller.org/en/stable/operating-mode.html).
- Sparkle oferuje aktualizacje aplikacji macOS:
  [dokumentacja](https://sparkle-project.org/documentation/).

Protokół, podział procesów, zachowanie kolejki, budżety wydajnościowe i zakres
GUI są projektem Fetchmunk. Nie są funkcjami gwarantowanymi przez gallery-dl.
Adapter do wewnętrznych interfejsów silnika trzeba zweryfikować na przypiętej
wersji. Ten dokument nie zastępuje tej weryfikacji.

Do zatwierdzenia przed realizacją: ten zakres, kontrakt IPC, docelowe komputery,
lista źródeł i wynikający z niej zakres logowania. Licencja i dane do podpisania
muszą być rozstrzygnięte przed dystrybucją zewnętrzną.
