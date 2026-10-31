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

**Etap 3 (31.10):** `tozsamosc` + job `fm_tozsamosc` (workflow ręczny), mapa w `fm_tozsamosc`.
- Drużyny po terminarzu, nie po nazwie: 45 dni terminarzy FotMob (45 zapytań) vs 6206 meczów
  Sofascore z `hd_*`; głosy na poziomie meczu + **weryfikacja przez rywali** (para zostaje,
  gdy w meczach z ≥ 2 różnymi rywalami rywal też pasuje – sam czas dawał przypadki typu
  „Hallescher = Silkeborg”) + propagacja na drużyny z 1 meczem + zapas po nazwie (jedyna
  w obu źródłach, bez sprzeczności godzin; 87 par – reprezentacje, ligi tureckie, U21).
  Wynik: 2413 drużyn; mecze księgi do 28.10 – 98,5% (100% tych, które są w `hd_*`);
  drużyny `trend_lib` 1421/1439 = **99,4% wpisów**; rozgrywki 148, wszystkie z `PROFILE`
  trafione (poza Leagues Cup – poza sezonem). Lista par o odmiennych nazwach przejrzana
  („Chivas”/„CD Guadalajara”, „OB”/„Odense”, „FC Kharkiv”/„Metalist 1925”) – wszystkie dobre.
- Zawodnicy po nazwisku w obrębie meczu (kandydaci z OBU kadr – statshub zapisywał zawodników
  pod drużyną rywala), z grą Sofascore z tego meczu jako dowodem, 634 mecze 25–29.10:
  **99,57% zawodników, którzy wg Sofascore grali w zmapowanym meczu, ma parę** (4166/4184);
  zgodność minut ±15 i strzałów/fauli ±1: 4144 + 18 częściowo, 4 „niezgodne” = jeden mecz,
  w którym statshub zapisał 4 minuty (te same nazwiska – błąd danych, nie osoby).
  Tryb „tylko nazwisko” (tak będą mapowani nowi po przełączeniu): 99,28%.
- Przejrzane ręcznie: 10 par po minutach (pseudonimy: Valde, Malick/El Hadji Diouf,
  Junior Dina/Eric Ebimbe, Zine/Ambrosini Zini…) – dobre; 30 par spoza kadr (transfery,
  tylko z dowodem gry i tymi samymi minutami) – te same nazwiska; 4 niejednoznaczne
  (Danilo, Ramon, Marcos Paulo, Maicon – dwie różne osoby w kadrze) zostają bez pary.
- **Dublety statshub:** nasz numer syntetyczny (≥ 9·10⁸, 3 mecze) przegrywa z prawdziwym
  numerem tej osoby (15–40 meczów) – historia zostaje przy prawdziwym.
- **Błąd FotMob wykryty przy okazji:** ten sam numer zawodnika dla dwóch osób (9 na 18 775,
  numery ~750 000–760 000; 750027 = Brahim Díaz w Realu i Fabricio Perez w Boliwii).
  Mapa pamięta nazwisko przy numerze; wiersz z innym nazwiskiem = `kolizje` (do etapu 4:
  takie wiersze nie wchodzą do historii, `Tozsamosc.wiersz_zgodny`).
- Odrzucone po pomiarze: „nazwa jedyna w bazie” bez dowodu gry (łączyło pospolite nazwiska –
  Carlos Hernández, Juan Pérez), próg samego podobieństwa napisu < 0,86 („Takeshi Wada” ≠
  „Takashi Sawada”).

## Etap 4 – podkroki (31.10)
Zasada łączenia historii: **do 29.10 – nasze dane statshub (`trend_lib`, `hd_*`), od 29.10 – baza
FotMob**, bez dubli (ten sam mecz = ten sam start ±3 h). Nie wolno oddać samego FotMob: bank łączy
historie regułą „pełna nie ustępuje częściowej”, więc 2–3 świeże mecze z `historia_pelna` wyparłyby
20 meczów z banku.

| # | Podkrok | Bramka |
|---|---|---|
| 4a | Baza meczów od 29.10 + codzienne dopisywanie (`fm_baza`, c9d98e1) | nadrobione 29.10–dziś, 0 odmów |
| 4b | Zawodnik: `fetch_player_performance` w kształcie statshub (bank + baza), `fetch_extra_stats`, wyszukiwarka/profil z mapy | na meczach 25–29.10 wiersze z bazy = bank ≥ 97% na rynek; `trendy_z_performance` z nowych wierszy = z wierszy statshub (testy kształtu) |
| 4c | Kadra: `fetch_team_players_performance` (+ niedostępni z `lineup.unavailable`) | kadra = zawodnicy meczów drużyny; testy kształtu `trendy_kadry`, `niedostepni_z_kadry`, `braki_druzyny` |
| 4d | Drużyna: `fetch_team_performance` (`hd_*` + baza, 15 pól), wynik, status, mapa strzałów, sędzia | magazyn `hd_*` dopisany z bazy = rekordy statshub na meczach wspólnych (bramka etapu 2) |
| 4e | Terminarz w kształcie `event/by-date` (numery z mapy, zastępcze dla nowych) + przełącznik `ZRODLO_STATYSTYK` (statshub / fotmob) w `sources/statshub.py` i `build_league._sh` | cykl próbny lokalnie bez wysyłki daje typy; porównanie z ostatnim cyklem statshub (typy per rynek, rozkład szans) |

