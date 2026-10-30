# Plan: własny statshub na danych FotMob (od 30.10.2026)

**Powód:** od 29.10 ~18 UTC statshub odpowiada wyzwaniem Cloudflare (403) – chmurze i z domu.
**Decyzja właściciela (30.10):** FotMob jako źródło; ruch mały i spokojny, bez ukrywania się
i bez obchodzenia zabezpieczeń; cel – działanie jak przed 29.10 albo lepiej.

**Zasada architektury:** model, typy, drabinki, karty i rozliczenia NIE zmieniają logiki.
Podmieniamy źródło pod `sources/statshub.py`: własna baza meczów oddaje dane w formacie
statshub (te same pola i kształty), przełącznik źródła pozwala wrócić na statshub, gdy odpowie.

**Pomiar wstępny (30.10, 88 zapytań):** liczby FotMob = statshub dla tych samych zawodników
i meczów: strzały 98%, celne 99%, zza pola 98/99%, głową 99/100%, faule 99/99%, spalone 100%,
odbiory 96%. Mapa strzałów brak w części mniejszych lig (Veikkausliiga, Serbia, USL, Ekwador).

## Etapy (każdy kończy się bramką – bez jej przejścia nie idziemy dalej)

| # | Etap | Bramka (dowód, że działa) |
|---|---|---|
| 0 | **Rozpoznanie:** pełna mapa pól statshub (kształt odpowiedzi każdej funkcji, kto co czyta), odpowiedniki w FotMob, braki | dokument mapowania; każde pole czytane przez pipeline ma źródło albo jawną decyzję |
| 1 | **Klient FotMob** (`sources/fotmob.py`): mecze dnia, szczegóły meczu; tempo ≤ 1 zapytanie / 2 s, cache, każdy mecz pobrany raz, wykrywanie odmowy (log + licznik) | testy na zapisanych odpowiedziach; 2 dni realnych danych bez błędu |
| 2 | **Baza meczów** (repo stanu): po gwizdku zawodnicy (16 rynków + minuty, skład, pozycja, rywal) i drużyny (gole, rożne, kartki, strzały, faule + stracone), sędzia | zgodność z `trend_lib` ≥ 97% na rynek na ≥ 200 meczach |
| 3 | **Tożsamość:** zawodnicy, drużyny, rozgrywki FotMob ↔ numery statshub (ciągłość `trend_lib`, księgi, profili, form) | ≥ 95% aktywnych zawodników zmapowanych, niejednoznaczne przejrzane |
| 4 | **Warstwa zgodności:** funkcje w kształcie statshub z bazy (performance zawodnika/drużyny/kadry, trendy meczu, trendy drużyn, sędzia, mapa strzałów, status i wynik) + przełącznik `ZRODLO_STATYSTYK` | testy kształtu; cykl próbny (dry-run) daje typy; porównanie z ostatnim cyklem statshub (liczba typów per rynek, rozkład szans) |
| 5 | **Terminarz i parowanie z Superbetem** z FotMob | odsetek sparowanych ≥ statshub (~79%) |
| 6 | **Rozliczenia** z FotMob (zapas: 365scores) | ponowne rozliczenie typów z 25–29.10 = 100% zgodne z księgą |
| 7 | **Wdrożenie:** dry-run w Actions → publikacja; log: zapytania FotMob/cykl, odmowy, braki mapy strzałów | strona z typami; kontrola produktu bez czerwonych |
| 8 | **Obserwacja 3 dni:** trafność, pokrycie, ruch | brak regresji względem tygodnia przed 29.10 |

## Odporność na przyszłość (sprawdzana na KAŻDYM etapie)
Cel: strona działa w pełni, nawet jeśli jedno źródło kiedyś odmówi. Bez ukrywania się
i obchodzenia zabezpieczeń – odporność bierzemy z małego ruchu, własnych danych i zapasu.

1. **Mały, równy ruch.** Każdy zakończony mecz pobierany RAZ (potem tylko z bazy), terminarz
   kilka razy na dobę, zapytania rozłożone w czasie (odstęp + losowy rozrzut), bez zrywów.
   Licznik zapytań na cykl i na dobę w logu; budżet dobowy z bramką (przekroczenie = czerwony job).
   Dla porównania: statshub dostawał tysiące zapytań na cykl (trendy, kadry po 80 meczów, H2H).
2. **Grzeczna reakcja na odmowę.** 403/429/challenge → natychmiastowa pauza źródła (nie ponawiamy
   w kółko), alarm w logu i w `awarie_cyklu`, cykl liczy dalej z bazy i zapasu.
3. **Własne dane = niezależność.** Surowe odpowiedzi (skompresowane) i znormalizowane wiersze
   w repo stanu. Gdy źródło padnie, cała historia zostaje u nas – brakuje tylko nowych meczów.
4. **Drugie źródło dla rdzenia.** 365scores (już w kodzie, działa z chmury) jako zapas dla
   statystyk zawodników i rozliczeń; adapter źródeł tak, żeby podpięcie kolejnego (statshub po
   odpowiedzi Jamesa, Sportradar) było zmianą konfiguracji, nie przebudową.
5. **Bezpiecznik strony.** Cykl bez danych nigdy nie nadpisuje strony (f06932a) – zostaje
   ostatni dobry stan.

## Wyniki bramek

**Etap 1 (30.10, 7849ef2):** 320 meczów 28–29.10, 322 zapytania, 0 błędów, 0 odmów.
Bez nagłówka User-Agent CloudFront odpowiada 403 – klient wysyła własny.

**Etap 2 (30.10):** parser `fotmob.mecz_do_bazy` + `baza_meczow` (klucz na miesiąc, ~0,9 KB/mecz gz).
- Zawodnicy (237 meczów, zgodność ze statshub): strzały 97,9%, celne 98,9%, faule 99,1%,
  faulowani 99,3%, głową 98,8% / celne 99,4%, celne zza pola 98,9%, spalone 100%, kartki 99,3%;
  na granicy: zza pola 96,9%, odbiory 96,0%; mała próba: przechwyty 84% (n=104),
  zablokowane 94% / niecelne 91% (n=35). Różnice to ±1 – inny dostawca (FotMob = Opta).
- Drużyny (272 mecze, łączenie co do minuty startu): rożne 99,2%, faule 98,1%, spalone 98,4%,
  gole 100% poza meczami z karnymi, celne 96,6%, kartki (żółte+czerwone) 94,3%, strzały 89,7%
  (±1, symetrycznie). **Żadna cecha modelu drużyn bez stałego przesunięcia** (stosunek średnich
  0,99–1,01 na ~450 meczach). `f3` (wejścia w tercję) → suma „Passes into final third”,
  korelacja 0,962, skala ×1/0,912 (do warstwy zgodności).
- **Błąd statshub wykryty przy okazji:** magazyn `hd_*` liczył do goli serię rzutów karnych
  (Liverpool 7 przy 1:1) – nowa baza ma gole bez karnych + osobno wynik po 90'.
- Luka: mapa strzałów (głową / zza pola) brak w KNVB Cup, AFC Champions League Elite, lidze
  chilijskiej – tam statshub ją miał. Zapas do rozważenia w etapie 4: mapa strzałów 365scores.

## Otwarte sprawy
- Przewidywane składy (statshub `predicted-teams-lineup`) – właściciel: z innych źródeł.
- Kursy referencyjne UK (`ref_odds` w trendach) – sprawdzić, czy model z nich korzysta.
- Odpowiedzi statshub (James) i Sportradar – jeśli dadzą legalny dostęp, przełącznik wraca.
