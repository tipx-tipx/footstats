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

## Otwarte sprawy
- Przewidywane składy (statshub `predicted-teams-lineup`) – właściciel: z innych źródeł.
- Kursy referencyjne UK (`ref_odds` w trendach) – sprawdzić, czy model z nich korzysta.
- Odpowiedzi statshub (James) i Sportradar – jeśli dadzą legalny dostęp, przełącznik wraca.
