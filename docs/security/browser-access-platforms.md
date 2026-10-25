# Dostęp do sesji przeglądarek — granice platform i projekt konektora

Stan przeglądu źródeł: 2026-10-25. Dokument rozdziela fakty platformowe od proponowanego kontraktu Fetchmunk. To analiza dokumentacji, nie potwierdzenie działania integracji na komputerach użytkowników. Nie odczytywano rzeczywistych profili, cookies ani kluczy.

## Fakty i ograniczenia

**Otwarcie strony w przeglądarce nie przekazuje Fetchmunk jej cookies.** Logowanie w przeglądarce i udzielenie dostępu do sesji to osobne operacje. Wniosek wynika z odrębnych magazynów profilu, kontroli dostępu do plików i zabezpieczeń kluczy opisanych poniżej. Nie istnieje tu uniwersalne uprawnienie systemowe „udostępnij sesję dowolnej aplikacji”.

### macOS

Dostęp do pliku profilu, dostęp do klucza szyfrującego i sterowanie przeglądarką to różne mechanizmy:

- Apple wymienia Safari wśród danych innych aplikacji objętych Full Disk Access. Uprawnienie to ma szeroki zakres; nie jest zgodą ograniczoną do jednej domeny. [Apple: Privacy & Security](https://support.apple.com/guide/mac-help/change-privacy-security-settings-on-mac-mchl211c911f/mac).
- Aplikacja nie może samodzielnie przyznać sobie Full Disk Access przez entitlement lub kod. Użytkownik nadaje je w ustawieniach systemu. Sandbox i sposób dystrybucji nadal wymagają osobnej weryfikacji. [Apple: dostęp do plików](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox).
- Automation dotyczy sterowania innymi aplikacjami. Nie należy przedstawiać go jako uprawnienia do czytania bazy cookies albo Keychain. [Apple: Automation](https://support.apple.com/et-ee/guide/mac-help/mchl07817563/mac).
- Chrome na macOS korzysta z Keychain. Dostęp do bazy cookies nie oznacza automatycznie dostępu do potrzebnego klucza. [Chrome Security Team](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html).

**Wniosek dla Safari:** bez testu podpisanej, dystrybuowanej aplikacji na wspieranej wersji macOS nie deklarujemy automatycznego importu. Chroniony plik oznacza stan wymagający dostępu lub blokadę, a nie automatyczne kierowanie każdego użytkownika po Full Disk Access. Bezpieczny wariant domyślny to import świadomie wybranego pliku cookies. Nie zakładamy, że Safari ma wbudowany eksport w tym formacie.

### Windows

Chrome od wersji 127 wdrażał App-Bound Encryption dla cookies. Mechanizm sprawdza tożsamość aplikacji; uruchomienie innej aplikacji jako ten sam użytkownik nie wystarcza do odszyfrowania. Starsze DPAPI ma inną granicę: zwykle chroni względem użytkownika i komputera, nie samej aplikacji. [Chrome Security Team](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html), [Microsoft: CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

Polityka Chrome dokumentuje, że wyłączenie App-Bound Encryption pogarsza bezpieczeństwo. Fetchmunk nie proponuje zmiany tej polityki, administratora, iniekcji do procesu ani obchodzenia zabezpieczeń. [Chrome Enterprise](https://chromeenterprise.google/policies/application-bound-encryption-enabled/).

**Wniosek:** chroniony profil zwraca `unsupported_protection`; zgoda użytkownika nie zmienia technicznej dostępności. Nie przenosimy automatycznie wniosków o Chrome na wszystkie wersje Edge, Brave czy Chromium. Wymagany jest test konkretnego produktu, wersji i formatu. Plik wyeksportowany przez użytkownika jest alternatywą, nie gwarancją akceptacji sesji przez serwis.

### Linux

Chrome używa systemowego magazynu, np. KWallet lub gnome-libsecret. Chromium dokumentuje różne magazyny i możliwość konfiguracji bez szyfrowania; nie należy zakładać jednego mechanizmu dla każdej dystrybucji. Fetchmunk nie przełącza przeglądarki na taki tryb. [Chrome Security Team](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html), [Chromium: Linux Password Storage](https://chromium.googlesource.com/chromium/src/+/970ad57b01aa23246161475ff50fe717ef65d6e1/docs/linux/password_storage.md).

Secret Service działa w sesji użytkownika; obiekty mogą być zablokowane, odblokowanie może wymagać systemowego promptu, a blokada może wrócić w trakcie działania. Brak usługi, brak wpisu i zablokowany wpis nie są tym samym. Specyfikacja wskazanego `latest` ma status draft. Aktualny KWallet opisuje również migrację implementacji do Secret Service; adapter powinien wykrywać możliwości, nie zgadywać ich po nazwie pulpitu. [Secret Service](https://specifications.freedesktop.org/secret-service/latest-single/), [KDE KWallet](https://github.com/KDE/kwallet).

### Firefox i format pliku

Mozilla dokumentuje cookies w `cookies.sqlite`, oddzielnie od plików haseł. To nie jest obietnica stabilności schematu ani publiczny interfejs eksportu. [Mozilla: profile](https://support.mozilla.org/en-US/kb/profiles-where-firefox-stores-user-data).

Implementacja yt-dlp pokazuje osobne ścieżki dla Firefox, Safari i przeglądarek Chromium oraz obsługę różnic profili i schematów. yt-dlp jest zatwierdzonym dodatkowym silnikiem Fetchmunk. Jego FAQ dokumentuje import Mozilla/Netscape i ostrzega, że eksport z całej przeglądarki może obejmować wszystkie serwisy. [Kod yt-dlp](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/yt_dlp/cookies.py), [FAQ yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).

## Proponowany kontrakt Fetchmunk

Poniższe punkty są projektem, nie opisem gotowej funkcji:

1. Konektor określa platformę, przeglądarkę, profil i zatwierdzony zakres domen. Wykrywanie dostępności nie czyta wartości cookies przed zgodą.
2. Jeden czytelny ekran zgody w Fetchmunk wyjaśnia źródło, zakres, użycie oraz przechowywanie sesji. System może niezależnie pokazać własne okno Keychain lub odblokowania portfela; nie obiecujemy jednego kliknięcia na wszystkich platformach. Zgoda nie obejmuje nowych domen ani innego profilu.
3. Odczyt uruchamia się wyłącznie na wyraźne żądanie. Zebrany zakres trafia do wspólnej warstwy sesji, bez surowych wartości w GUI, IPC diagnostycznym lub logach. Jeśli technika wymaga chwilowego odczytu szerszej bazy, należy ujawnić to przed zgodą i nie utrwalać ani przekazywać dalej nadmiarowych rekordów.
4. Import wybranego pliku jest wspólną alternatywą. Walidujemy format, rozmiar i domeny; odrzucamy niepasujące rekordy. Plik źródłowy może pozostać jawnym sekretem poza Fetchmunk — aplikacja nie obiecuje jego bezpiecznego usunięcia ani nie kasuje go bez decyzji użytkownika.
5. Nie obchodzimy App-Bound Encryption, TCC, sandboxa ani kontroli portfela. Nie uruchamiamy przeglądarki z osłabionymi zabezpieczeniami.

| Stan konektora | Znaczenie i działanie |
| --- | --- |
| `ready` | Mechanizm dostępny; nie oznacza ważnego zalogowania w serwisie. |
| `consent_required` | Brak zgody Fetchmunk na wskazany zakres; brak odczytu. |
| `permission_required` / `denied` | Dostęp wymaga decyzji systemowej lub został odrzucony; bez pętli promptów. |
| `locked` | Portfel wymaga odblokowania; ponowienie po świadomej akcji. |
| `unavailable` | Brak usługi lub sesji systemowej; zachowanie danych i opcja importu. |
| `profile_missing` | Nie ma wybranego profilu; wybór innego źródła. |
| `busy` | Plik chwilowo niedostępny; bez zabijania przeglądarki. |
| `unsupported_protection` / `unsupported_format` | Zabezpieczenie lub format nieobsługiwany; import pliku lub inne wspierane źródło. |
| `invalid_session` | Import się udał, lecz sesja wygasła albo serwis ją odrzucił; ponowne połączenie. |

## Klucz Fetchmunk a klucz przeglądarki

To dwa odrębne sekrety. **Propozycja:** losowy 256-bitowy klucz główny Fetchmunk w systemowym magazynie (macOS Keychain, Windows Credential Manager, Linux Secret Service/KWallet przez wspierany adapter). Dane sesji szyfrowane AES-256-GCM, z unikalnym nonce dla każdego szyfrowania danym kluczem, uwierzytelnionymi metadanymi wersji/identyfikatora oraz sprawdzaniem tagu przed użyciem. Klucza nie zapisujemy obok zaszyfrowanej bazy, w konfiguracji, repozytorium ani logach. Brak bezpiecznego magazynu wyłącza trwały zapis; bez cichego fallbacku do jawnego pliku.

Adapter rozróżnia `found`, `missing`, `locked`, `denied`, `unavailable` i `error`. Apple odróżnia `errSecItemNotFound` od `errSecInteractionNotAllowed`; drugi kod nie jest dowodem braku klucza ani jednoznacznym dowodem blokady. Microsoft `CredReadW` odróżnia `ERROR_NOT_FOUND` od `ERROR_NO_SUCH_LOGON_SESSION`. Secret Service ma osobne wyniki wyszukiwania locked/unlocked. [Apple: missing](https://developer.apple.com/documentation/security/errsecitemnotfound), [Apple: interaction](https://developer.apple.com/documentation/security/errsecinteractionnotallowed), [Microsoft: CredReadW](https://learn.microsoft.com/windows/win32/api/wincred/nf-wincred-credreadw), [Secret Service](https://specifications.freedesktop.org/secret-service/latest-single/).

Zatwierdzone zachowanie po utracie klucza: potwierdzony `missing` przy istniejącym szyfrogramie unieważnia i usuwa wyłącznie nieczytelne zaszyfrowane profile poświadczeń. Flaga `last_reset` informuje o resecie w bieżącej sesji; GUI wyraźnie informuje o konieczności ponownego połączenia kont. Nie usuwa się historii, ustawień ani plików źródłowych użytkownika. Dopiero po takim resecie można utworzyć nowy klucz dla nowych sesji. Odmowa, blokada, niedostępność usługi lub inna awaria NIGDY nie powodują usunięcia danych ani rotacji/resetu; wymagają ponowienia po usunięciu przyczyny. Błąd integralności zgłasza osobny kod credential_lost i usuwa tylko nieczytelny rekord, zgodnie z zatwierdzonym wymaganiem usuwania danych, których nie można odszyfrować. Oznacza to także utratę rekordu po podmianie klucza na inny prawidłowo sformatowany klucz; nie próbujemy zgadywania ani odzyskiwania. Magazyn systemowy i AES-GCM chronią dane w spoczynku; nie gwarantują ochrony przed kompromitacją procesu Fetchmunk albo aktywnej sesji systemowej.

## Co trzeba jeszcze sprawdzić

Testy na wydawanych binariach i sztucznych profilach: podpis/tożsamość procesu oraz helpera na macOS, Safari/TCC, Chrome App-Bound Windows, Firefox i kontenery, różne usługi Linux i pakiety sandboxowane. Osobno testować anulowanie promptu, ponowną blokadę, brak klucza przy istniejącej bazie, uszkodzony tag GCM i cofnięcie zgody. Sama lektura dokumentacji nie potwierdza wsparcia tych kombinacji.

## Stan wdrożenia 0.4.0

Implementacja ma wspólny BrowserConnector z polityką sys.platform i natywnymi
backendami klucza: Keychain, WinVault, SecretService. Linux bez SecretService
odmawia zapisu; brak osobnego fallbacku do starszego KWallet. Konserwatywnie
blokujemy bezpośredni import Chrome/Edge/Brave na Windows do czasu weryfikacji
formatu. Import zgłasza bezpieczny kod ogólny, jeśli upstream nie dostarczy
jednoznacznego typu przyczyny; powyższa pełna tabela pozostaje docelowym kontraktem.
Lista profili nie czyta klucza; utrata jest wykrywana przy użyciu/zapisie.
Nie zweryfikowano rzeczywistych profili żadnej przeglądarki ani Windows/Linux.
