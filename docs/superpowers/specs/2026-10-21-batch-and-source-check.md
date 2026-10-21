# Alfa0.3.0 — wiele linków i sprawdzanie źródła

Użytkownik poprosił o plan150 zadań, zgodę in blanco, końcowy commit/push oraz
folder z działającą paczką. Roadmapa obejmuje dalsze wydania; ta sesja dostarcza
pierwszy spójny etap01–50. Pozostałe zadania zostają jawnie zaplanowane.

## Kontrakt

jobs.create_many params: operation_id, urls:[string], destination:absolutePath.
Max100 wejściowych adresów, każdy <=16384 znaków, suma UTF-8<=524288.
Walidacja wspólna z jobs.create: HTTP/HTTPS, host, brak danych logowania,
białych/control znaków, NUL i niepoprawnego portu. GUI usuwa puste wiersze,
trimuje brzegi; backend wymaga już poprawnych adresów. Duplikaty identycznych
stringów pomijamy, kolejność pierwszych wystąpień zachowana. Zwracamy
{jobs:[{job_id,revision}],created_count,duplicate_count}. Jeden commit,
cała paczka albo nic; eventy i worker dopiero po zatwierdzeniu. Brak domyślnego
rozpoznawania URL przez sieć podczas dodawania. Capability batch_jobs.

sources.inspect params:url. Walidacja jak wyżej. Wynik {supported:bool,
category:string|null,subcategory:string|null}. Dopasowanie wzorców ekstraktorów
gallery-dl bez iterowania ekstraktora, zapytań HTTP i odczytu cookies/config
użytkownika. Capability source_inspection. To deklaracja rozpoznania formatu
adresu, nie obietnica dostępności materiału ani obsługi sesji.

## GUI

Arkusz wielu linków: TextEditor, jawny Wklej, liczba unikalnych i duplikatów,
numery nieprawidłowych wierszy, katalog docelowy. Model zachowuje operation_id,
urls i destination po timeout/rozłączeniu; ponowienie wysyła to samo. Edycja
jest zablokowana do rozstrzygnięcia; nie oferujemy porzucenia niepewnej operacji.
Sukces odświeża globalne liczniki i stronę all bez wyszukiwania.

Przycisk Sprawdź obok pojedynczego adresu wywołuje źródła wyłącznie na żądanie.
Zmiana tekstu unieważnia odpowiedź poprzedniego sprawdzenia. Brak automatycznego
czytania schowka/sesji. Pokazujemy, że kontrola dotyczy formatu adresu.

## Błędy i weryfikacja

Rozpoznajemy tylko potwierdzone typy wyjątków przypiętej wersji gallery-dl.
HTTP403 nie oznacza automatycznie logowania. Nigdy nie kopiujemy surowych
komunikatów, URL ani nagłówków do diagnostyki. Testy kontrolowane, bez kont.
Nowa paczka0.3.0 przechodzi Python/Swift/metadata, smoke .app i DMG oraz CI.
Nie twierdzimy, że zaliczono testy żywych źródeł czy notaryzację.
