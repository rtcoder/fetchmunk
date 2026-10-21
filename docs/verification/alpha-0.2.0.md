# Fetchmunk 0.2.0 — weryfikacja 2026-10-21

Wykonano lokalną część planu `docs/superpowers/plans/2026-10-21-next-50.md`.
Nie dodano logowania, aktualizatora, innych silników ani klientów Windows/Linux.

## Dostarczone zachowanie

- Dosłowne wyszukiwanie Unicode po prezentowanym adresie i katalogu, max200 znaków.
- Filtry ukończonych, wymagających uwagi i anulowanych; globalne liczniki.
- Generacje i powiązanie kursora z zapytaniem; wygasanie przywraca właściwy filtr/query.
- Nowe pobranie czyści wyszukiwanie, aby nie znikało pod poprzednim filtrem.
- Szczegóły zadania, daty, próba, adres i katalog; bajty, poprawny postęp i prędkość pliku.
- Raport kopiowany na żądanie z allowlistą; brak URL/ścieżek/nazw plików/ID.
- Ustawienia motywu i katalogu, menu i skróty Cmd+L/R/1–6, wersja z bundle.
- Manifest i dostępne teksty licencji w Resources, kontrola obecności i hashy w smoke.
- Testy pakowania także w GitHub Actions. Wersje app/backend/pyproject:0.2.0, build2.

## Dowody lokalne

- Backend: **86 testów PASS**, 8,15s.
- Swift: **30 testów PASS**, 2,20s.
- Generator metadanych: **4 testy PASS**; tylko faktycznie zebrane dystrybucje,
  nieobecny Python LICENSE i brak/zmiana zasobów odrzucają paczkę.
- actionlint i git diff --check: PASS.
- Pełny build `.app`/DMG: PASS; strict codesign ad hoc: PASS;
  wszystkie5 Mach-O deployment target <=13 (nie zastępuje testu na macOS13).
- Smoke `.app`: PASS, handshake0,077s, rzeczywiste pobranie z lokalnego HTTP,
  idempotencja, manifest i zakończenie procesu.
- Smoke DMG zamontowanego tylko do odczytu: PASS, handshake0,336s; odmontowano.
- Rozmiar app około26MiB, DMG15MiB; suma SHA-256 obok paczki końcowej.
- Manifest końcowego buildu: 9 dystrybucji, brakujące teksty w tym inventory:0.
  Licencja Pythona obecna. To nie pełny przegląd natywnych/vendored zależności.

W trakcie testów poprawiono odtworzony błąd pozostawienia query po dodaniu
zadania. Test najpierw wykazał2 niezgodności, po poprawce jest zielony.
Nowe filtry początkowo powodowały sortowanie tymczasowe całej historii;
regresje trzech filtrów w obu kierunkach potwierdziły poprawkę kolejności indeksu.

Kontrolny pomiar na fixture100000 ukończonych rekordów: brak wyników
wyszukiwania completed104,27ms, all103,46ms. EXPLAIN bez TEMP B-TREE.
Wyszukiwanie jest skanem kandydatów, nie indeksem pełnotekstowym, i nie ma
obietnicy stałego czasu dla dowolnie dużej bazy. Nie ładuje historii do RAM GUI.

Niezależny przegląd zmian nie znalazł potwierdzonych problemów wymagających
poprawki; reviewer sprawdził m.in. cursor/query, generacje i prywatność raportu.

## Ograniczenia

Próba dostępu do hosta GUI zakończyła się błędem ScreenCaptureKit -3811.
Nie deklarujemy wizualnego sprawdzenia nowych widoków, motywów, skrótów ani
VoiceOver. Testy modeli i kompilacja nie zastępują tego sprawdzenia.
Nie zmieniono prywatnych danych aplikacji ani sesji przeglądarki.
Nie wykonano testów żywych serwisów, Gatekeepera na czystym Macu ani macOS13.
Podpis ad hoc; brak Developer ID/notaryzacji, automatycznych aktualizacji,
uwierzytelniania i decyzji o licencji projektu. Lista przed wydaniem: `docs/release.md`.

GitHub Actions i otwarcie folderu końcowego następują po push; wynik zostanie
uzupełniony po wykonaniu, bez przenoszenia istniejącego tagu v0.1.0.