**4b – rdzeń (31.10, `sources/wlasny_statshub.py`):** wiersze `player/performance` z banku + bazy.
- Bank → wiersze → `trendy_z_performance` = bank: 11 126 / 11 675 serii identycznych, 511 z dodatkowymi
  meczami (warstwa zna mecz z innych rynków, np. zerowe kartki), 38 różnic (0,3%) – dublety w samym
  banku (ten sam mecz dwa razy), które warstwa scala.
- Wiersz FotMob = wiersz statshub na 4776 wspólnych meczach: numer meczu 99,9%, drużyna 100%, faule
  99,4%, faulowani 99,4%, celne 98,9%, strzały 98,1%, głową 98,9/99,6%, zza pola 97,6/99,2%, spalone
  i kartki 100%, minuty ±3 96,4%, odbiory 96,3%; mała próba: przechwyty 85% (n=117).
- Symulacja przełączenia (bank ucięty na 27.10 + FotMob): mecze sprzed granicy 7989 / 8450 serii
  identycznie, po granicy zgodne tam, gdzie FotMob ma składy. **Luka źródła:** część meczów FotMob
  nie ma składów (krajowe puchary – np. 14 meczów z pustą listą zawodników) albo statystyk zawodników
  (Botola Pro, National League) – statshub je miał. ⚑ Reguła do 4c: mecz bez składów NIE wchodzi
  do listy meczów drużyny w kadrze – inaczej „opuścił mecz drużyny” uznałby, że zawodnik nie zagrał.
- Do zrobienia w 4b: wyszukiwarka i profil zawodnika z mapy, `fetch_extra_stats` dla kadr.

**4a – wynik (31.10):** baza nadrobiona 29–31.10 (202 mecze, 0 odmów), razem 1152 mecze; mapa:
19 483 zawodników z parą, 3296 zastępczych; drugi przebieg mapy – bramka 99,12%.
Dopisane do zapisu meczu: numer zmiennika (superzmiana), surowa mapa strzałów (sytuacja – bank
stylu), bilans sędziego (mecze, żółte/mecz, czerwone, karne), grupa ligi (`liga_grupa`).

**4c (31.10):** kadra (`fetch_team_players_performance`) + `fetch_extra_stats`; niedostępni i składy
z meczu przed gwizdkiem (`mecz_nadchodzacy`). 120 drużyn: mecze banku w oknie kadr zgodne 96,5%,
reszta = mecze ze starym klubem o tej samej porze (słusznie poza kadrą). Zawodnik z niepełnym bankiem
(feed propsów, ~19% aktywnych) nie dostaje `historia_pelna`, dopóki taki wiersz jest w ostatnich 10
meczach – „opuścił mecz” mówi wtedy „nie wiemy”, nie „nie grał”.

**4d (31.10):** historia drużyny (`fetch_team_performance`), wynik, status (+ terminarz), mapa
strzałów, sędzia. Rekord magazynu `hd_*` zbudowany funkcją magazynu z wierszy FotMob vs statshub,
744 mecze: numer meczu, rywal, strona 100%, rozgrywki 100% (po mapowaniu grup), rożne 98,9%,
faule 97,2%, spalone 98,3%, posiadanie 95%, celne 94,7%, kartki 93,5%, strzały 89% (±1, jak etap 2),
gole 96,2% (statshub liczył serię karnych). Cechy modelu (xG, tercja, odbiory, przechwyty) różnią się
definicją dostawcy – bez stałego przesunięcia (etap 2). **Luka źródła:** w części pucharów i niższych
lig FotMob nie ma statystyk drużyn (np. kartek), a statshub miał.

## ⚑ Wyłączone do etapu 7 (31.10)
`cycle.yml`, `rozlicz.yml`, `magazyn.yml` – wyłączone ręcznie (`gh workflow disable`): przy 403
statshub cykl kończył się na czerwono co 30 min (~30 maili/dobę), rozliczanie wisiało do limitu
czasu, magazyn nic nie pobierał, a wszystkie dalej pukały do statshub. Przy wdrożeniu (etap 7):
`gh workflow enable` dla trzech + włączyć zadanie w cron-job.org (po odrzuconych `/api/tick`
wyłącza się samo – jak 07.10).

## Otwarte sprawy
- Przewidywane składy (statshub `predicted-teams-lineup`) – właściciel: z innych źródeł.
- Kursy referencyjne UK (`ref_odds` w trendach) – sprawdzić, czy model z nich korzysta.
- Odpowiedzi statshub (James) i Sportradar – jeśli dadzą legalny dostęp, przełącznik wraca.
