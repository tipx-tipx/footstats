"""Radar okazji kontekstowych — sygnały, których model celowo nie gra.

Trzy detektory (pomysł z ręcznych typów tipsterskich, 2026-07-22):

1. TRANSFER („nowy w drużynie"): historia statshub podąża za ZAWODNIKIEM,
   nie klubem — gdy ostatnie mecze gracza są w innej lidze niż liga jego
   obecnej drużyny (konsensus lig z historii KOLEGÓW z zespołu), rynek
   często wycenia go w ciemno. Model liczy takie przypadki ze starej
   historii i zwykle odrzuca je jako „rozjazd z rynkiem" — dlatego radar
   działa POZA bramami publikacji: to warstwa informacyjna z drabinką
   kursów, nie typ modelu.

2. FORMA („seria"): model świadomie NIE ma czynnika formy (PLAN.md — tylko
   wygaszanie czasowe, podwójne liczenie psuje kalibrację). Radar pokazuje
   serię trafień nad linią Superbetu jako sygnał w UI, bez dotykania p_model.

3. DEBIUTANT („rynek zgaduje"): Superbet kwotuje zawodnika, którego NIE MA
   w feedzie propsów statshub (bukmacherzy UK nie wystawili mu linii — brak
   danych w nowym klubie). Zmierzone na Ba-Sy (Hearts) 2026-07-22: feed
   propsów Sturm–Hearts miał 42 graczy, nowego nabytku ani śladu, a Superbet
   dawał mu pełną drabinkę. Identyfikacja przez /api/search + weryfikację
   team_id profilu z drużynami meczu.

Wszystkie progi są celowo konserwatywne: radar ma pokazywać kilka soczystych
wpisów dziennie, nie ścianę szumu.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import replace as dc_replace

import numpy as np

from ..model import betting
from ..model import context as context_mod
from ..model import counts as counts_mod
from ..model import kontekst_drabinki as kd
from ..model import tempo as tempo_mod
from ..model import uczony
from ..sources import betclic, statshub, superbet
from .. import diagnostyka
from . import magazyn_druzyn, radar_imienny

# --- progi detektorów ---
OKNO_TRANSFER = 15          # ile ostatnich meczów historii patrzymy na ligi
MIN_HISTORIA_TRANSFER = 8   # mniej meczów = za mało, żeby orzekać o zmianie
MAX_MECZE_W_NOWEJ = 3       # tyle meczów w lidze drużyny to wciąż „nowy"
MIN_MECZE_W_STAREJ = 6      # tyle meczów w innej lidze potwierdza przeszłość
OKNO_GRAL_PRZECIW = 8       # mecz PRZECIW obecnej drużynie w tylu ostatnich
MAX_DNI_SWIEZOSC = 60       # ostatni występ dawniej = nieaktualna historia
# ⚑⚑ ILE MECZÓW DRUŻYNY WOLNO OPUŚCIĆ (2026-08-21) — właściwa miara
# świeżości tam, gdzie znamy kalendarz drużyny; `MAX_DNI_SWIEZOSC` zostaje
# wyłącznie jako zapas dla drużyn spoza magazynu.
#
# POWÓD: kalendarz jest złą miarą na przełomie sezonów. Przerwa letnia trwa
# ~75 dni, czyli DŁUŻEJ niż próg 60, więc w sierpniu odpadał każdy, kto nie
# zdążył jeszcze zagrać w nowych rozgrywkach. Zmierzone na 407 zawodnikach
# z 30 nadchodzących meczów: reguła kalendarzowa odrzucała 195 (47,9%),
# w tym **46 z 98 zawodników z PRZEWIDYWANEGO SKŁADU** na najbliższy mecz.
# Ta reguła odrzuca 76 (18,7%), w tym 4 z 98.
#
# ⚑ TO NIE JEST LUZOWANIE PROGU. Zawodnik, który opuścił 6+ kolejnych meczów
# swojej drużyny, odpada nadal — także wtedy, gdy kalendarzowo wygląda
# świeżo (grał 20 dni temu, ale drużyna zagrała od tego czasu osiem razy).
# Stara reguła takiego PRZEPUSZCZAŁA.
#
# 5 to około pięciu-sześciu tygodni ligi. Z odzyskanych 120 zawodników
# 94 opuściło najwyżej DWA mecze, więc próg ma zapas i nie stoi na krawędzi.
MAX_OPUSZCZONYCH_MECZOW = 5

OKNO_FORMY = 6              # seria liczona z tylu OSTATNICH rozegranych
MIN_GIER_FORMA = 12         # łącznie rozegranych, żeby była baza porównania
MIN_TRAFIEN_FORMA = 5       # tyle z OKNO_FORMY meczów nad linią = seria
MIN_BOOST_FORMY = 1.4       # średnia/90 w oknie >= tyle razy średnia bazy
                            # (1.25 dawało ~13% graczy na żywym feedzie —
                            # pomiar 2026-07-22; seria ma być rzadka)
MIN_MINUT_MECZU = 20        # krótsze występy nie liczą się do serii
MIN_KURS_FORMY = 1.35       # linia serii musi być grywalna (nie 1.05)

MIN_RYNKOW_DEBIUTANTA = 2   # Superbet kwotuje >= tyle rynków (odsiew szumu)
MAX_WYSZUKAN_CYKL = 90      # budżet zapytań /api/search na cykl (statshub to
                            # otwarte API bez limitów — próg jest grzeczności,
                            # nie technicznym wymogiem). Mecze iterowane od
                            # NAJBLIŻSZEGO kickoffu, najpierw te bez trendów.
MAX_DEBIUTANTOW_MECZU = 10  # ilu kandydatów IDENTYFIKUJEMY per mecz. Sufit
                            # kart trzyma round-robin, więc tu chodzi o
                            # szerokość lejka: przy 3 braliśmy pierwszych wg
                            # liczby rynków (rotacyjnych), a dobrzy gracze —
                            # np. Imaz z 2,8 strzału śr. — nie byli nawet
                            # sprawdzani (pomiar 2026-07-25)
MAX_RYNKOW_BEZ_HISTORII = 4  # karta bez historii to sama drabinka kursów —
                             # 9 rynków × kilka szczebli to ściana, nie analiza
# rynki pokazywane na kartach bez historii, w kolejności ważności
RYNKI_PODSTAWOWE = ("shots", "sot", "fouls_committed", "fouls_won",
                    "shots_outside_box", "offsides", "tackles")
# ⚑ LIMIT KART NA DZIEŃ MECZOWY, NIE NA CAŁY ZAKRES (2026-09-18, właściciel:
# „analogicznie jak w zawodnikach i drużynach — limit 10 na dzień, wiadomo, że
# często nie będzie wypełniany"). Do dziś MAX_WPISOW = 30 obejmował pięć dni
# naraz, a front brał z tego 10 najlepszych (DRABINKI_MAX) — też z całego
# zakresu. Doba produktowa jak lista dnia (6:00 → 6:00 czasu polskiego,
# `dzien_karty` = `build_wc_fast.dzien_listy`). Karty już opublikowane
# zajmują miejsca swojego dnia (`build_wc_fast.scal_karty_z_publikacjami`).
MAX_KART_DZIEN = 10
MAX_WPISOW = 80             # bezpiecznik całości (≈ 10 × dni zakresu)
MAX_WPISOW_MECZ = 2         # sufit kart na mecz (bez gwarancji slotu!)
MAX_SHOTMAP_CYKL = 160      # budżet zapytań o shotmapy historyczne na cykl
OSTATNIE_N = 10             # ile ostatnich występów pokazuje karta rynku
MAX_SEZONOW_WPISU = 3       # sekcja "sezony" na karcie (bieżący + poprzednie)
# przycinanie drabinki: nikt nie gra linii 8+ @23.00 z ~0% szans — szum
MAX_SZCZEBLI = 5            # tyle linii max na rynek
# SUFIT LINII NA KARCIE (decyzja usera 2026-07-30): „wszystkie typy — faule
# popełnione/wywalczone, strzały — max 3+, tylko odbiory max 4+".
# Linia 2,5 to zakład „3 lub więcej", linia 3,5 to „4 lub więcej" — stąd te
# liczby. Wyżej drabinka i tak schodziła w kursy, które nikogo nie interesują,
# a psuła wrażenie „karta pokazuje sensowne typy".
MAX_LINIA_DOMYSLNA = 2.5    # czyli „3+"
MAX_LINIA_RYNKU = {"tackles": 3.5}   # odbiory: „4+"
MIN_P_SZCZEBLA = 0.03       # od 3. szczebla w górę: p_model < 3% ucina resztę

# PODŁOGA DRUGIEGO SZCZEBLA (2026-08-03, zgłoszenie usera: „ważne, żeby realne
# było wejście też drugiego szczebla").
#
# `MIN_P_SZCZEBLA` obowiązuje dopiero OD TRZECIEGO szczebla, więc pierwszy
# i drugi nie miały żadnej podłogi. Zmierzone na bieżącym przebiegu: osiem
# drugich szczebli miało szanse 0,08 · 0,13 · 0,15 · 0,17 · 0,17 · 0,27 · 0,28
# · 0,40 — sześć z ośmiu poniżej 0,27. Drugi szczebel przy kursie 6,70
# i szansie 8% stał obok sensownej jedynki i wyglądał jak część oferty,
# a był losem na loterii.
#
# Ucinamy drabinkę na pierwszym szczeblu (poza pierwszym), który nie sięga
# progu — dalsze są z definicji gorsze. Szczeble BEZ policzonej szansy
# zostają: tam nie mamy czym oceniać i UI mówi o tym wprost.
#
# ZOSTAJE 0,25 — i to jest świadomy powrót po nieudanej próbie 0,33.
#
# Podniesienie tego progu wyglądało na oczywistą realizację życzenia usera
# („drugi szczebel ma być realny"), a okazało się sprzeczne samo w sobie.
# Przykłady typerów, które user wkleił 08.08, mają drugi szczebel po kursie
# 3,20–6,60 — czyli rynek wycenia go na 15–31%. Żądając od niego 33% naszej
# szansy, wymuszamy, żeby nasza liczba była o jedną trzecią WYŻSZA od ceny
# rynku — dokładnie ten rozjazd, który w pomiarach oznacza NASZ błąd
# (MAX_ROZJAZD_KARTY = 1,25). Karta wzorcowa (Hellebrand, 5/8 nad drugą linią)
# lądowała przy 0,33 dokładnie na granicy odrzucenia.
#
# Realność drugiego szczebla pilnuje więc POKRYCIE, nie nasz procent — patrz
# MIN_POKRYCIE_DRUGIEGO. Ten próg zostaje jako dolny bezpiecznik na szczeble
# całkiem martwe (rozkład z dry-runu: 336 następników poniżej 10%).
MIN_P_DRUGIEGO_SZCZEBLA = 0.25
# ⚑ ILE RAZY DRUGI SZCZEBEL MA WCHODZIĆ (2026-08-08, decyzja usera:
# „drugi szczebel musi być bardzo realny, nie zważając już nawet na nasze %,
# bo z reguły oni dają typy takie, że drugi szczebel też często wchodzi").
#
# To jest ta sama liczba, którą typer wypisuje mecz po meczu — i jedyna, która
# nie zależy od naszego własnego ścinania szansy (Wilson + korekta strumienia
# −0,40 logit potrafią zrobić z pokrycia 5/8 szansę 0,33). Pokrycie drugiego
# szczebla w przykładach usera:
#     Mbappé 5/7 · Igbekeme 7/8 · Hellebrand 5/8 · Berg 3/5 · Yamal 2/4
#     · Lokilo 2/5 · Sánchez 0/4  (mediana 60%)
# Próg 0,50 wpuszcza pięć z siedmiu i odcina te, gdzie drugi szczebel jest
# czystą opcją ryzykowną bez pokrycia.
MIN_POKRYCIE_DRUGIEGO = 0.50

# DWA RODZAJE GRY (propozycja usera 2026-08-03). Ten podział jest PROSTOPADŁY
# do `kategoria` (ta mówi, co widać w drugim cenniku) — tu chodzi o to, jak
# kartę się gra:
#   * „dwa_szczeble" — tanio, ale drugi szczebel realnie wchodzi,
#   * „wyzszy_kurs"  — pierwszy szczebel od 2,0 w górę, a mimo to szansa bliska
#                     rzutowi monetą; wtedy cena bukmachera jest przesadzona.
# NAZWY BEZ SŁOWA „PEWNY" — decyzja usera z 28.07 („różnica kursowa to nie
# równa się pewniak") dotyczy CAŁEGO UI, nie tylko kategorii rozjazdu.
# Karta, która nie spełnia żadnego z warunków, nie dostaje etykiety — lepiej
# nie obiecywać nic, niż obiecywać po cichu.
PEWNA_MIN_P_HERO = 0.60
PEWNA_MIN_P_DRUGI = 0.40
VALUE_MIN_KURS_HERO = 2.00
VALUE_MIN_P_HERO = 0.45
# równe podłodze drugiego szczebla (2026-08-08): etykieta nie ma prawa być
# łatwiejsza niż warunek, na którym drugi szczebel w ogóle zostaje na karcie
VALUE_MIN_P_DRUGI = 0.33
MAX_KURS_SZCZEBLA = 12.0    # ...podobnie kurs powyżej tego progu
# SZCZEBEL „ZA DROBNE" (2026-09-15, decyzja właściciela). Następna linia po
# ostatnim szczeblu karty, pokazywana OBOK drabinki — bez naszej szansy i poza
# wyborem karty. Typerzy grają ją jako „opcję dla odważnych" za symboliczną
# stawkę (docs/analiza-typerow-betekipa.md: 3. szczebel ma 52 z 90 ich typów,
# mediana kursu 7,50). Nasza księga: trzeci szczebel trafia 5,3% ±4,1 (6/113)
# przy cenie ok. 19%, więc NIE obiecujemy szansy — pokazujemy kurs i historię,
# a rekord idzie do księgi jako pomiar.
MAX_KURS_ZA_DROBNE = 15.0
# pierwszy szczebel drabinki od 1.65 (decyzja usera 2026-07-25): linie po
# 1.2-1.5 to pewniaki bez value — drabinka ma zaczynać się od grywalnej ceny
# ZEJŚCIE 1,65 -> 1,45 (2026-07-30) — wymuszone sufitem linii wyżej.
# Sufit „3+" zostawia na karcie tylko niskie linie, a te są tanie: linia 2+
# kosztuje zwykle 1,45–1,80. Przy progu 1,65 dry-run z sufitem dał ZERO kart
# (wcześniej 1–3), bo cała drabinka wypadała na cenie. Dwa życzenia usera —
# „max 3+" i „za mało kart" — da się spełnić naraz tylko wtedy, gdy próg ceny
# zejdzie razem z sufitem linii.
# ⚑ PODŁOGA CENY DOTYCZY *NASZEGO TYPU*, NIE POCZĄTKU DRABINKI (2026-08-08).
#
# Życzenie usera („pierwszy szczebel min. 1,6/1,7") realizuje `MIN_KURS_SCORE`
# niżej, a NIE ta stała. Różnica wygląda na kosmetyczną, a jest zasadnicza —
# zmierzona dry-runem, po tym jak podniesienie TEJ stałej do 1,60 zbiło podaż
# z ~20 kart do JEDNEJ:
#
#   drabinka startuje od pierwszej linii spełniającej próg, więc podnosząc go,
#   przesuwamy CAŁĄ drabinkę w górę — a drugi szczebel ląduje na linii, której
#   nikt nie przebija. Przykład z danych: zawodnik z 1+ @1,55 (70%), 2+ @2,60
#   (42%), 3+ @6,00 (15%). Przy progu 1,45 drabinka to [1+, 2+] i drugi
#   szczebel ma 42% — dokładnie to, o co prosi user. Przy progu 1,60 pierwsza
#   linia wypada, drabinka to [2+, 3+], a drugi szczebel ma 15% i karta ginie.
#
# Dowód liczbowy (dry-run 08.08, rozkład szansy drugiego szczebla przed cięciem):
#   poniżej 10%: 336 | 10–20%: 52 | 20–25%: 4 | 25–30%: 8 | 30–33%: 1 | 33%+: 5
# Czyli przy podniesionej podłodze drugi szczebel jest MARTWY w 96% przypadków.
# Podnoszenie progu ceny startu działa więc PRZECIWKO drugiemu szczeblowi.
#
# Zostaje 1,45: drabinka ma prawo POKAZAĆ tanią linię (to kontekst i dowód, że
# zdarzenie jest częste — dokładnie jak we wzorcu typera, gdzie tania cena
# Superbetu jest argumentem), ale NASZYM TYPEM zostaje dopiero szczebel od 1,60.
MIN_KURS_PIERWSZEGO = 1.45
# --- Rozliczenia 82 drabinek: całą zyskowność niesie wąskie pasmo ceny ---
#     poniżej 1,50   n= 3   trafia   0,0%   zwrot −100,0%
#     1,50–1,70      n=10   trafia  70,0%   zwrot   +9,3%   <- jedyne dodatnie
#     1,70–2,00      n=17   trafia  23,5%   zwrot  −56,1%
#     2,00–2,50      n=23   trafia  39,1%   zwrot  −14,4%
#     powyżej 2,50   n=29   trafia  17,2%   zwrot  −46,9%
# W paśmie 1,50–1,70 deklaracja zgadza się z wynikiem co do punktu (69,7%
# obiecane, 70,0% trafione) — jedyne miejsce w drabinkach, gdzie nasza liczba
# jest prawdziwa. Podłoga (nie okno) to decyzja usera: droższe karty zostają
# w grze, ale ranking je odsuwa (patrz OKNO_CENY_PREF_*).
#
# --- TWARDE BRAMY JAKOŚCI (decyzja usera 2026-07-25: „tylko najlepsze
# drabinki, nie randomowe"). Sygnał (transfer/forma/debiutant) NIE jest już
# przepustką — zostaje plakietką, ale karta musi obronić się liczbami. ---
# ⚑ TO TU MIESZKA ŻYCZENIE „PIERWSZY SZCZEBEL OD 1,6/1,7" (2026-08-08):
# szczebel tańszy niż próg może stać na karcie jako kontekst, ale nie zostanie
# NASZYM TYPEM (hero). Podniesione z 1,45 razem ze zgłoszeniem usera —
# w odróżnieniu od MIN_KURS_PIERWSZEGO nie przesuwa całej drabinki w górę,
# więc nie zabija drugiego szczebla (patrz długa nota wyżej).
#
# 1,55, nie 1,60 — decyzja usera 08.08 poparta rozliczeniami: zyskowne pasmo to
# 1,50–1,70, więc próg 1,60 odcinałby jego lepszą, dolną połowę. Przykłady
# typerów zaczynają się od 1,48 (mediana 1,90), więc 1,55 jest po bezpiecznej
# stronie i nadal spełnia „minimum 1,6/1,7" tam, gdzie to ma znaczenie.
MIN_KURS_SCORE = 1.55
# RANKING PREFERUJE OKNO, W KTÓRYM DRABINKI ZARABIAJĄ (patrz tabela wyżej).
# Nie brama, tylko premia w kolejności: karta startująca od 1,65 wychodzi przed
# kartę startującą od 2,40 przy podobnej przewadze. Wartość w punktach
# przewagi — 0,015 to tyle, co półtora punktu procentowego edge, czyli premia
# realna, ale nie przebijająca wyraźnie lepszej karty.
#
# ⚑ GÓRNA GRANICA 1,90 -> 1,70 (2026-08-13). Okno powoływało się na tabelę
# wyżej, a tamta tabela mówi „1,70–2,00: trafia 23,5%, zwrot −56,1%" — czyli
# premia obejmowała połowę NAJGORSZEGO pasma w całej zakładce. Sprawdzone
# ponownie na 94 rozliczeniach bieżącej epoki, z podziałem na połowy próby
# (próg stawiamy na LUKĘ, bo ROI w tych wycinkach zmienia znak):
#
#     pasmo        n   deklaruje  trafia    luka     I poł.   II poł.
#     1,55–1,70   16     62,3%    62,5%    +0,2 pp   +2,9     -1,8
#     1,70–1,90   15     55,6%    26,7%   -28,9 pp  -27,0    -32,7
#     1,90+       53     44,6%    34,0%   -10,7 pp   -8,5    -13,1
#
# Pasmo 1,55–1,70 jest skalibrowane CO DO PUNKTU i stabilnie — dokładnie jak
# mówiła pierwotna nota. Pasmo 1,70–1,90 jest nie tylko najgorsze, ale gorsze
# niż to, co ZOSTAJE poza oknem, więc premia działała przeciwko sobie.
# Oba pasma są zdominowane przez ten sam rynek (`shots`, 12 z 15 i 12 z 16),
# więc to nie jest efekt składu rynków. Bez `fouls_committed` bez zmian.
#
# To zmiana KOLEJNOŚCI, nie bramy — żadna karta przez to nie znika.
#
# ⚑⚑ PREMIA ZDJĘTA (2026-09-15, decyzja właściciela po pomiarze). Na większej
# próbie tabela z 13.08 się nie powtarza — 1. szczebel od 13.08 (księga):
#
#     pasmo        n   deklaruje  cena   trafia   zwrot
#     1,55–1,70   95     55%      59%     56%     −11%
#     1,70–1,90   34     50%      53%     50%     −12%
#     1,90+       13     44%      44%     54%      +9%
#
# Oba pasma leżą tak samo pod ceną, więc „najgorsze pasmo" było szumem na 15
# kartach, a premia spychała karty do najniższych kursów: 95 ze 142 pierwszych
# szczebli startowało z 1,55–1,70. Eksperci BET EKIPA zaczynają drabinkę od
# mediany 2,20. Stałe zostają (wartość 0), żeby test i powrót były jedną liczbą;
# decyzja o minimum 1,8+ — po tygodniu rozliczeń po poprawkach z 15.09.
OKNO_CENY_PREF_OD = 1.55
OKNO_CENY_PREF_DO = 1.70
BONUS_OKNA_CENY = 0.0
MIN_PROBA_SCORE = 8         # min. występów w próbie (było 5 — za krótkie
                            # serie udawały pewniaki: 3/5 = "60%")
# Surowe pokrycie linii. ZEJŚCIE 0.6 -> 0.5 (decyzja usera 2026-07-26):
# próg 60% pochodził z czasów, gdy karta nie miała realnego
# prawdopodobieństwa i pokrycie musiało samo udawać jakość. Odkąd bramą jest
# przewaga nad kursem (MIN_EDGE_KARTY liczone z p_final), 60% wycinało akurat
# typy najbardziej wartościowe: „5/10 przy kursie 3,00" to 50% szansy wobec
# 33% w cenie. Pomiar cyklu 2026-07-26: 236 z ~346 kandydatów padało na tym
# progu, a na braku przewagi tylko 4 — czyli lista była krótka nie dlatego,
# że typy są słabe, tylko dlatego, że bramka pytała o złą rzecz.
PROG_POKRYCIA_KARTY = 0.5

# ⚑ SITO (2026-09-16, decyzja właściciela: „problemem nie jest wyszukiwarka,
# tylko sito"). Pierwszy szczebel ma być NAJWYŻSZĄ linią, którą zawodnik
# realnie pokrywa, a nie linią najhojniej wycenioną przez bukmachera. Pomiar
# na księdze 20.08–14.09 (113 kart hero z pełnymi cechami) i na 51 typach
# BET EKIPY rozliczonych naszymi danymi:
#
#     nasze karty                         n    trafia   cena
#     pokrycie ≥0,7 & minuty ≥80          66    62,1%   60,6%
#       … & kurs ≥1,8                      9    77,8%   53,2%
#       … & p modelu ≥0,45 & kurs ≥1,8     7    85,7%   52,7%
#     pokrycie 0,6–0,7                    17    41,2%   58,9%
#     minuty <85                          56    44,6%   60,4%
#     BET EKIPA: pokrycie10 ≥7            10    70,0%   48,3%
#     BET EKIPA: pokrycie <7              41    39,0%   46,5%
#
# Dotychczasowy wybór po przewadze `p_final − 1/kurs` dawał 58% kart w paśmie
# 1,55–1,80 i 53% trafień przy cenie 62% ([[drabinki-liczba-jest-odwrotna]]:
# przewaga nad ceną porządkuje ODWROTNIE).
#
# ⚑ SITO JEST BRAMĄ KARTY (2026-09-17, decyzja właściciela: „5 z 7 kart to
# 6/10 — trzeba znaleźć rozwiązanie"). Do 16.09 karta bez linii sitowej dalej
# powstawała i stała za sitowymi — przy małej podaży strona pokazywała
# głównie karty niesitowe. Zmierzone 17.09 na kopii księgi do 14.09
# (218 rozliczonych kart hero, historia z biblioteki trendów sprzed
# kickoffu, występy ≥20 min jak w `_grane`):
#
#     pokrycie ≥7/10 i…                        n    trafia   cena
#     forma ost. 5: 4–5/5                     110    52,7%   59,6%
#     forma ost. 5: 3/5                        37    43,2%   57,6%
#     forma ost. 5: ≤2/5                        8    37,5%   56,0%
#     brak występu <60 min w ost. 5           126    52,4%   58,8%
#     JEST występ <60 min w ost. 5             29    37,9%   59,4%
#     SITO = 7/10 & 4/5 & brak <60 min         95    55,8%   59,4%
#       … & kurs ≥1,8                          23    65,2%   50,3%
#     POZA SITEM (reszta pokazanych)          123    39,8%   53,7%
#
# Co z tego wynika i czego NIE ma w sicie:
#  * FORMA liczona z ostatnich 5 występów na tej linii — 3/5 to inna klasa
#    niż 4/5. Forma jest bramą SZCZEBLA, nie karty: gdy 2,5 ma 7/10, ale
#    ostatnio 3/5, hero schodzi na 1,5, a 2,5 zostaje celem polowania.
#    Forma z samych pełnych występów (≥60 min) nie rozdziela lepiej
#    (50,9% vs 52,7%), więc liczymy ją z tego samego okna co pokrycie.
#  * KRÓTKI WYSTĘP (<60 min) w ostatnich 5 zastępuje średnią minut: średnia
#    z 6 ≥80 nic nie dodawała (55,3% vs 60,0% poniżej 80 przy braku krótkich),
#    a jeden występ z ławki obniżał trafność o kilkanaście punktów.
#    Wyjątek: ogłoszony/przewidywany skład (`xi` True) — on odpowiada wprost.
#  * SUFIT KURSU ZDJĘTY: w sicie pasmo 1,8+ trafia 65% przy cenie 50%;
#    stary sufit 2,60 wziął się z kart wybieranych po przewadze, nie po
#    pokryciu. Hero = NAJWYŻSZA linia sitowa, która ma następnik.
#  * SZANSA MODELU NIE JEST BRAMĄ: w sicie p<0,45 → 66,7% (n=6) — brak
#    dowodu w obie strony; model zostaje w kolejności kart (ocena).
#  * WYJĄTEK RYWALA (życzenie właściciela 17.09, NIEZMIERZONY — n=2): gdy
#    rywal oddaje na tym rynku wyraźnie więcej niż norma, próg formy schodzi
#    do 3/5. Stempel `sito_wyjatek` w księdze ma to zmierzyć.
#  * FORMA DRUGIEGO SZCZEBLA: cel polowania z ≤1/5 wchodził 10% (n=10) przy
#    cenie 30%, z ≥2/5 — 21%; szczebel z martwą formą nie jest następnikiem.
PROG_POKRYCIA_SITA = 0.70    # 7 z 10 na wybranej linii
OKNO_FORMY_SITA = 5          # ostatnie występy, z których liczymy formę linii
PROG_FORMY_SITA = 4          # 4 z 5 przebić na wybranej linii
PROG_FORMY_SITA_RYWAL = 3    # 3 z 5, gdy rywal hojny na tym rynku (mierzone)
MNOZNIK_RYWALA_WYJATKU = 1.15
MIN_MINUT_PELNEGO_WYSTEPU = 60   # krótszy występ w ostatnich 5 = rotacja
MIN_UDZIAL_SITA = 0.80       # startów w meczach drużyny (albo XI ogłoszone)
# --- SIŁA LINII zamiast twardego sita (sito v3, 2026-09-18) --------------
# Właściciel 17.09: karta to PAKIET argumentów × cena, nie jeden próg; hero
# ma być realny i opłacony (~1,7+), ale 1,6 jest OK, gdy drugi szczebel jest
# bardzo realny. Pomiar w księdze (218 hero, do 14.09):
#     7/10 & forma 4-5/5   n=93   57%  (cena 59%)
#     6/10 & forma 4-5/5   n=11   55%  (cena 50%)   <- sito 7/10 to wycinało
#     7/10 & forma 3/5     n=23   48%  (cena 57%)
#     6/10 & forma 3/5     n=13   15%
#     forma <=2/5          n=35   ~35%
#     sito & kurs <1,70    n=59   59%  (cena 63%)   <- PRZEGRYWA z ceną
#     sito & kurs 1,80+    n=23   65%  (cena 51%)
# Pokrycie i forma działają RAZEM: siła = 0,4·pokrycie + 0,6·forma (waga
# formy większa, bo 6/10&4/5 ≈ 7/10&4/5, a 7/10&3/5 wyraźnie gorsze), minus
# kary za rotację (występ <60 min w ost. 5: 38% vs 52%), za nieznane minuty
# i za udział startów <0,8 (XI ogłoszone zdejmuje kary), ± rywal. Trafialność
# ≈ SKALA_SILY × siła (0,76→57%, 0,72→54%, 0,64→48%, 0,50→37% — pasuje).
# Hero = linia z NAJWYŻSZĄ WARTOŚCIĄ PAKIETU:
#     wartość = (SKALA_SILY·siła − 1/kurs) + WAGA_NASTEPNIKA · SKALA_SILY·siła_2
# czyli własna przewaga po cenie plus realność drugiego szczebla — tania
# linia 10/10 przy 1,55 wciąż może wygrać, ale 7/10 przy 1,62 przegrywa
# z 7/10 przy 1,90, a mocny następnik podnosi tańszy start (życzenie
# właściciela). Próg siły hero = 0,70 (7/10&4/5 = 0,76; 6/10&4/5 = 0,72;
# 7/10&3/5 = 0,64 odpada, chyba że hojny rywal +0,06). Drugi szczebel w
# księdze trafia 21% przy cenie 30% w każdym przekroju poza formą 4-5/5 (28%)
# — dlatego następnik liczy się siłą, nie przewagą. Progi do przeliczenia
# po ~2 tyg. z księgi (`sila`, `drugi_sila`, `wartosc_pakietu` na hero).
WAGA_POKRYCIA_SILY = 0.4
WAGA_FORMY_SILY = 0.6
KARA_KROTKICH_WYSTEPOW = 0.25   # występ <60 min w ost. 5 (bez ogłoszonej XI)
KARA_BRAK_MINUT = 0.10          # nie znamy minut ostatnich meczów
KARA_UDZIALU = 0.10             # udział startów < MIN_UDZIAL_SITA
KARA_BRAK_FORMY = 0.10          # brak 5 ostatnich występów na linii
PREMIA_RYWALA = 0.06            # rywal hojny (≥ MNOZNIK_RYWALA_WYJATKU) / skąpy
MNOZNIK_RYWALA_SKAPEGO = 0.85
# ⚑ SITO v4 (2026-09-21, decyzja właściciela po backteście na księdze —
# 13 006 par z historią sprzed meczu ze statshub, nota w pamięci projektu):
#   * pokrycie 6/10 z formą 4–5/5, wpuszczone 18.09, trafiało 40,8% przy cenie
#     51,6% (n=169, −10,8 pp); „to samo sito, ale ≥ 7/10” było lepsze przy
#     każdym cięciu kursu (≥1,8: −2,3 → +0,2 pp; ≥2,0: +1,4 → +4,0). Próg wraca
#     na 7/10, kosztem ~40% linii po sicie.
#   * ostatni występ < 62 min: −8,7 pp (n=115); 2+ krótkie w ostatnich 5:
#     −11,5 pp (n=43); JEDEN krótki: −4,5 pp vs −2,7 przy zerze — kara 0,25 za
#     jeden krótki była za ostra. Średnia minut z 6 (dawna brama karty) przy
#     medianie ≥ 62 nie różniła się od bazy (51,9% vs 56,3%, n=52) — jeden
#     26-minutowy występ zabijał kartę Mandragory na 0,5 (7/9).
#   Forma 5 zostaje z wagą 0,6 (decyzja właściciela), okno 10 zostaje.
PROG_POKRYCIA_SILY = 0.70       # poniżej 7/10 linia nie jest hero niezależnie od formy
MIN_KROTKICH_KARY = 2           # kara za krótkie występy dopiero od dwóch w ost. 5
SITO_WERSJA = "v4-2026-09-21"   # stempel do księgi — Skuteczność liczy wersje osobno
PROG_SILY_HERO = 0.70
SKALA_SILY = 0.75               # siła → trafialność (dopasowanie z księgi)
WAGA_NASTEPNIKA = 0.25
# ⚑⚑ WYBÓR PIERWSZEGO SZCZEBLA: NAJWYŻSZY KURS WŚRÓD MOCNYCH LINII (2026-09-18,
# decyzja właściciela „akceptuję wszystko”). Księga do 14.09: linia mocna
# (7/10 & 4–5/5, bez krótkich) trafia ~55–65% NIEZALEŻNIE od kursu — przy
# kursie <1,70 59% wobec ceny 63% (przegrywa), przy 1,80–2,50 65% wobec 51%
# (n=23). Pokrycie 8–9/10 to tanie linie (46%), więc siła 1,0 taniej linii
# nie jest powodem, żeby wygrała z droższą. Chery 17.09: zza pola 1,5 @3,9
# (7/10, 4/5) przegrałby z tanią linią w starej wartości pakietu.
#   * hero = NAJWYŻSZY kurs spośród linii z siłą ≥ PROG_SILY_HERO,
#     wartość pakietu tylko rozstrzyga remis;
#   * kurs < MIN_KURS_HERO (1,70) tylko z REALNYM następnikiem (forma
#     ≥ MIN_FORMA_NASTEPNIKA_TANIEGO z 5 i pokrycie ≥ MIN_POKRYCIE_NASTEPNIKA_TANIEGO)
#     — „pewny pierwszy, płatny drugi” (Openda 0,5 @1,68 + 1,5 @4,25); inaczej
#     taka linia zostaje pojedynczym typem listy dnia, nie drabinką;
#   * weto modelu (skalibrowany w każdym paśmie, pomiar 16.09): szansa
#     modelu niższa od ceny o więcej niż WETO_MODELU_PP → linia nie jest hero;
#   * perełka = hero z kursem ≥ PROG_PERLY — stempel do księgi i rankingu.
# Każdy hero niesie `powod_szczebla` (perla / najwyzsza_mocna /
# tania_z_drugim) — progi do przeliczenia z rozliczeń po ~2 tyg.
MIN_KURS_HERO = 1.70
# ⚑ PEREŁKA NIE MOŻE PADAĆ NA BRAMACH ZROBIONYCH POD TANIE LINIE (2026-09-18,
# symulacja Chery'ego na pełnej historii, korekta strumienia −0,5 logit jak w
# produkcji ~−0,40): zza pola 1,5 @3,9 (7/10, 4/5) ma iloraz p_final/cena 1,67
# (@4,25: 1,82) — MAX_ROZJAZD_KARTY 1,25 ścinał CAŁĄ kartę, a następnik
# 2,5 @9,0 (5/10, 2/5) miał 0,22 < MIN_P_DRUGIEGO_SZCZEBLA 0,25, więc 1,5
# zostawała bez drugiego szczebla i hero schodził na 0,5 @1,70.
#   * linia BARDZO mocna (siła ≥ PROG_SILY_ROZJAZDU = 7/10 & 4/5) ma limit
#     rozjazdu MAX_ROZJAZD_KARTY_MOCNEJ zamiast 1,25 — pomiar −37% ROI przy
#     1,30–1,50× pochodzi sprzed sita (karty z samej przewagi modelu), dla
#     mocnych linii pomiaru nie ma; każda taka karta niesie `rozjazd_iloraz`
#     do księgi (decyzja właściciela 18.09: „tak, upewnij się i dopracuj”);
#   * następnik szczebla z kursem ≥ PROG_PERLY potrzebuje szansy
#     MIN_P_NASTEPNIKA_PERLY — przy kursach 6–10 to z natury bonus; pokrycie
#     (≥ 5/10) i forma (≥ 2/5) następnika zostają bez zmian.
PROG_SILY_ROZJAZDU = 0.76
MAX_ROZJAZD_KARTY_MOCNEJ = 2.0
MIN_P_NASTEPNIKA_PERLY = 0.15
MIN_FORMA_NASTEPNIKA_TANIEGO = 4
MIN_POKRYCIE_NASTEPNIKA_TANIEGO = 0.50
WETO_MODELU_PP = 0.10
PROG_PERLY = 2.20
MIN_FORMA_DRUGIEGO = 2       # następnik: wszedł w ≥2 z 5 ostatnich
# PRÓG ZOSTAJE NA 0.5 mimo zgłoszenia „drabinki są randomowe" (2026-07-27).
# Podniesienie go na 0.65 wycięłoby kartę, którą user wskazał jako DOBRĄ
# (Marcel Regula, strzały 2,5 @2,05 przy pokryciu 6/10 = 0,60). Szum, o który
# chodziło, nie siedzi w progu głównej linii, tylko w tym, co leży OBOK niej
# na karcie — i to tniemy trzema bramami niżej.
#
# PIERWSZY WYNIK POMIARU (dry-run 2026-07-29, 160 kandydatów):
#   daleko pod progiem (<0,40)        152 szczeble
#   w paśmie pomiarowym (0,40–0,50)    42
#     z tego poniżej ceny fair         40
#     z tego rozjazd z rynkiem          2
#     do zmierzenia                     0
# Czyli PRÓG 0,5 NIE ODCINA NICZEGO, czego nie odciąłby kurs: każdy szczebel
# tuż pod progiem bukmacher wycenia wyżej, niż my go liczymy. Powód jest
# mechaniczny — Wilson ścina 4/10 do 0,30, a rynek płaci tam jak za ~0,33+.
# Wniosek praktyczny: ruszanie tego progu (w górę czy w dół) nie zmieni ani
# podaży kart, ani wyniku. Wąskim gardłem jest korekta próby zderzona z ceną.
# Pomiar zostaje włączony — kosztuje tyle co nic, a w dniu, w którym rynek
# wystawi taką linię hojnie, karta pomiarowa się zapisze i rozliczy.
#
# POMIAR PROGU (2026-07-29). Dotąd 0,5 było WIARĄ: nikt nie wiedział, czy
# szczeble tuż pod progiem trafiają gorzej, tak samo, czy lepiej — bo nigdzie
# się nie rozliczały. Ta sama sztuczka, co przy typach modelu (betting.NEAR_*):
# szczebel odrzucony WYŁĄCZNIE pokryciem i mieszczący się w tolerancji poniżej
# trafia do księgi z flagą `odrzucony`, rozlicza się w tle i NIE pokazuje się
# nigdzie — ani w Drabinkach, ani w Skuteczności, ani w kalibracji. Po kilku
# tygodniach porównanie jego trafień z opublikowanymi (rozliczanie.
# pomiar_progu_drabinek) powie, czy 0,5 to dobra liczba — zamiast zgadywania.
NEAR_POKRYCIA = 0.10        # mierzymy pokrycia 0,40–0,50
# NIŻSZY PRÓG PRZEWAGI DLA POMIARU — konieczny, nie wygodny. Pierwsza wersja
# wymagała od szczebla pomiarowego pełnego MIN_EDGE_KARTY i dała ZERO
# kandydatów w dry-runie 2026-07-29 (na 99 odrzuconych pokryciem). Powód jest
# mechaniczny: p_final rośnie razem z pokryciem, więc szczebel spod progu ma
# z definicji niższą szansę, a przy niższej szansie wymagane +3 pp przewagi
# zostawia okno kursów szerokie na kilka setnych (dla 4/10 dokładnie
# 3,67–3,85). Bukmacher tam nie kwotuje i pomiar nigdy by nie ruszył.
# Zostaje więc uczciwe minimum: „warte swojej ceny" (przewaga >= 0).
MIN_EDGE_POMIARU = 0.0
# Sufit pomiaru trzymamy w rzędzie publikacji (dawniej MAX_WPISOW=30; od 18.09
# MAX_KART_DZIEN × dni zakresu): grupa
# porównawcza ma być tej samej wielkości co publikacja, a nie ją zdominować —
# rozliczone wpisy nigdy nie wypadają z księgi (to dataset kalibracji).
# Bierzemy szczeble o największej przewadze, czyli tą samą regułą, którą
# wybieramy karty — inaczej porównywalibyśmy TOP z losem.
MAX_POMIAROW_CYKLU = 25

# --- SPRZĄTANIE KARTY (zgłoszenie usera 2026-07-27: „często są randomowe
# rzeczy"). Karta Reguły miała 9 rynków i 25 szczebli, z czego 11 to pokrycia
# 0/10 i 1/10 przy kursach 8-33. Sama linia była sensowna, tonęła w szumie. ---
MIN_TRAF_SZCZEBLA = 2       # szczebel trafiony 0 albo 1 raz na 10 to nie typ
MIN_NIEZEROWYCH_RYNKU = 5   # rynek, w którym zawodnik ma <5 niezerowych
                            # meczów (np. „celne głową" obrońcy), to przypadek
                            # — nie pokazujemy go wcale
MAX_RYNKOW_KARTY = 3        # tyle rynków max na karcie, wybrane po jakości
MIN_MINUT_KARTY = 62        # zmiennik (52-55 min śr.) to ryzyko, nie typ
MIN_EDGE_KARTY = 0.03       # przewaga po korekcie próby, w pkt proc.
# ...ale JUŻ NIE JAKO BRAMA (decyzja usera 2026-08-08). Zostaje w rankingu
# i w etykiecie `powod_wejscia`; kartę zdejmuje odtąd pokrycie, cena i rynek.
#
# POWÓD JEST POMIAROWY, nie estetyczny. 86 rozliczonych kart rozbitych wg
# naszej przewagi nad ceną NIE UKŁADA SIĘ W ŻADEN PORZĄDEK:
#     przewaga < 0      n=18   trafia 33,3%   zwrot −25,7%
#     przewaga 0-3 pp   n=17   trafia 17,6%   zwrot −61,9%
#     przewaga 3-8 pp   n=42   trafia 35,7%   zwrot −24,1%
#     przewaga 8 pp+    n= 9   trafia 22,2%   zwrot −57,4%
# Karty BEZ przewagi wypadają lepiej niż te z przewagą 8 pp+. Brama na tym
# postawiona nie broniła jakości — ucinała podaż. To ta sama obserwacja co
# [[czy-bijemy-kurs]]: nasza liczba jest gorsza od samego kursu.
BRAMA_PRZEWAGI = False

# --- CO NAPRAWDĘ ROZDZIELA KARTY (pomiar 2026-08-08 na 86 rozliczeniach) ---
# Cel produktu wg usera: „wyławiamy kursy w okolicach 2 i więcej, to są value
# kursy i realne znaleziska". Pasmo 2,00+ traciło −32,5% — ale nie z powodu
# ceny, tylko JEDNEGO RYNKU i górnego końca skali:
#     faule popełnione, kurs 2,00+        n=13   trafia  7,7%   zwrot  −80,4%
#     faule popełnione, kurs poniżej 2    n= 5   trafia  0,0%   zwrot −100,0%
#     bez fauli, kurs 2,00-2,50           n=22   trafia 45,5%   zwrot   −1,1%
#     bez fauli, kurs 2,50+               n=20        —          zwrot  −35,7%
# Osiemnaście kart na faulach, JEDNA trafiona. Ten rynek nie jest słaby przy
# wysokich kursach — jest słaby zawsze, więc nie daje kart w ogóle.
RYNKI_BEZ_KARTY = frozenset({"fouls_committed"})
# ⚑ POMIAR RYNKU BEZ KARTY (2026-09-21, decyzja właściciela: „faule popełnione
# z powrotem, ale upewnij się"). Backtest na księdze (45 dni, historia sprzed
# meczu ze statshub performance, 13 006 par): faule popełnione po dzisiejszym
# sicie (siła ≥ 0,70) przy kursie ≥ 1,7 trafiają 36,8% przy cenie 52,7%
# (n=38, ROI −28,6%), gdy strzały 46,3% przy 48,1%, faule wywalczone 45,2%
# przy 49,5%. Linia 1,5 z pokryciem 8+/10: 41,7% przy 61,8% (n=12). Ten sam
# obraz co 08.08 (18 kart, 1 trafiona). Backtest nie ma sędziego, XI ani
# rywala — radar ma. Dlatego rynek NIE wraca na kartę, tylko do POMIARU:
# linia fauli, która przeszła WSZYSTKIE bramy karty (sito, minuty, XI,
# następnik), rozlicza się w tle z własnym stemplem
# (`rozliczanie.pomiar_progu_drabinek` → „rynek_bez_karty"). Gdy po kilku
# tygodniach trafia co najmniej tyle, co cena, ban zdejmuje jedna stała.
POWOD_POMIARU_RYNKU = "rynek_bez_karty"
# Powyżej tej ceny karta musi mieć mocną serię NA TEJ LINII (decyzja usera:
# „wpuszczaj, ale tylko z mocnym pokryciem"). Bez tego 2,50+ to −35,7% nawet
# po odsianiu fauli, a z nim zostają te karty, które user pokazuje jako
# wzorcowe — drugi szczebel po 3,50-5,50 z realną historią za sobą.
CENA_WYMAGAJACA_SERII = 2.50
PROG_POKRYCIA_DROGIEJ = 0.70

# --- DRUGA ŚCIEŻKA WEJŚCIA: MOCNA SERIA (decyzja usera 2026-07-30) ---
# „Drabinka to nie tylko przewaga nad kursem" — karta „7 na 10 meczów po 2+
# faule, kurs 2,50" jest wartościowa niezależnie od tego, czy nasza szansa
# bije cenę, bo pokazuje realny wzorzec, a nie naszą opinię o cenie.
#
# PROGI Z POMIARU, nie z wyczucia. Dry-run 30.07 rozbił 87 kandydatów
# odrzuconych na przewadze wg pokrycia i ceny:
#     mocne 7+/10, kurs 1,7-2,0   =  8      <- wpuszczamy
#     mocne 7+/10, kurs 2,0+      =  1      <- wpuszczamy
#     srednie 6/10, kurs 2,0+     =  3      <- wpuszczamy
#     slabe 5/10, kurs do 1,7     = 34      <- odrzucamy dalej
# 68 z 87 odrzuceń to tanie linie poniżej 1,7 — wpuszczenie ich zamieniłoby
# „za mało kart" na „dużo słabych kart", czyli nie rozwiązałoby problemu.
PROG_POKRYCIA_SERII = 0.70   # mocna seria...
MIN_KURS_SERII = 1.70        # ...przy cenie, która jest coś warta
# ...albo seria trochę słabsza, ale przy wyraźnie wyższej stawce
PROG_POKRYCIA_SERII_DROGIEJ = 0.60
MIN_KURS_SERII_DROGIEJ = 2.00
# Przewaga NIE jest wymagana, ale karta nie może być jawnie gorsza od ceny:
# przy −6 pp nasze własne liczby mówią, że bukmacher ma rację, a my nie.
MIN_EDGE_SERII = -0.06

# --- TRZECIA ŚCIEŻKA WEJŚCIA: RÓŻNICA MIĘDZY BUKMACHERAMI („hybryda") ---
# Decyzja usera 2026-08-08. Dotąd różnica kursów była wyłącznie ETYKIETĄ:
# karta musiała najpierw przejść bramę „nasz model bije cenę", a rozjazd tylko
# ją opisywał. To odwracało kolejność dowodów — bo różnica między dwoma
# cennikami jest przewagą, która NIE ZALEŻY od tego, czy nasz model ma rację,
# a my mamy zmierzone, że nasza liczba jest gorsza od samego kursu w 7 z 9
# rynków ([[czy-bijemy-kurs]]).
#
# ZASTRZEŻENIE USERA, KTÓRE JEST TU NAJWAŻNIEJSZE: „tylko gdy serio ten typ ma
# szansę realnie wejść, nie możemy opierać się tylko na kursie". Dlatego
# różnica zastępuje WYŁĄCZNIE wymóg przewagi modelu. Wszystkie pozostałe
# warunki zostają: minuty, udział startów, realny drugi szczebel, brak
# kwarantanny — a pokrycie musi być WYŻSZE niż przy zwykłej karcie, bo skoro
# model nie wnosi przewagi, dowód ma nieść historia.
PROG_POKRYCIA_HYBRYDY = 0.60
# Ile punktów procentowych różnicy uznajemy za okazję — ta sama liczba, którą
# front nazywa „rozjazdem" (PROG_OKAZJI_PP), bo dwie bramy mówiące o tym samym
# nie mogą stać w dwóch różnych miejscach. Osobna stała, żeby dało się stroić
# wejście bez ruszania etykiety.
MIN_ROZJAZD_WEJSCIA = 12.0
# ⚑ RÓŻNICA KURSÓW W RANKINGU (2026-09-15, decyzja właściciela: „to już miało
# być, dołóż od razu, z głową"). Do dziś rozjazd był wyłącznie przepustką
# (hybryda) i etykietą, a karty ustawiała nasza przewaga — a ta dla drugiego
# szczebla porządkuje trafienia na poziomie rzutu monetą (AUC 0,47–0,51,
# księga 20.08–14.09), podczas gdy SAMA CENA porządkuje je lepiej (0,58).
# Tak typują eksperci BET EKIPA: „reszta rynku wycenia na 1,30, a STS daje
# 2,20" — wartość bierze się z tego, że jeden bukmacher się pomylił.
#
# WARTOŚĆ = szansa z OSTROŻNIEJSZEJ ceny (tańszej, po zdjęciu marży) minus
# szansa zapłacona w LEPSZEJ cenie. Karta awansuje o nadwyżkę ponad próg.
# Z GŁOWĄ, czyli trzy warunki, bez których rozjazd nie liczy się wcale:
#   * obie drabinki muszą się zgadzać (`betclic.porownaj_drabinke` odrzuca
#     przesunięte i niezgodne cenniki — inaczej „rozjazd" to dwa różne rynki),
#   * model uczony NIE MOŻE przeczyć: jeśli widzi szansę niższą niż płaci
#     lepsza cena, zakładamy, że to tańszy bukmacher się myli, nie drogi,
#   * pozostałe bramy karty zostają (minuty, skład, pokrycie, drugi szczebel).
# Efekt mierzymy stemplami w księdze (kurs_superbet/kurs_betclic/rozjazd_pp).
PROG_WARTOSCI_ROZJAZDU = 0.02
WAGA_WARTOSCI_ROZJAZDU = 1.0
# ile model uczony może być poniżej ceny, zanim uznamy, że przeczy rozjazdowi
TOLERANCJA_MODELU_ROZJAZDU = 0.02


def wartosc_rozjazdu(szczebel: dict | None) -> float:
    """Ile płaci lepsza cena ponad ostrożniejszą wycenę (0 = brak okazji).

    Zero także wtedy, gdy model uczony widzi szansę niższą niż płaci lepsza
    cena — patrz PROG_WARTOSCI_ROZJAZDU.
    """
    roz = (szczebel or {}).get("rozjazd") or {}
    try:
        sb, bc = float(roz.get("superbet") or 0), float(roz.get("betclic") or 0)
    except (TypeError, ValueError):
        return 0.0
    if sb <= 1.0 or bc <= 1.0 or sb == bc:
        return 0.0
    lepszy, gorszy = max(sb, bc), min(sb, bc)
    p_ostrozna = betting.implied_prob_one_sided(gorszy)
    wartosc = p_ostrozna - 1.0 / lepszy
    pu = ((szczebel or {}).get("p_uczony") or {}).get("p")
    if pu is not None and float(pu) < 1.0 / lepszy - TOLERANCJA_MODELU_ROZJAZDU:
        return 0.0
    return max(0.0, round(wartosc, 4))
# GÓRNA granica przewagi — brama zgody z rynkiem (pomiar 2026-07-27 na 336
# rozliczonych typach modelu, patrz betting.OKNO_ZGODY_*): im mocniej nasza
# szansa rozjeżdża się z ceną bukmachera, tym RZADZIEJ mamy rację.
#
# Drabinki nie miały tej bramy w ogóle, a ich ranking to dosłownie „kto
# najbardziej rozjeżdża się z kursem" — więc na szczyt trafiało to, co
# najpewniej jest błędem. Karta Fabio Fehra (FC Thun, 2026-07-28) stała
# 16 pp nad ceną rynku i była kartą numer 1 dnia.
#
# Tu liczymy ILORAZEM (nasza szansa / cena rynku), a nie różnicą w punktach
# jak przy typach modelu, bo drabinki żyją na zupełnie innych kursach: model
# typuje średnio po 1,50, a karta zaczyna się od 1,65 i sięga 4,0. Te same
# „10 punktów procentowych" to przy kursie 1,7 błąd o 18%, a przy 3,5 —
# o 38%. Pomiar w formie ilorazu (ROI +2,3% do 1,15x, −17,8% w 1,15–1,30x,
# −37,3% w 1,30–1,50x) skaluje się przez cały ten zakres.
MAX_ROZJAZD_KARTY = 1.25
# Udział meczów rozpoczętych w pierwszym składzie (z ostatnich rozegranych).
# Karta liczy wszystko z minut, których zmiennik po prostu nie dostanie.
MIN_UDZIAL_STARTOW = 0.6
OKNO_STARTOW = 10
# poziom ufności korekty próby: 7/10 -> ~57% zamiast naiwnych 70%
WILSON_K = 0.674            # ~75% jednostronnie

# --- KOREKTA KONTEKSTOWA (przebudowa 2026-07-26) ---
# Pokrycie linii mówi, co zawodnik robił PRZECIW KOMU INNEMU. Żeby karta
# odpowiadała na „gra z najlepszą defensywą, czemu miałby oddać 2 strzały?",
# liczymy DWIE prawdopodobieństwa z tego samego rozkładu NB (model/counts.py):
#
#   p_ref — historia płasko (bez wygaszania), minuty jak w próbie, zero kontekstu
#   p_ctx — historia wygaszana w czasie (forma), minuty PROGNOZOWANE, pełny
#           kontekst meczu (rywal, sędzia, scenariusz, dom, sezony)
#
# Ich iloraz to czysta korekta: wszystko, co wspólne (poziom gracza, prior,
# rozrzut), skraca się i zostaje tylko to, czym NADCHODZĄCY mecz różni się od
# przeciętnego meczu z próby. Tym ilorazem mnożymy pokrycie Wilsona — baza
# zostaje empiryczna i zgodna z tym, co karta pokazuje („trafione 8/10").
RADAR_TAU_DNI = 60.0        # wygaszanie historii w p_ctx = czynnik formy
PSEUDO_MECZE_PRIOR = 3.0    # słaby prior z własnej średniej: dodaje rozrzut
                            # przy krótkiej historii, nie przesuwa poziomu
KOREKTA_WIDELKI = (0.55, 1.60)   # kontekst koryguje, nie rządzi
P_FINAL_WIDELKI = (0.02, 0.97)
CAP_SEZONU = (0.85, 1.15)   # ile może ruszyć średnia z całych sezonów
# klasy jakości po przewadze nad kursem (pkt proc.). Progi są ZAŁOŻENIEM do
# skalibrowania z rozliczeń drabinek — dopiero własny strumień skuteczności
# powie, czy „top" faktycznie trafia lepiej niż „solidny".
PROG_KLASY = ((0.10, "top"), (0.06, "mocny"))


def _z_korekta_strumienia(p: float, delta: float) -> float:
    """Szansa po korekcie strumienia drabinek (delta w skali logitowej).

    Ta sama jednostka, co kalibracja modelu — dodanie delty do logitu ściąga
    (albo podnosi) całą skalę równomiernie, w odróżnieniu od mnożnika, który
    przy p bliskim 1 potrafi wyjechać poza zakres.
    """
    if not delta:
        return p
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return 1.0 / (1.0 + math.exp(-(math.log(p / (1.0 - p)) + delta)))


def _wilson_low(traf: int, z: int, k: float = WILSON_K) -> float:
    """Dolna granica ufności odsetka trafień — kara za krótką próbę.

    Bez tego 5/5 (100%) bije 8/10 (80%), choć druga próba jest dwa razy
    pewniejsza. Wzór Wilsona: im mniej meczów, tym mocniej ściąga w dół.
    """
    if z <= 0:
        return 0.0
    p = traf / z
    mian = 1.0 + k * k / z
    licz = p + k * k / (2 * z) - k * math.sqrt(
        (p * (1.0 - p) + k * k / (4 * z)) / z
    )
    return max(0.0, licz / mian)


def _mnoznik_sezonu(
    sezony: list[dict], rynek_kod: str, okno90: float | None,
) -> tuple[float, dict]:
    """Średnie z CAŁYCH sezonów vs poziom z ostatnich meczów.

    Sezonowa próba (30+ meczów) jest znacznie mocniejsza niż okno 10 spotkań,
    więc kiedy okno mówi „2,4 strzału", a dwa sezony „1,5", to okno jest
    najpewniej szczytem formy, nie nowym poziomem. Mnożnik działa na lambdę
    (czyli tylko w p_ctx), więc nie skraca się w ilorazie korekty.
    """
    probki = [
        (s["na90"][rynek_kod], float(s.get("minuty") or 0))
        for s in (sezony or [])
        if (s.get("na90") or {}).get(rynek_kod) is not None
        and (s.get("mecze") or 0) >= 8
    ]
    minuty = sum(m for _v, m in probki)
    if not probki or minuty <= 0 or not okno90 or okno90 <= 0:
        return 1.0, {}
    sezon90 = sum(v * m for v, m in probki) / minuty
    m = float(np.clip(sezon90 / okno90, *CAP_SEZONU))
    return m, {
        "sezon90": round(sezon90, 2), "okno90": round(okno90, 2),
        "mnoznik": round(m, 3),
    }


def _posteriory(
    grane: list[tuple[float, float, int]], teraz: int,
) -> tuple[object, object, float] | None:
    """(posterior wygaszany, posterior płaski, średnie minuty próby).

    Prior jest celowo słaby i wzięty z własnej średniej zawodnika — jego rolą
    jest dorzucić naddyspersję przy krótkiej historii (NB zamiast Poissona),
    a nie przesunąć poziom. Poziom niosą obserwacje.
    """
    if not grane:
        return None
    c = np.array([x[0] for x in grane], dtype=float)
    m = np.array([x[1] for x in grane], dtype=float)
    dni = np.array(
        [max(0.0, (teraz - x[2]) / 86400.0) for x in grane], dtype=float
    )
    minuty_sum = float(m.sum())
    if minuty_sum <= 0:
        return None
    sr90 = float(c.sum()) / minuty_sum * 90.0
    prior = counts_mod.GroupPrior(
        mean_per90=max(sr90, 0.05), pseudo_matches=PSEUDO_MECZE_PRIOR
    )
    post_swiezy = counts_mod.fit_posterior(
        c, m, dni, prior, tau_days=RADAR_TAU_DNI
    )
    # płaski = te same dane bez wygaszania (tau tak duże, że wagi ~1)
    post_plaski = counts_mod.fit_posterior(
        c, m, np.zeros_like(dni), prior, tau_days=RADAR_TAU_DNI
    )
    return post_swiezy, post_plaski, minuty_sum / len(grane)
UTID_MUNDIAL = 16           # MŚ nigdy nie jest „starą ligą" (lato 2026:
                            # każdy reprezentant wracał z mundialu)
# utid liczy się jako „rozgrywki drużyny" (nie stara liga zawodnika), gdy
# grało w nim >= tylu RÓŻNYCH kolegów z zespołu — łapie bieżącą fazę ligi
# (Apertura/Clausura), puchary klubu i mundial przy 2+ reprezentantach
MIN_KOLEGOW_WSPOLNY_UTID = 2

# minuty z historii bywają None/0 dla meczów bez występu
def _grane(tr: statshub.StatshubTrend) -> list[tuple[float, float, int]]:
    """(licznik, minuty, ts) wyłącznie z meczów faktycznie rozegranych."""
    return [
        (float(c), float(m), int(ts))
        for c, m, ts in zip(tr.counts, tr.minutes, tr.timestamps)
        if m and m >= MIN_MINUT_MECZU
    ]


# Ten sam mecz u dwóch źródeł (statshub / 365Scores / magazyn) ma znacznik
# czasu z dokładnością do godziny–dwóch (strefa, przesunięcie gwizdka);
# dwa mecze JEDNEJ drużyny nigdy nie dzielą mniej niż doba.
TOLERANCJA_MECZU_S = 4 * 3600
# tyle meczów drużyny wystarczy, żeby udział startów coś znaczył — mniej niż
# w starej mierze (5), bo tu każdy mecz jest rozstrzygnięty („był w XI" albo
# „nie było go"), a nie tylko „zagrał ileś minut"
MIN_MECZOW_DRUZYNY = 3
OKNO_STARTOW_S = 120 * 86400     # jak OKNO_SWIEZEJ_PROBY_S — nie liczymy zeszłego sezonu
# Kalendarz drużyny, którego najnowszy rozegrany mecz jest o tyle starszy niż
# najnowszy występ zawodnika, jest NIEAKTUALNY (magazyn nie odświeżył klubu)
# i nie może rozstrzygać o startach — patrz `dopelnij_meczami_druzyny`.
# 14 dni, bo przerwa reprezentacyjna daje do ~10 dni między ostatnim meczem
# klubu a meczem kadry, a klub odświeżany co dobę nie ma luki większej niż 2.
KALENDARZ_NIEAKTUALNY_S = 14 * 86400


def dopelnij_meczami_druzyny(
    tr: statshub.StatshubTrend, kalendarz: dict[int, list[int]] | None,
    teraz: int, okno: int = OKNO_STARTOW, tylko_pelna: bool = True,
) -> tuple[list[bool], list[float], list[int]] | None:
    """Historia zawodnika DOPEŁNIONA meczami drużyny, w których nie zagrał.

    ⚑ PO CO (2026-09-14, zgłoszenie właściciela: karta na zawodnika Como,
    „który nigdy nie wychodzi w podstawowym składzie"). Feed zawodnika ma
    tylko mecze, w których ZAGRAŁ. Rezerwowy z trzema występami po 70 minut
    w sezonie wyglądał więc jak etatowy starter: `started` = 3/3, udział
    startów 100%, model minut liczył mu 80 minut. Docstring modelu minut
    od początku wymagał „historii ostatnich meczów drużyny (uwzględniając
    mecze, w których zawodnik NIE zagrał)" — ale nikt mu jej nie dawał.

    Zwraca (started, minutes, timestamps) dla ostatnich `okno` ROZEGRANYCH
    meczów drużyny (od najnowszego); mecz bez występu → (False, 0.0, ts).
    None = nie znamy kalendarza tej drużyny (magazyn jej nie ma) — wołający
    MUSI wtedy wrócić do starej miary, nie udawać zera.

    ⚑ TYLKO PRZY PEŁNEJ HISTORII (2026-09-17). Mecz drużyny bez występu w
    historii zawodnika to „opuścił" wyłącznie wtedy, gdy historia zna każdy
    jego mecz (`historia_pelna`, performance). Feed propsów i statystyki 365
    znają część meczów — Hödl (Sturm) miał z nich 2 mecze na 10 w kalendarzu
    i wylatywał jako rezerwowy, grając 11 z 12. Z niepełną historią
    zwracamy None (nie wiemy); podejrzanych dociąga `dociagnij_pelne_wystepy`.
    `tylko_pelna=False` służy WYŁĄCZNIE do wytypowania podejrzanych.
    """
    if not kalendarz or tr.team_id is None:
        return None
    if tylko_pelna and not getattr(tr, "historia_pelna", False):
        return None
    try:
        ts_dr = kalendarz.get(int(tr.team_id)) or []
    except (TypeError, ValueError):
        return None
    # rozegrane = zaczęły się ponad 3 h temu (magazyn ma też mecze przyszłe
    # dopisane z terminarza, bez statystyk)
    # ⚑ OKNO STARTÓW NIE SIĘGA ZESZŁEGO SEZONU (2026-09-16). „Ostatnie 10
    # meczów drużyny" po sześciu kolejkach nowego sezonu zahaczało o maj:
    # Golovin (Monaco) grał 5 z 6 meczów od sierpnia, a brama widziała
    # 5 z 10, bo trzy majowe mecze (kontuzja) i jeden z lipca liczyły się
    # jak opuszczone. Okno to te same 120 dni, co świeżość próby zawodnika
    # (`OKNO_SWIEZEJ_PROBY_S` w build_wc_fast) — minimum MIN_MECZOW_DRUZYNY
    # zostaje, więc na starcie sezonu miara wraca do samych występów.
    rozegrane = sorted(
        (t for t in ts_dr if teraz - OKNO_STARTOW_S <= t <= teraz - 3 * 3600),
        reverse=True,
    )[:okno]
    if not rozegrane:
        return None
    wystepy = [
        (int(ts), bool(st), float(m or 0.0))
        for ts, st, m in zip(tr.timestamps, tr.started, tr.minutes) if ts
    ]
    # ⚑ KALENDARZ STARSZY NIŻ WYSTĘPY = NIE ZNAMY KALENDARZA (2026-09-15).
    # Magazyn odświeżał tylko kluby z zakresu drużynowego, więc reszta stała
    # od 18.08. Okno 10 „ostatnich" meczów sięgało wtedy do poprzedniego
    # sezonu, a świeże starty nie miały się z czym sparować — Tejon
    # (Marítimo, 6/6 startów w sezonie) wychodził „2 z 10". Wołający wraca do
    # starej miary, tak jak dla drużyny spoza magazynu.
    ostatni_wystep = max((w[0] for w in wystepy if w[2] > 0), default=0)
    if ostatni_wystep - rozegrane[0] > KALENDARZ_NIEAKTUALNY_S:
        return None
    # ⚑ PO TRANSFERZE OKNO ZACZYNA SIĘ OD PIERWSZEGO MECZU W NOWYM KLUBIE
    # (2026-09-15). Trossard w Beşiktaşu: 83, 90, 84, 66, 62 minut w pięciu
    # ostatnich meczach — a „udział startów" 0,5, bo pięć starszych meczów
    # drużyny rozegrano, zanim przyszedł. Dowodem transferu są jego występy,
    # których kalendarz tej drużyny nie zna, a które leżą PRZED pierwszym
    # meczem w niej. Minimum `MIN_MECZOW_DRUZYNY` zostaje, więc nowy
    # zawodnik z jednym występem na trzy mecze dalej jest rezerwowym.
    def _w_kalendarzu(ts: int) -> bool:
        return any(abs(ts - t) <= TOLERANCJA_MECZU_S for t in ts_dr)
    # Idziemy od najnowszego występu wstecz: ciąg występów zgodnych z kalendarzem
    # to gra w tym klubie, pierwszy występ SPOZA kalendarza kończy ciąg (inny
    # klub albo kadra przed transferem). Pojedyncze stare zbieżności godzin
    # (weekendowe gwizdki dwóch lig) nie przesuwają już początku okna.
    # Ciąg „gdzie indziej" musi mieć co najmniej DWA występy z rzędu: kalendarz
    # z feedu zna ~76% meczów drużyny, więc pojedynczy nieznany mecz pucharowy
    # udawałby transfer i ścinał okno rezerwowemu (Leonel Flores, Boca).
    pierwszy = None
    gdzie_indziej = False
    kolejne_obce = 0
    for t in sorted((w[0] for w in wystepy if w[2] > 0), reverse=True):
        if _w_kalendarzu(t):
            if kolejne_obce:
                break                      # pojedynczy obcy mecz — to nie transfer
            pierwszy = t
        else:
            kolejne_obce += 1
            if kolejne_obce >= 2 and pierwszy is not None:
                gdzie_indziej = True
                break
    if (gdzie_indziej and pierwszy is not None
            and pierwszy > rozegrane[-1] + TOLERANCJA_MECZU_S):
        po = [t for t in rozegrane if t >= pierwszy - TOLERANCJA_MECZU_S]
        rozegrane = rozegrane[:max(len(po), MIN_MECZOW_DRUZYNY)]
    started: list[bool] = []
    minuty: list[float] = []
    kiedy: list[int] = []
    for t in rozegrane:
        traf = min((w for w in wystepy if abs(w[0] - t) <= TOLERANCJA_MECZU_S),
                   key=lambda w: abs(w[0] - t), default=None)
        started.append(traf[1] if traf else False)
        minuty.append(traf[2] if traf else 0.0)
        kiedy.append(t)
    return started, minuty, kiedy


def polacz_wystepy(trendy: list) -> statshub.StatshubTrend | None:
    """Jeden trend z WSZYSTKIMI występami zawodnika, zebranymi ze wszystkich
    jego rynków — do bram składu (udział startów, „nie grał ostatnio").

    ⚑ PO CO (2026-09-16, audyt lejka). Feed propsów daje historię rynku
    TYLKO z meczów, w których bukmacherzy UK ten rynek kwotowali. Eric Dier
    (Monaco): „celne" z feedu znały 2 mecze tego sezonu, „strzały" z
    performance — wszystkie 6. Brama liczona na trendzie „celnych" widziała
    2 z 10 meczów drużyny i wyrzucała starter, który nie opuścił ani jednego.
    Zmierzone na parach z kursem Superbetu: 451 par „rzadko w XI", w których
    unia rynków tego samego zawodnika ma ≥5 występów w 120 dniach.

    Występ jest jeden, niezależnie od tego, ile rynków go zna: mecze sklejamy
    po znaczniku czasu (tolerancja jak przy kalendarzu), start = którykolwiek
    rynek mówi „start", minuty = najwięcej, co którykolwiek widział. Bazą
    jest trend z najdłuższą historią, więc kontekst (drużyna, rywal, sygnał
    składu) zostaje. Liczniki (`counts`) idą z bazy, a dla meczów spoza niej
    zero — bramy składu ich nie czytają; do prognozy dalej idzie trend rynku.
    """
    trendy = [t for t in (trendy or []) if t is not None]
    if not trendy:
        return None
    baza = max(trendy, key=lambda t: len(t.timestamps or []))
    if len(trendy) == 1:
        return baza
    mecze: list[list] = []   # [ts, started, minutes, count]
    for t in trendy:
        n = min(len(t.timestamps or []), len(t.minutes or []))
        st = list(t.started or [])
        cn = list(t.counts or [])
        for i in range(n):
            ts = int(t.timestamps[i] or 0)
            if not ts:
                continue
            m = float(t.minutes[i] or 0.0)
            s = bool(st[i]) if i < len(st) else m >= 60.0
            c = float(cn[i]) if (t is baza and i < len(cn)) else 0.0
            traf = next((w for w in mecze if abs(w[0] - ts) <= TOLERANCJA_MECZU_S), None)
            if traf is None:
                mecze.append([ts, s, m, c])
            else:
                traf[1] = traf[1] or s
                traf[2] = max(traf[2], m)
                if t is baza:
                    traf[3] = c
    mecze.sort(key=lambda w: -w[0])
    return dc_replace(
        baza,
        timestamps=[w[0] for w in mecze],
        started=[w[1] for w in mecze],
        minutes=[w[2] for w in mecze],
        counts=[w[3] for w in mecze],
        # unia z choć jednym trendem z performance zna KAŻDY mecz zawodnika
        historia_pelna=any(getattr(t, "historia_pelna", False) for t in trendy),
    )


# budżet zapytań performance na dociągnięcie pełnej historii zawodnikom, których
# niepełna historia wygląda na „rzadko w XI" (patrz dociagnij_pelne_wystepy)
MAX_PERF_UDZIAL = 150


def dociagnij_pelne_wystepy(
    wystepy: dict[int, statshub.StatshubTrend],
    kalendarz: dict[int, list[int]] | None,
    teraz: int,
    budzet: int = MAX_PERF_UDZIAL,
    kickoff: dict[int, int] | None = None,
    fetch=None,
    trendy_gracza: dict[int, list] | None = None,
) -> dict[str, int]:
    """Dociągnij z performance pełną historię tym, których NIEPEŁNA historia
    wygląda na rezerwowego — zanim brama składu ich odrzuci.

    ⚑ PO CO (2026-09-17, Hödl / Sturm Graz). Feed propsów nie miał go wcale,
    historia z 365 znała same puchary (2 mecze), a kalendarz drużyny 10 —
    brama widziała „w XI w 2 z 10". Performance: 11 startów z 12. Kalendarz
    orzeka „opuścił mecz" TYLKO przy pełnej historii (`historia_pelna`),
    więc bez tego kroku taki zawodnik byłby „nieznany" i przechodził bez
    kontroli — a prawdziwy rezerwowy z trzema występami razem z nim.
    Dociągamy więc tylko podejrzanych (kalendarz liczony na niepełnej
    historii mówi „rzadko" albo „nie grał ostatnio"), najbliższy kickoff
    pierwszy. Mutuje `wystepy` (unia feed + performance, flaga pełnej
    historii). Zwraca liczniki do rentgenu.

    `trendy_gracza` ({pid: [trendy rynków]}): pełna historia PODMIENIA też
    same trendy rynków (jak `odswiez_stare_trendy`), żeby bank trendów
    ją zapamiętał — bez tego każdy cykl dociągał tych samych ludzi od nowa
    (18.09 01:00: 7728 podejrzanych na budżet 150, bo nic nie zostawało).
    Rynki, których performance nie zna (zza pola, głową), zostają.
    """
    fetch = fetch or statshub.fetch_player_performance
    licz = {"podejrzani": 0, "dociagnieci": 0, "bez_budzetu": 0,
            "bez_danych": 0, "nadal_rzadko": 0, "bez_numeru_statshub": 0}
    if not kalendarz:
        return licz
    kolejka: list[tuple[int, int]] = []
    for pid, tr in wystepy.items():
        if tr is None or getattr(tr, "historia_pelna", False):
            continue
        dop = dopelnij_meczami_druzyny(tr, kalendarz, teraz, tylko_pelna=False)
        if not dop or len(dop[0]) < MIN_MECZOW_DRUZYNY:
            continue
        rzadko = sum(1 for st in dop[0] if st) / len(dop[0]) < MIN_UDZIAL_STARTOW
        nieobecny = all((m or 0) <= 0 for m in dop[1][:OKNO_NIEOBECNOSCI])
        if rzadko or nieobecny:
            # ⚑ NUMER SYNTETYCZNY Z 365 (2026-09-18). Performance go nie zna —
            # cykl 18.09 11:22: 150 z 150 budżetu „bez danych”, 0 dociągniętych.
            # Dociągnięci z prawdziwym numerem wypadają z kolejki (bank pamięta
            # `historia_pelna`), więc najbliższe kickoffy zapychali syntetyczni,
            # którym zapytanie nigdy nic nie da.
            if int(pid) >= 900_000_000:
                licz["bez_numeru_statshub"] += 1
                continue
            kolejka.append(((kickoff or {}).get(pid, 1 << 40), pid))
    licz["podejrzani"] = len(kolejka)
    kolejka.sort()
    for i, (_k, pid) in enumerate(kolejka):
        if i >= budzet:
            licz["bez_budzetu"] += 1
            continue
        tr = wystepy[pid]
        try:
            rows = fetch(int(pid))
        except Exception as e:                                 # noqa: BLE001
            diagnostyka.cichy("statshub", "performance_udzial", e)
            rows = None
        perf = (statshub.trendy_z_performance(int(pid), tr.player_name,
                                              tr.team_id, rows)
                if rows else {})
        if not perf:
            licz["bez_danych"] += 1
            continue
        pelny = polacz_wystepy([tr] + list(perf.values()))
        wystepy[pid] = pelny
        licz["dociagnieci"] += 1
        for t in (trendy_gracza or {}).get(pid) or []:
            s = perf.get(t.market_code)
            if s is None:
                continue
            t.counts, t.minutes = list(s.counts), list(s.minutes)
            t.timestamps, t.started = list(s.timestamps), list(s.started)
            t.game_positions = list(s.game_positions)
            t.game_opponents = list(s.game_opponents)
            t.game_opponent_ids = list(s.game_opponent_ids)
            t.game_utids = list(s.game_utids)
            t.historia_pelna = True
        u = udzial_startow(pelny, kalendarz=kalendarz, teraz=teraz)
        if u is not None and u < MIN_UDZIAL_STARTOW:
            licz["nadal_rzadko"] += 1
    return licz


def wystepy_zawodnikow(trends: list) -> dict[int, statshub.StatshubTrend]:
    """{player_id: trend z unią występów} dla całej listy trendów cyklu."""
    per: dict[int, list] = {}
    for t in trends or []:
        if t is not None and t.player_id:
            per.setdefault(t.player_id, []).append(t)
    return {pid: polacz_wystepy(ich) for pid, ich in per.items()}


def krotkie_wystepy(tr, okno: int = OKNO_FORMY_SITA) -> int | None:
    """Ile z ostatnich `okno` ROZEGRANYCH meczów trwało krócej niż
    MIN_MINUT_PELNEGO_WYSTEPU — sygnał rotacji (patrz nota przy
    PROG_POKRYCIA_SITA). None = brak historii.

    Z surowych minut, nie z `_grane`: 15-minutowe wejście też jest rotacją,
    choć do serii (MIN_MINUT_MECZU) się nie liczy."""
    if tr is None:
        return None
    grane = [float(m) for m in (tr.minutes or []) if m and float(m) > 0][:okno]
    if not grane:
        return None
    return sum(1 for m in grane if m < MIN_MINUT_PELNEGO_WYSTEPU)


def ostatni_wystep_min(tr) -> float | None:
    """Minuty OSTATNIEGO rozegranego meczu (sito v4). None = brak historii."""
    if tr is None:
        return None
    for m in (tr.minutes or []):
        if m and float(m) > 0:
            return float(m)
    return None


def udzial_startow(
    tr: statshub.StatshubTrend, okno: int = OKNO_STARTOW,
    kalendarz: dict[int, list[int]] | None = None, teraz: int | None = None,
) -> float | None:
    """Jaka część ostatnich meczów DRUŻYNY zaczynał w pierwszym składzie.

    Z kalendarzem drużyny (magazyn) liczymy naprawdę względem JEJ meczów:
    mecz, w którym go nie było, to mecz bez startu. Bez kalendarza zostaje
    stara miara z samych występów — a ta myli rezerwowego z tytularnym
    (patrz `dopelnij_meczami_druzyny`). None = za krótka historia.
    """
    if kalendarz and teraz is not None:
        dop = dopelnij_meczami_druzyny(tr, kalendarz, teraz, okno)
        if dop and len(dop[0]) >= MIN_MECZOW_DRUZYNY:
            return sum(1 for st in dop[0] if st) / len(dop[0])
    n = min(len(tr.started), len(tr.minutes), okno)
    if n < 5:
        return None
    return sum(1 for i in range(n) if tr.started[i]) / n


# Tyle ostatnich meczów drużyny bez ani minuty = zawodnik wypadł z gry
# (kontuzja, odsunięcie, transfer). Brama niezależna od udziału startów:
# etatowy starter po kontuzji ma dalej 7/10, a nie zagra.
OKNO_NIEOBECNOSCI = 3


def nie_gral_ostatnio(tr: statshub.StatshubTrend,
                      kalendarz: dict[int, list[int]] | None, teraz: int,
                      okno: int = OKNO_NIEOBECNOSCI) -> bool | None:
    """Czy opuścił CAŁE `okno` ostatnich meczów drużyny (None = nie wiemy).

    ⚑ 2026-09-15, zgłoszenie właściciela (Connell, Senesi w drabinkach).
    Connell: ostatni występ 22.08, drużyna od tej pory pięć meczów bez niego.
    """
    dop = dopelnij_meczami_druzyny(tr, kalendarz, teraz, okno=okno)
    if not dop or len(dop[1]) < okno:
        return None
    return all((m or 0) <= 0 for m in dop[1])


def gral_w_ostatnim_meczu(
    tr: statshub.StatshubTrend, kalendarz: dict[int, list[int]] | None,
    teraz: int, ostatni_ts: int | None = None,
) -> bool | None:
    """Czy zagrał (choć minutę) w OSTATNIM rozegranym meczu swojej drużyny.

    Najprostszy sygnał „jest w rotacji", gdy składu jeszcze nie ma — lista
    dnia (6:00) używa go jako drugiego szczebla po ogłoszonym/przewidywanym
    XI. `ostatni_ts` = ostatni mecz drużyny znany skądinąd (z feedu), gdy
    magazyn jej nie ma. None = nie wiemy, kiedy drużyna grała.
    """
    dop = dopelnij_meczami_druzyny(tr, kalendarz, teraz, okno=1)
    if dop:
        return dop[1][0] > 0
    if not ostatni_ts:
        return None
    return any(
        ts and abs(int(ts) - int(ostatni_ts)) <= TOLERANCJA_MECZU_S and (m or 0) > 0
        for ts, m in zip(tr.timestamps, tr.minutes)
    )


def liga_konsensus(
    trends: list[statshub.StatshubTrend],
) -> dict[int, tuple[int, set[int]]]:
    """Per drużyna: (dominująca liga, utidy wspólne dla >= 2 kolegów).

    Dominanta = moda utid-ów wszystkich meczów wszystkich graczy drużyny —
    wskazuje ligę domową bez zewnętrznej mapy klub->liga (zmierzone:
    Hearts->36, Sturm->45, Lech->202 z feedu Sturm–Hearts / AGF–Lech).

    Zbiór wspólnych utid-ów to ROZGRYWKI DRUŻYNY (bieżąca faza ligi,
    puchary, mundial przy 2+ reprezentantach) — sygnal_transferu nie może
    brać ich za „starą ligę" zawodnika (pomiar 2026-07-22: Apertura vs
    Clausura w Liga MX i CONCACAF Champions Cup wychodziły jako transfery).
    """
    liczniki: dict[int, Counter] = {}
    gracze_utidu: dict[int, dict[int, set[int]]] = {}  # tid -> utid -> pids
    widziani: set[tuple[int, int]] = set()  # (team_id, player_id) raz
    for t in trends:
        if not t.team_id or not t.game_utids:
            continue
        klucz = (t.team_id, t.player_id)
        if klucz in widziani:
            continue  # jeden rynek wystarczy — historia gier ta sama
        widziani.add(klucz)
        liczniki.setdefault(t.team_id, Counter()).update(
            u for u in t.game_utids if u
        )
        slot = gracze_utidu.setdefault(t.team_id, {})
        for u in set(t.game_utids):
            if u:
                slot.setdefault(u, set()).add(t.player_id)
    out: dict[int, tuple[int, set[int]]] = {}
    for tid, c in liczniki.items():
        if not c:
            continue
        wspolne = {
            u for u, pids in gracze_utidu.get(tid, {}).items()
            if len(pids) >= MIN_KOLEGOW_WSPOLNY_UTID
        }
        out[tid] = (c.most_common(1)[0][0], wspolne)
    return out


def sygnal_transferu(
    tr: statshub.StatshubTrend,
    liga_druzyny: int | None,
    utidy_druzyny: set[int] | None,
    teraz: int,
) -> dict | None:
    """Wykryj „nowego w drużynie" z historii jednego zawodnika.

    Dwa warianty:
      * zmiana_ligi — ostatnie mecze w innej lidze niż liga drużyny,
      * gral_przeciw — w ostatnich meczach grał PRZECIW obecnej drużynie
        (transfer wewnątrz ligi; własnej drużyny nie ma się w rywalach).

    „Starą ligą" nie mogą być rozgrywki, w których gra sama drużyna
    (utidy_druzyny) ani mundial — inaczej sezonowa zmiana fazy ligi
    (Apertura/Clausura), puchar klubu albo powrót z MŚ wygląda jak transfer.
    """
    utids = [u for u in tr.game_utids[:OKNO_TRANSFER] if u]
    if len(utids) < MIN_HISTORIA_TRANSFER:
        return None
    ost_ts = max((ts for _, _, ts in _grane(tr)), default=0)
    if not ost_ts or teraz - ost_ts > MAX_DNI_SWIEZOSC * 86400:
        return None  # dawno nie grał — to nie „świeży nabytek w rytmie"
    gral_przeciw = bool(
        tr.team_id
        and tr.team_id in tr.game_opponent_ids[:OKNO_GRAL_PRZECIW]
    )
    if not liga_druzyny:
        return None
    wykluczone = (utidy_druzyny or set()) | {liga_druzyny, UTID_MUNDIAL}
    n_nowa = sum(1 for u in utids if u == liga_druzyny)
    inne = Counter(u for u in utids if u not in wykluczone)
    zmiana_ligi = False
    utid_stara, n_stara = (None, 0)
    if inne:
        utid_stara, n_stara = inne.most_common(1)[0]
        zmiana_ligi = (
            n_nowa <= MAX_MECZE_W_NOWEJ
            and n_stara >= MIN_MECZE_W_STAREJ
            and n_stara >= 2 * max(n_nowa, 1)
        )
    # gral_przeciw wystarcza sam: mecz PRZECIW obecnej drużynie w ostatnich
    # OKNO_GRAL_PRZECIW występach = transfer co najwyżej sprzed kilku kolejek
    # (licznik meczów w lidze nic tu nie mówi — stary klub grał w tej samej)
    if not zmiana_ligi and not gral_przeciw:
        return None
    return {
        "powod": "zmiana_ligi" if zmiana_ligi else "gral_przeciw",
        "stara_liga_utid": utid_stara if zmiana_ligi else None,
        "mecze_stara": n_stara if zmiana_ligi else None,
        "mecze_nowa": n_nowa,
    }


def sygnal_formy(
    tr: statshub.StatshubTrend, drabinka: dict[float, float], teraz: int
) -> dict | None:
    """Seria trafień nad linią Superbetu w ostatnich meczach.

    Linia serii = NAJWYŻSZA kwotowana linia, nad którą zawodnik przeszedł
    w >= MIN_TRAFIEN_FORMA z OKNO_FORMY ostatnich występów, o ile jej kurs
    jest grywalny. Do tego kontrola trendu: średnia/90 okna wyraźnie ponad
    średnią wcześniejszej bazy (inaczej „seria" to po prostu poziom gracza).
    """
    grane = _grane(tr)
    if len(grane) < MIN_GIER_FORMA:
        return None
    okno, baza = grane[:OKNO_FORMY], grane[OKNO_FORMY:]
    if teraz - okno[0][2] > MAX_DNI_SWIEZOSC * 86400:
        return None
    min_okno = sum(m for _, m, _ in okno)
    min_baza = sum(m for _, m, _ in baza)
    if min_okno <= 0 or min_baza <= 0:
        return None
    per90_okno = sum(c for c, _, _ in okno) / min_okno * 90.0
    per90_baza = sum(c for c, _, _ in baza) / min_baza * 90.0
    if per90_baza <= 0 or per90_okno < MIN_BOOST_FORMY * per90_baza:
        return None
    najlepsza = None
    for linia, kurs in sorted(drabinka.items()):
        if kurs < MIN_KURS_FORMY:
            continue
        trafienia = sum(1 for c, _, _ in okno if c > linia)
        if trafienia >= MIN_TRAFIEN_FORMA:
            najlepsza = (linia, kurs, trafienia)
    if najlepsza is None:
        return None
    linia, kurs, trafienia = najlepsza
    return {
        "linia": linia,
        "kurs": kurs,
        "trafienia": trafienia,
        "okno": min(OKNO_FORMY, len(okno)),
        "srednia90_okno": round(per90_okno, 2),
        "srednia90_baza": round(per90_baza, 2),
    }


def _ten_sam_cykl_ligi(a: str, b: str) -> bool:
    """'Liga MX, Apertura' i 'Liga MX, Clausura' to JEDNA liga w dwóch
    fazach pod osobnymi utid-ami — porównujemy część przed przecinkiem."""
    pa = a.split(",")[0].strip().lower()
    pb = b.split(",")[0].strip().lower()
    return bool(pa) and pa == pb


def _klucze_dopasowane(klucze: set[str], nazwa: str) -> set[str]:
    """Wszystkie klucze norm_name z oferty Superbetu pasujące do nazwiska.

    Celowo LIBERALNE (podzbiór tokenów w obie strony, jak
    superbet.znajdz_zawodnika, ale bez wymogu jednoznaczności): tu chodzi
    o WYKLUCZENIE znanych graczy — lepiej pominąć wątpliwego debiutanta,
    niż flagować gwiazdę o podobnym nazwisku."""
    key = superbet.norm_name(nazwa)
    out = {key} if key in klucze else set()
    tokeny = set(key.split())
    if not tokeny:
        return out
    for k in klucze:
        tk = set(k.split())
        if tokeny <= tk or tk <= tokeny:
            out.add(k)
    return out


def debiutanci_meczu(
    sb_odds: dict,
    znane_nazwiska: list[str],
    team_ids: tuple[int, int],
    licznik_wyszukan: list[int],
    min_rynkow: int = MIN_RYNKOW_DEBIUTANTA,
    maks_kandydatow: int = MAX_DEBIUTANTOW_MECZU,
    budzet_wyszukan: int = MAX_WYSZUKAN_CYKL,
) -> list[dict]:
    """Zawodnicy kwotowani przez Superbet, nieobecni w feedzie statshub.

    licznik_wyszukan: jednoelementowa lista-mutowalny budżet zapytań
    /api/search współdzielony przez wszystkie mecze cyklu.

    `min_rynkow` — ile rynków musi mieć kandydat. Domyślne 2 to próg RADARU:
    karta z jednym rynkiem to za mało na analizę. Ale TABELA POKRYĆ ma inny
    cel — tam jeden kwotowany rynek to pełnoprawny wiersz, i akurat na
    kwalifikacjach pucharów bywa jedyny (Sparta Praga – Lyon, 03.08: 66
    zawodników i u każdego WYŁĄCZNIE kartka). Domyślny próg wycinał tam
    komplet kandydatów, więc strona zostawała pusta mimo pełnej oferty.
    """
    players = sb_odds.get("players") or {}
    names = sb_odds.get("player_names") or {}
    if not players:
        return []
    klucze = set(players.keys())
    znane: set[str] = set()
    for nazwa in znane_nazwiska:
        znane |= _klucze_dopasowane(klucze, nazwa)
    kandydaci = []
    for key, rynki in players.items():
        if key in znane:
            continue
        n_rynkow = sum(1 for mk, linie in rynki.items() if linie)
        if n_rynkow < min_rynkow:
            continue
        kandydaci.append((key in names, n_rynkow, key))
    out = []
    # ⚑ NAJPIERW KANDYDACI Z NAZWISKIEM W ORYGINALE (2026-09-15). Bez niego
    # zostaje klucz `norm_name` z członami posortowanymi alfabetycznie
    # („luongo massimo"), a wyszukiwarka statshuba trafia nim co trzeci raz.
    # Tacy kandydaci (stare wpisy pamięci Betclica) mieli najwięcej rynków,
    # więc szli pierwsi i zjadali budżet: 618 zapytań, 10 odkrytych.
    for _ma_nazwe, n_rynkow, key in sorted(kandydaci, reverse=True):
        if licznik_wyszukan[0] >= budzet_wyszukan:
            break
        if len(out) >= maks_kandydatow:
            break  # komplet kart tego meczu — nie pal budżetu dalej
        surowa = (names.get(key) or key).strip()
        if "," in surowa:
            # Superbet formatuje "Nazwisko, Imię" — wyszukiwarka statshub
            # tego nie rozumie (zmierzone 2026-07-25: "Sylla, Youssuf"
            # -> 0 trafień; "Youssuf Sylla" -> trafia)
            czesci = [c.strip() for c in surowa.split(",") if c.strip()]
            surowa = " ".join(reversed(czesci))
        licznik_wyszukan[0] += 1
        trafienia = statshub.search_players(surowa)
        profil = None
        for t in trafienia[:3]:
            if not t.get("id"):
                continue
            # nazwa z wyszukiwarki musi się zgadzać tokenowo z ofertą
            t_tok = set(superbet.norm_name(str(t.get("name") or "")).split())
            k_tok = set(key.split())
            if not (t_tok and (t_tok <= k_tok or k_tok <= t_tok)):
                continue
            p = statshub.fetch_player_profile(int(t["id"]))
            if p.get("team_id") in team_ids:
                profil = p
                break
        if profil is None:
            continue  # nie potwierdziliśmy przynależności — nie zgadujemy
        out.append({"klucz_sb": key, "nazwa": profil.get("name") or surowa,
                    "profil": profil})
    return out


def _korekta_linii(
    posty: tuple, minuty_proj: float, f_ctx: float, linia: float,
) -> tuple[float, float, float] | None:
    """(korekta, p_ctx, p_ref) dla jednej linii — patrz KOREKTA_WIDELKI."""
    post_swiezy, post_plaski, minuty_bazowe = posty
    p_ctx = counts_mod.predict_match(
        post_swiezy, minuty_proj, f_ctx
    ).p_over(linia)
    p_ref = counts_mod.predict_match(
        post_plaski, minuty_bazowe, 1.0
    ).p_over(linia)
    if p_ref <= 1e-6:
        return None
    return float(np.clip(p_ctx / p_ref, *KOREKTA_WIDELKI)), p_ctx, p_ref


def _rynki_wpisu(
    drabinki: dict[str, dict[str, float]],
    trendy_mk: dict[str, statshub.StatshubTrend],
    p_model_idx: dict[tuple[str, str, float], float],
    podmiot: str,
    nazwy_pl: dict[str, str],
    *,
    sedzia: dict | None = None,
    tempo: dict | None = None,
    is_home: bool | None = None,
    koncesje: kd.KoncesjeDruzyn | None = None,
    koncesje_nazw=None,
    nazwa_rywala: str | None = None,
    nazwa_druzyny: str | None = None,
    opp_id: int | None = None,
    minuty_proj: float | None = None,
    sezony: list[dict] | None = None,
    teraz: int = 0,
    korekta_logit: float = 0.0,
    diag: Counter | None = None,
    zrodla: dict[str, dict[str, str]] | None = None,
    wagi_modelu: dict | None = None,
    tabela_rywali: dict | None = None,
    # imienny rentgen: {rynek: powód}, czemu rynek NIE dał drabinki
    powody_rynkow: dict | None = None,
) -> list[dict]:
    """Sekcja `rynki` wpisu: przycięta drabinka kursów + pokrycie linii
    w ostatnich występach + forma i PEŁNY kontekst meczu per rynek.

    `zrodla` (rynek -> "linia" -> nazwa bukmachera) niesie WYJĄTKI od Superbetu.
    Siatka kursów bierze wyższą z dwóch cen, więc bez tego szczebel pokazywałby
    cenę Betclica podpisaną cudzym nazwiskiem — patrz `zrodla_kursow`.

    Każdy szczebel dostaje `p_final` — pokrycie Wilsona przemnożone przez
    korektę kontekstową (rywal na tym rynku, sędzia przy faulach, scenariusz
    meczu, dom/wyjazd, średnie sezonowe, forma i prognoza minut). To ta liczba,
    nie surowe „8/10", decyduje o wyborze i kolejności kart.

    `korekta_logit` — nauka z WŁASNYCH rozliczeń drabinek (patrz `zbuduj`).
    Wchodzi na samym końcu, po korekcie kontekstowej, więc karta pokazuje
    szansę już poprawioną o to, jak strumień radził sobie naprawdę."""
    out = []
    for mk, linie in drabinki.items():
        if not linie:
            if powody_rynkow is not None:
                powody_rynkow[mk] = "bez_linii_powyzej"
            continue  # rynek bez kursów „powyżej" = pusta drabinka, bez sensu
        tr = trendy_mk.get(mk)
        grane = _grane(tr) if tr is not None else []
        okno = grane[:OSTATNIE_N]
        if powody_rynkow is not None and not grane:
            powody_rynkow[mk] = "bez_historii_rynku"
        # RYNEK MUSI BYĆ JEGO RYNKIEM. Obrońca z jednym celnym strzałem głowy
        # na dziesięć meczów nie ma „rynku celnych głową" — ma przypadek.
        # Liczymy mecze z niezerowym wynikiem, nie sumę: 0,0,0,0,4 to jeden
        # mecz, w którym coś się wydarzyło, a nie seria.
        if okno and sum(1 for c, _m, _t in okno if c > 0) < MIN_NIEZEROWYCH_RYNKU:
            if powody_rynkow is not None:
                powody_rynkow[mk] = "za_malo_niezerowych"
            continue
        # --- KONTEKST MECZU dla tego rynku (mnożniki lambdy) ---
        posty = _posteriory(grane, teraz) if grane else None
        lacznie_min = sum(m for _c, m, _t in grane)
        srednia90 = (
            sum(c for c, _m, _t in grane) / lacznie_min * 90.0
            if lacznie_min > 0 else None
        )
        f_rywal, opis_rywal = kd.mnoznik_rywala(
            mk, tr, koncesje, opp_id,
            (tr.position if tr is not None else None), teraz,
            koncesje_nazw=koncesje_nazw,
            nazwa_rywala=nazwa_rywala,
            nazwa_druzyny=nazwa_druzyny,
        )
        f_sedzia, opis_sedzia = kd.mnoznik_sedziego(mk, sedzia)
        f_scen, opis_scen = kd.mnoznik_scenariusza(mk, tempo, is_home)
        f_dom, opis_dom = kd.mnoznik_domu(mk, is_home)
        f_sezon, opis_sezon = _mnoznik_sezonu(sezony or [], mk, srednia90)
        f_ctx = context_mod.cap(
            f_rywal * f_sedzia * f_scen * f_dom * f_sezon,
            context_mod.CAP_COMBINED,
        )
        sufit_linii = MAX_LINIA_RYNKU.get(mk, MAX_LINIA_DOMYSLNA)
        drabinka = []
        for linia_s, kurs in sorted(linie.items(), key=lambda kv: float(kv[0])):
            if float(linia_s) > sufit_linii:
                # GDZIE GINIE DRUGI SZCZEBEL (2026-08-08). Sufit linii ucina tu
                # NASTĘPNIK już zbudowanej drabinki — czyli dokładnie to, czego
                # user szuka na karcie. Bez licznika „karta jednoszczeblowa"
                # wygląda tak samo, jakby bukmacher po prostu nie kwotował.
                if diag is not None and len(drabinka) == 1:
                    diag["nastepnik_ucialy_sufit_linii"] += 1
                break   # linie posortowane rosnąco — wyżej już nic nie weźmiemy
            if not drabinka and kurs < MIN_KURS_PIERWSZEGO:
                if diag is not None:
                    diag["start_pominiety_przez_cene"] += 1
                continue  # drabinka startuje od pierwszej grywalnej ceny
            if len(drabinka) >= MAX_SZCZEBLI:
                break
            linia = float(linia_s)
            p = p_model_idx.get((podmiot, mk, linia))
            # od 3. szczebla: linie z ~0% szans / kosmicznym kursem = szum;
            # wyższe linie będą tylko gorsze, więc ucinamy resztę drabinki
            if len(drabinka) >= 2 and (
                (p is not None and p < MIN_P_SZCZEBLA)
                or kurs > MAX_KURS_SZCZEBLA
            ):
                break
            szczebel = {
                "linia": linia, "kurs": kurs,
                "p_model": round(p, 3) if p is not None else None,
            }
            # ⚑ DRUGA LICZBA Z MODELU UCZONEGO (2026-08-17) — liczona OBOK
            # rachunku drabinki i nie wpływająca na wybór ani kolejność kart.
            # Drabinki stoją na pokryciu Wilsona przemnożonym przez mnożniki
            # kontekstu, czyli na jeszcze innym rachunku niż silnik zawodniczy
            # — a to właśnie ta klasa różnic kosztowała nas najwięcej
            # (jeden strumień, jeden zestaw warstw, patrz
            # [[model-nie-ma-pamieci-druzyn]]). Stempel pozwoli porównać oba
            # na TYCH SAMYCH szczeblach, po rozliczeniu.
            if wagi_modelu and tr is not None:
                try:
                    _pu = uczony.prognoza_zawodnika(
                        wagi_modelu,
                        {
                            "counts": list(tr.counts or []),
                            "minutes": list(tr.minutes or []),
                            "timestamps": list(tr.timestamps or []),
                            "started": list(tr.started or []),
                            "game_positions": list(tr.game_positions or []),
                            "league_average": tr.league_average,
                            "opponent_average": tr.opponent_average,
                            "is_home": bool(tr.is_home),
                            "opponent_id": tr.opponent_id,
                            "position": tr.position,
                            "market_code": mk,
                        },
                        mk, linia, "powyzej",
                        oczekiwane_minuty=minuty_proj,
                        do_ts=teraz or None,
                        tabela_rywali=tabela_rywali,
                    )
                except Exception as e:                          # noqa: BLE001
                    diagnostyka.cichy("radar", "model_uczony", e)
                    _pu = None
                if _pu:
                    szczebel["p_uczony"] = _pu
                    if diag is not None:
                        diag["model_uczony_policzony"] += 1
                elif diag is not None:
                    diag["model_uczony_bez_pokrycia"] += 1
            # u kogo ta cena jest do wzięcia — zapisujemy tylko wtedy, gdy to
            # NIE Superbet, więc front ma domyślną nazwę i nie musi jej znać
            _kto = ((zrodla or {}).get(mk) or {}).get(str(linia)) \
                or ((zrodla or {}).get(mk) or {}).get(linia_s)
            if _kto:
                szczebel["bukmacher"] = _kto
            if okno:
                # POKRYCIE: ile z ostatnich występów przebiło tę linię —
                # rdzeń analizy tipsterskiej ("2+ trafione w 8/10")
                traf = sum(1 for c, _, _ in okno if c > linia)
                szczebel["pokrycie"] = {"traf": traf, "z": len(okno)}
                # FORMA: to samo na ostatnich 5 — sito patrzy na obie liczby
                # (patrz nota przy PROG_POKRYCIA_SITA)
                okno5 = okno[:OKNO_FORMY_SITA]
                szczebel["pokrycie5"] = {
                    "traf": sum(1 for c, _, _ in okno5 if c > linia),
                    "z": len(okno5)}
                # SZANSA PO KONTEKŚCIE: pokrycie Wilsona × korekta meczowa.
                # Bez prognozy minut nie ma czego rzutować na mecz.
                kor = (
                    _korekta_linii(posty, minuty_proj, f_ctx, linia)
                    if posty and minuty_proj else None
                )
                if kor is not None:
                    p_baz = _wilson_low(traf, len(okno))
                    szczebel["p_bazowe"] = round(p_baz, 3)
                    szczebel["korekta"] = round(kor[0], 3)
                    szczebel["p_final"] = round(
                        float(np.clip(
                            _z_korekta_strumienia(
                                p_baz * kor[0], korekta_logit
                            ),
                            *P_FINAL_WIDELKI,
                        )), 3
                    )
            drabinka.append(szczebel)
        # ROZKŁAD SZANSY DRUGIEGO SZCZEBLA — zbierany ZANIM cokolwiek utniemy.
        # Sam licznik „ilu nie przeszło" nie mówi, gdzie postawić próg: przy
        # 0,33 wygląda tak samo świat, w którym następniki mają po 0,32, jak
        # ten, w którym mają po 0,10. Koszyki odpowiadają na to jednym
        # przebiegiem, zamiast strojenia progu po omacku.
        if diag is not None and len(drabinka) >= 2:
            p2 = drabinka[1].get("p_final")
            if p2 is not None:
                prog_k = (
                    "00-10" if p2 < 0.10 else "10-20" if p2 < 0.20
                    else "20-25" if p2 < 0.25 else "25-30" if p2 < 0.30
                    else "30-33" if p2 < 0.33 else "33-40" if p2 < 0.40
                    else "40+"
                )
                diag[f"p2_{prog_k}"] += 1
        # DRUGI SZCZEBEL MA BYĆ REALNY — patrz MIN_P_DRUGIEGO_SZCZEBLA.
        for i, s in enumerate(drabinka):
            p_f = s.get("p_final")
            if i >= 1 and p_f is not None and p_f < prog_nastepnika(drabinka[i - 1].get("kurs")):
                if diag is not None and i == 1:
                    diag["nastepnik_ponizej_progu_szansy"] += 1
                drabinka = drabinka[:i]
                break
        # SZCZEBLE-ŚMIECI PRECZ. „Celne głową 1,5 — trafione 0/10, kurs 33,0"
        # nie niesie żadnej informacji poza tym, że bukmacher kwotuje wszystko.
        # Szczeble bez pokrycia (gołe drabinki, brak historii) zostają — tam
        # nie mamy czym oceniać, a UI mówi wprost, że historii nie znamy.
        przed_smieciami = len(drabinka)
        drabinka = [
            s for s in drabinka
            if (s.get("pokrycie") or {}).get("traf", MIN_TRAF_SZCZEBLA)
            >= MIN_TRAF_SZCZEBLA
        ]
        if diag is not None and przed_smieciami > 1 and len(drabinka) == 1:
            diag["nastepnik_trafiony_mniej_niz_dwa_razy"] += 1
        if not drabinka:
            if powody_rynkow is not None:
                powody_rynkow[mk] = (
                    "bez_pokrycia_szczebli" if przed_smieciami else
                    "start_za_tani_lub_sufit")
            continue
        if powody_rynkow is not None:
            powody_rynkow.pop(mk, None)     # rynek dał drabinkę
        za_drobne = None
        if len(drabinka) >= 2:
            _ost = float(drabinka[-1]["linia"])
            for _l_s, _k in sorted(linie.items(), key=lambda kv: float(kv[0])):
                _l = float(_l_s)
                if _l <= _ost + 1e-9:
                    continue
                if _l <= _ost + 1.0 + 1e-9 and _k and float(_k) <= MAX_KURS_ZA_DROBNE:
                    za_drobne = {"linia": _l, "kurs": _k}
                    if okno:
                        za_drobne["pokrycie"] = {
                            "traf": sum(1 for c, _, _ in okno if c > _l),
                            "z": len(okno)}
                    _kto3 = ((zrodla or {}).get(mk) or {}).get(str(_l))                         or ((zrodla or {}).get(mk) or {}).get(_l_s)
                    if _kto3:
                        za_drobne["bukmacher"] = _kto3
                break
        rec: dict = {
            "rynek_kod": mk,
            "rynek": nazwy_pl.get(mk, mk),
            "drabinka": drabinka,
            # WSZYSTKIE kwotowane linie, nie tylko opublikowane szczeble
            # (2026-08-04). Porównanie cen z drugim bukmacherem wymaga co
            # najmniej DWÓCH wspólnych linii — inaczej nie wiadomo, czy obaj
            # liczą to samo (drabinki potrafią zachodzić przesunięte o szczebel).
            # Karta pokazuje drabinkę przyciętą do tego, co grywalne, więc
            # bywa jednoszczeblowa i wtedy porównanie nie miało z czego powstać:
            # zmierzone 04.08 na Matíasie Verze — jedna nasza linia wobec dwóch
            # u Betclica, porównanie odrzucone jako „za mało wspólnych".
            #
            # Rozdzielamy więc DWIE RÓŻNE RZECZY: na czym SPRAWDZAMY zgodność
            # cenników (pełna lista) i co POKAZUJEMY userowi (przycięta
            # drabinka). Weryfikacja dostaje komplet dowodów, karta zostaje
            # krótka.
            **({"za_drobne": za_drobne} if za_drobne else {}),
            "linie_pelne": {str(k): v for k, v in sorted(
                ((float(l), kurs) for l, kurs in linie.items()),
            )},
            # WODOSPAD KONTEKSTU — karta ma powiedzieć wprost, czemu ścinamy
            # albo podbijamy pokrycie. Puste sekcje (np. sędzia bez obsady)
            # zostają z etykietą źródła, żeby UI mogło napisać „nie wiemy".
            "kontekst": {
                "rywal": opis_rywal,
                "sedzia": opis_sedzia,
                "scenariusz": opis_scen,
                "dom": opis_dom,
                "sezony": opis_sezon,
                "lacznie": round(f_ctx, 3),
            },
        }
        if tr is not None:
            N = OSTATNIE_N
            rec["ostatnie"] = [int(c) for c, _, _ in grane[:N]]
            rec["minuty"] = [int(m) for _, m, _ in grane[:N]]
            rec["rywale"] = [
                str(o) for (o, m) in zip(tr.game_opponents, tr.minutes)
                if m and m >= MIN_MINUT_MECZU
            ][:N]
            if srednia90 is not None:
                rec["srednia90"] = round(srednia90, 2)
            # FORMA okno-vs-baza (informacyjnie, na KAŻDYM rynku z historią;
            # sygnal_formy zostaje osobno jako rzadka plakietka "seria")
            if len(grane) >= MIN_GIER_FORMA - 2:
                okno_f, baza = grane[:OKNO_FORMY], grane[OKNO_FORMY:]
                m_o = sum(m for _, m, _ in okno_f)
                m_b = sum(m for _, m, _ in baza)
                if m_o > 0 and m_b > 0:
                    rec["forma"] = {
                        "okno90": round(
                            sum(c for c, _, _ in okno_f) / m_o * 90.0, 2
                        ),
                        "baza90": round(
                            sum(c for c, _, _ in baza) / m_b * 90.0, 2
                        ),
                    }
            # KONTEKST RYWALA: ile rywal średnio ODDAJE na tym rynku i jak
            # wypada na tle ligi (gotowe agregaty z feedu statshub)
            if tr.opponent_average is not None or tr.opponent_rank is not None:
                rec["rywal"] = {
                    "srednia": tr.opponent_average,
                    "rank": tr.opponent_rank,
                    "z": tr.total_ranks,
                    "liga": tr.league_average,
                }
        out.append(rec)
    # KOLEJNOŚĆ RYNKÓW WEDŁUG JAKOŚCI, NIE WEDŁUG LISTY (zmiana 2026-07-27).
    # Dotąd rynki szły w stałej kolejności ważności (strzały przed spalonymi),
    # więc na górze karty lądował rynek „ważny", a nie rynek DOBRY. Teraz każdy
    # dostaje ocenę: najlepszy szczebel liczony jako surowe pokrycie × kurs,
    # czyli ile złotówek wróciłoby ze złotówki, gdyby pokrycie było prawdą.
    # Przy tym samym pokryciu wygrywa wyższy kurs — a to dokładnie oznacza
    # rynki niszowe (strzały zza pola, głową), gdzie bukmacher kwotuje grubiej
    # niż na zwykłych strzałach po 1,25.
    def _jakosc(r: dict) -> float:
        best = 0.0
        for s in r.get("drabinka", []):
            p = s.get("pokrycie")
            if p and p.get("z"):
                best = max(best, p["traf"] / p["z"] * float(s["kurs"]))
        return best

    kolejnosc_rynku = {mk: i for i, mk in enumerate(RYNKI_PODSTAWOWE)}
    out.sort(key=lambda r: (
        "ostatnie" not in r,
        -_jakosc(r),
        kolejnosc_rynku.get(r["rynek_kod"], len(RYNKI_PODSTAWOWE)),
        r["rynek_kod"],
    ))
    if not any("ostatnie" in r for r in out):
        return out[:MAX_RYNKOW_BEZ_HISTORII]  # sama drabinka = bez ściany
    # SUFIT RYNKÓW NA KARCIE: dziewięć rynków to nie analiza, tylko wypis
    # wszystkiego, co Superbet kwotuje. Zostają trzy najlepsze.
    return out[:MAX_RYNKOW_KARTY]


def _p_po_strzyzeniu(s: dict | None) -> float | None:
    """Szansa szczebla po tym samym ścięciu, które robi `_oceń_karte`.

    Gdy model liczy niżej niż pokrycie z historii, bierzemy średnią z obu —
    bo dwa źródła, które się nie zgadzają, nie dają pewności jednego z nich.
    Ocena DRUGIEGO szczebla musi używać tej samej liczby co ocena hero,
    inaczej brama przepuszczałaby szczeble, które i tak zaraz spadną poniżej
    progu (a user zobaczyłby na karcie inną szansę, niż przeszła selekcję).
    """
    if not s:
        return None
    p_final = s.get("p_final")
    if p_final is None:
        return None
    p_mod = s.get("p_model")
    if p_mod is not None and float(p_mod) < float(p_final):
        return round((float(p_final) + float(p_mod)) / 2.0, 3)
    return float(p_final)


def _oceń_karte(
    w: dict,
    powody: Counter | None = None,
    pomiar_out: list | None = None,
    powody_pomiaru: Counter | None = None,
    statystyki: Counter | None = None,
) -> tuple[float, dict | None]:
    """Ocena karty: (score, najlepszy_szczebel) albo (0.0, None) gdy odpada.

    Score = REALNA PRZEWAGA nad kursem: `p_final − 1/kurs`, gdzie p_final to
    pokrycie Wilsona po korekcie kontekstowej (rywal na tym rynku, sędzia przy
    faulach, scenariusz meczu, forma, prognoza minut, średnie sezonowe).
    Mnożników „na wierzchu" już nie ma — cały kontekst siedzi w p_final, więc
    score jest w tych samych jednostkach co rzeczywistość i da się go rozliczyć.

    Dodatkowo p_model (pełny silnik, gdy policzył tę linię) działa jako
    STRZYŻENIE, nigdy jako podbicie: gdy model widzi mniej niż my, schodzimy
    w połowie drogi do niego. Dwie niezależne estymaty w rozjeździe to powód
    do ostrożności, a nie do wybierania wygodniejszej.

    Karta bez ani jednej linii przechodzącej bramy NIE powstaje: sygnały same
    z siebie nie wystarczają (koniec z „Lewandowski, bo transfer").

    pomiar_out — kolektor SZCZEBLI POMIAROWYCH: linie odrzucone wyłącznie
    progiem pokrycia i mieszczące się w tolerancji NEAR_POKRYCIA (patrz tam).
    Zbieramy je, żeby rozliczyły się w tle i dały odpowiedź, czy 0,5 to dobry
    próg. Bramy karty (minuty, udział startów) obowiązują tak samo — pomiar ma
    porównywać rzeczy porównywalne, a nie zawodników, których i tak nie gramy.

    powody_pomiaru — licznik diagnostyczny: gdzie giną szczeble z przedziału
    pomiarowego. Bez niego pusty pomiar wygląda identycznie jak brak takich
    szczebli w ofercie, a to dwie zupełnie różne sytuacje.
    """
    # BRAMA MINUT (sito v4, nota przy PROG_POKRYCIA_SILY): rotację zdradza
    # OSTATNI występ i liczba krótkich w ostatnich 5, nie średnia z 6 — jeden
    # krótki mecz w środku serii nie robi z zawodnika zmiennika. Ogłoszona XI
    # przebija oba sygnały (jak w `sila_linii`). Karta bez pola `ostatni_
    # wystep_min` (starsza ścieżka) zostaje przy dawnej bramie średniej.
    if w.get("xi") is not True:
        _ost = w.get("ostatni_wystep_min")
        if _ost is not None:
            if float(_ost) < MIN_MINUT_KARTY:
                if powody is not None:
                    powody["ostatni_wystep_krotki"] += 1
                return 0.0, None
        elif (w.get("minuty_sr6") or 0) < MIN_MINUT_KARTY:
            if powody is not None:
                powody["za_malo_minut"] += 1
            return 0.0, None
        if (w.get("krotkie_wystepy5") or 0) >= MIN_KROTKICH_KARY:
            if powody is not None:
                powody["rotacja_krotkie_wystepy"] += 1
            return 0.0, None
    # czy on w ogóle regularnie WYCHODZI w pierwszym składzie: średnia minut
    # potrafi wyglądać dobrze u kogoś, kto raz zagrał 90 minut, a poza tym
    # siedzi. Cała analiza karty stoi na minutach, których rezerwowy nie dostanie.
    udzial = w.get("udzial_startow")
    if udzial is not None and udzial < MIN_UDZIAL_STARTOW and w.get("xi") is not True:
        if powody is not None:
            powody["rzadko_w_pierwszym_skladzie"] += 1
        return 0.0, None
    # wypadł z gry w ostatnich meczach drużyny — ogłoszony skład to przebija
    if w.get("nie_gral_ostatnio") is True and w.get("xi") is not True:
        if powody is not None:
            powody["nie_gral_w_ostatnich_meczach"] += 1
        return 0.0, None
    # -inf, nie 0: linia wpuszczona jako MOCNA SERIA ma prawo mieć ujemną
    # przewagę (patrz MIN_EDGE_SERII), więc próg 0,0 wycinałby dokładnie te
    # karty, dla których druga ścieżka powstała
    best_score, best_s = float("-inf"), None
    best_klucz: tuple = (-1, 0.0, float("-inf"))
    pomiar_score, pomiar_s = float("-inf"), None
    # najlepsza linia rynku bez karty, która przeszła sito — do pomiaru
    pomiar_rynku_score, pomiar_rynku_s = float("-inf"), None
    lokalne: Counter = Counter()
    for r in w.get("rynki", []):
        szczeble = r.get("drabinka", [])
        for i, s in enumerate(szczeble):
            # DRABINKA MUSI MIEĆ DRUGI SZCZEBEL (2026-08-08, decyzja usera).
            # Zmierzone na 20 żywych kartach: 12 miało JEDEN szczebel, 8 dwa,
            # trzeciego nie miała ani jedna — czyli w większości sprzedawaliśmy
            # pojedynczy typ pod nazwą „drabinka". User: „drugi szczebel bardzo
            # często siada i jest jakby głównym celem, żeby go upolować".
            # Szczebel bez realnego następnika nie zostaje więc nagłówkiem
            # karty — nie ma czego polować.
            nast = szczeble[i + 1] if i + 1 < len(szczeble) else None
            p_nast = _p_po_strzyzeniu(nast)
            # ILE RAZY DRUGI SZCZEBEL WCHODZIŁ — twarda liczba z historii,
            # niezależna od naszego ścinania szansy (patrz MIN_POKRYCIE_DRUGIEGO)
            pok_nast = (nast or {}).get("pokrycie") or {}
            udzial_nast = (
                pok_nast["traf"] / pok_nast["z"]
                if pok_nast.get("z") else None
            )
            p = s.get("pokrycie")
            if not p or p["z"] < MIN_PROBA_SCORE:
                lokalne["krotka_proba"] += 1
                continue
            if s["kurs"] < MIN_KURS_SCORE:
                lokalne["kurs_ponizej_progu"] += 1
                continue
            # rynek, który nie daje kart w ogóle (patrz RYNKI_BEZ_KARTY) —
            # osobny licznik, bo to decyzja o RYNKU, nie o tej konkretnej linii
            bez_karty = r.get("rynek_kod") in RYNKI_BEZ_KARTY
            if bez_karty:
                lokalne["rynek_bez_karty"] += 1
                # bez kolektora pomiaru — jak dotąd; z kolektorem linia idzie
                # przez WSZYSTKIE bramy jak zwykła (nie jak pomiarowa), ale
                # nigdy nie zostaje hero (patrz POWOD_POMIARU_RYNKU)
                if pomiar_out is None:
                    continue
            # SZCZEBEL POMIAROWY: pokrycie pod progiem, ale w tolerancji.
            # Nie przerywamy od razu — przepuszczamy go przez WSZYSTKIE
            # pozostałe bramy, żeby zmierzyć wyłącznie efekt progu pokrycia,
            # a nie „reszty świata". Na koniec i tak nie wraca jako hero.
            pokrycie = p["traf"] / p["z"]
            pomiarowy = pokrycie < PROG_POKRYCIA_KARTY
            if pomiarowy:
                lokalne["slabe_pokrycie"] += 1
                if pokrycie < PROG_POKRYCIA_KARTY - NEAR_POKRYCIA:
                    if powody_pomiaru is not None:
                        powody_pomiaru["daleko_pod_progiem"] += 1
                    continue
                if powody_pomiaru is not None:
                    powody_pomiaru["w_przedziale"] += 1
                if pomiar_out is None:
                    continue
            # DRABINKA MUSI MIEĆ DRUGI SZCZEBEL (2026-08-08, decyzja usera).
            # Zmierzone na 20 żywych kartach: 12 miało JEDEN szczebel, 8 dwa,
            # trzeciego nie miała ani jedna — czyli w większości sprzedawaliśmy
            # pojedynczy typ pod nazwą „drabinka". User: „drugi szczebel bardzo
            # często siada i jest jakby głównym celem, żeby go upolować".
            #
            # SZCZEBLA POMIAROWEGO TO NIE DOTYCZY, i to nie jest wygodnictwo:
            # pomiarowy ma pokrycie 0,40–0,50, a następnik (linia wyżej) zawsze
            # niższe, więc progu 0,50 nie przeszedłby NIGDY. Brama zabiłaby więc
            # cały pomiar progu pokrycia (patrz NEAR_POKRYCIA), zamiast zmierzyć
            # go osobno. Pomiarowy i tak nie wraca jako hero.
            if not pomiarowy:
                # DROGA KARTA MUSI MIEĆ SERIĘ (decyzja usera 2026-08-08).
                # Powyżej 2,50 sam kurs nie wystarcza: bez fauli to wciąż
                # −35,7%, a z serią 7+/10 zostają te karty, które user pokazuje
                # jako wzorcowe — drugi szczebel po 3,50–5,50 z historią.
                # TU, A NIE WYŻEJ, z tego samego powodu co brama drugiego
                # szczebla: pomiarowy ma pokrycie 0,40–0,50, więc progu 0,70
                # nie przeszedłby NIGDY i brama zjadłaby cały pomiar progu.
                if s["kurs"] >= CENA_WYMAGAJACA_SERII \
                        and pokrycie < PROG_POKRYCIA_DROGIEJ:
                    lokalne["droga_bez_serii"] += 1
                    continue
                if udzial_nast is not None \
                        and udzial_nast < MIN_POKRYCIE_DRUGIEGO:
                    lokalne["drugi_szczebel_rzadko_wchodzil"] += 1
                    continue
                # …i nie zgasł ostatnio: ≤1 z 5 wchodził 10% przy cenie 30%
                # (patrz nota przy PROG_POKRYCIA_SITA)
                _f_nast = (nast or {}).get("pokrycie5") or {}
                if _f_nast.get("z") and _f_nast["traf"] < MIN_FORMA_DRUGIEGO:
                    lokalne["drugi_szczebel_bez_formy"] += 1
                    continue
                if p_nast is None or p_nast < prog_nastepnika(s["kurs"]):
                    # CZTERY RÓŻNE DIAGNOZY, nie jedna ([[ciche-odrzucenia-zasada]]):
                    # drabinka jednoszczeblowa z powodu sufitu linii albo braku
                    # oferty, następnik za słaby, następnik bez policzonej szansy.
                    # Bez tego podziału „400 odrzuceń" nie mówi, który próg ruszyć.
                    if len(szczeble) == 1:
                        sufit = MAX_LINIA_RYNKU.get(
                            r.get("rynek_kod"), MAX_LINIA_DOMYSLNA
                        )
                        lokalne[
                            "jednoszczeblowa_start_na_suficie"
                            if float(s.get("linia", 0)) >= sufit
                            else "jednoszczeblowa_brak_kolejnej_linii"
                        ] += 1
                    elif nast is None:
                        pass   # ostatni szczebel dłuższej drabinki — to norma
                    elif p_nast is None:
                        lokalne["drugi_szczebel_bez_szansy"] += 1
                    else:
                        lokalne["slaby_drugi_szczebel"] += 1
                    continue
            p_final = s.get("p_final")
            if p_final is None:
                # szczebel pomiarowy jest już policzony jako `slabe_pokrycie` —
                # drugi powód dla tej samej linii przekłamałby diagnostykę
                if not pomiarowy:
                    lokalne["brak_korekty"] += 1
                elif powody_pomiaru is not None:
                    powody_pomiaru["brak_korekty"] += 1
                continue  # bez korekty kontekstowej nie oceniamy karty
            p_mod = s.get("p_model")
            if p_mod is not None and p_mod < p_final:
                p_final = round((p_final + float(p_mod)) / 2.0, 3)
                # szczebla pomiarowego NIE dotykamy: nie wchodzi na kartę,
                # więc nie ma prawa zmieniać tego, co user widzi
                if not pomiarowy:
                    s["p_final"] = p_final
                    s["strzyzenie_modelu"] = True
            edge = p_final - 1.0 / s["kurs"]
            # DWA POWODY, DLA KTÓRYCH LINIA MOŻE WEJŚĆ NA KARTĘ (patrz
            # PROG_POKRYCIA_SERII): przewaga nad kursem ALBO mocna seria przy
            # grywalnej cenie. Kolejność ma znaczenie — gdy linia ma przewagę,
            # karta stoi na przewadze; seria jest wtedy tylko dodatkiem.
            seria = (
                not pomiarowy
                and edge >= MIN_EDGE_SERII
                and (
                    (pokrycie >= PROG_POKRYCIA_SERII
                     and s["kurs"] >= MIN_KURS_SERII)
                    or (pokrycie >= PROG_POKRYCIA_SERII_DROGIEJ
                        and s["kurs"] >= MIN_KURS_SERII_DROGIEJ)
                )
            )
            # ...albo TRZECIA ścieżka: dwaj bukmacherzy wyceniają to samo
            # zdarzenie wyraźnie inaczej (patrz MIN_ROZJAZD_WEJSCIA). Przewagą
            # jest wtedy sama różnica cen, ale zdarzenie musi realnie wchodzić —
            # stąd ostrzejszy próg pokrycia niż przy zwykłej karcie.
            _roz = s.get("rozjazd") or {}
            hybryda = (
                not pomiarowy
                and edge >= MIN_EDGE_SERII
                and pokrycie >= PROG_POKRYCIA_HYBRYDY
                and float(_roz.get("roznica_pp") or 0.0) >= MIN_ROZJAZD_WEJSCIA
                # model uczony nie może przeczyć (patrz wartosc_rozjazdu)
                and wartosc_rozjazdu(s) > 0.0
            )
            # ⚑ PRZEWAGA NIE JEST JUŻ BRAMĄ DLA KARTY (patrz BRAMA_PRZEWAGI).
            # Dla SZCZEBLA POMIAROWEGO zostaje — on nie trafia na stronę, tylko
            # do pomiaru progu pokrycia, a tam „poniżej ceny fair" to sensowna
            # granica tego, co w ogóle warto mierzyć.
            _slaba_przewaga = edge < (
                MIN_EDGE_POMIARU if pomiarowy else MIN_EDGE_KARTY
            ) and not seria and not hybryda
            if _slaba_przewaga and not pomiarowy and statystyki is not None:
                # POMIAR ZOSTAJE, CHOĆ BRAMY JUŻ NIE MA. Te same kubełki co
                # wcześniej, tylko teraz opisują karty WPUSZCZONE bez przewagi
                # — czyli dokładnie ten materiał, na którym za kilka tygodni
                # sprawdzimy, czy zdjęcie bramy było słuszne.
                pas_p = ("mocne 7+/10" if pokrycie >= 0.7 else
                         "srednie 6/10" if pokrycie >= 0.6 else
                         "slabe 5/10")
                pas_k = ("kurs 2,0+" if s["kurs"] >= 2.0 else
                         "kurs 1,7-2,0" if s["kurs"] >= 1.7 else
                         "kurs do 1,7")
                statystyki[f"{pas_p} / {pas_k}"] += 1
            _brama = BRAMA_PRZEWAGI if not pomiarowy else True
            if _brama and _slaba_przewaga:
                if not pomiarowy:
                    lokalne["brak_przewagi"] += 1
                elif powody_pomiaru is not None:
                    powody_pomiaru["ponizej_ceny_fair"] += 1
                continue
            # ...ale przewaga ZA DUŻA to nie okazja, tylko sygnał, że to my się
            # mylimy (patrz MAX_ROZJAZD_KARTY). Cena rynku po zdjęciu marży,
            # tak jak w modelu — porównujemy jabłka z jabłkami.
            cena = betting.implied_prob_one_sided(s["kurs"])
            _iloraz = p_final / cena if cena > 0 else 0.0
            _limit_rozjazdu = MAX_ROZJAZD_KARTY
            if not pomiarowy and _iloraz > MAX_ROZJAZD_KARTY:
                # bardzo mocna linia ma własny limit (nota przy PROG_SILY_ROZJAZDU)
                _sl_r = sila_linii(
                    p, s.get("pokrycie5"), w.get("krotkie_wystepy5"), udzial,
                    w.get("xi") is True,
                    float((((r.get("kontekst") or {}).get("rywal") or {})
                           .get("mnoznik")) or 1.0))
                if (_sl_r and _sl_r.get("powod") is None
                        and _sl_r["sila"] >= PROG_SILY_ROZJAZDU):
                    _limit_rozjazdu = MAX_ROZJAZD_KARTY_MOCNEJ
            if cena > 0 and _iloraz > _limit_rozjazdu:
                if not pomiarowy:
                    lokalne["rozjazd_z_rynkiem"] += 1
                elif powody_pomiaru is not None:
                    powody_pomiaru["rozjazd_z_rynkiem"] += 1
                continue
            trafiony = {
                "rynek_kod": r["rynek_kod"], "rynek": r.get("rynek"),
                "linia": s["linia"], "kurs": s["kurs"],
                # u kogo ta cena jest — nagłówek karty mówi „u Superbetu",
                # więc gdy cena przyszła skądinąd, musi to wiedzieć
                **({"bukmacher": s["bukmacher"]} if s.get("bukmacher") else {}),
                "traf": p["traf"], "z": p["z"],
                "edge": round(edge, 3),
                # przepuszczona ponad MAX_ROZJAZD_KARTY jako bardzo mocna
                # linia — do księgi, żeby limit dało się przemierzyć
                **({"rozjazd_iloraz": round(_iloraz, 2)}
                   if _iloraz > MAX_ROZJAZD_KARTY else {}),
                "p_final": p_final,
                "p_bazowe": s.get("p_bazowe"),
                "korekta": s.get("korekta"),
                # druga liczba z modelu uczonego dla TEGO szczebla — biała
                # lista pól karty, bez tego stempel ginie po drodze
                **({"p_uczony": s["p_uczony"]} if s.get("p_uczony") else {}),
                # NA CZYM STOI TA LINIA — CZTERY różne dowody, cztery nazwy.
                # Kolejność od najmocniejszego: własna przewaga, mocna seria,
                # różnica między cennikami, a na końcu samo pokrycie.
                #
                # ⚑ CZWARTA NAZWA DOSZŁA 2026-08-08 I JEST OBOWIĄZKOWA. Dopóki
                # przewaga była bramą, karta bez przewagi i bez serii mogła
                # wejść WYŁĄCZNIE rozjazdem cen, więc „roznica_kursow" jako
                # ostatnia gałąź była prawdą. Po zdjęciu bramy (BRAMA_PRZEWAGI)
                # wchodzą też karty stojące na samym pokryciu — i dostawały tę
                # samą etykietę, czyli karta tłumaczyła się rozjazdem, którego
                # NIE MIAŁA. To jest dokładnie ta klasa błędu, której pilnujemy
                # w całym produkcie: nie wolno pokazać dowodu, który nie istnieje.
                "powod_wejscia": (
                    "przewaga" if edge >= MIN_EDGE_KARTY
                    else "seria" if seria
                    else "roznica_kursow" if hybryda
                    else "pokrycie"
                ),
                # DRUGI SZCZEBEL — cel polowania, nie ozdoba. Front ma go z czego
                # nazwać po imieniu, a rozliczenia — z czego zmierzyć osobno.
                # Szczebel pomiarowy bywa bez następnika (nie przechodzi przez
                # bramę pary), więc pola zostają puste zamiast wywalać cykl.
                "drugi_linia": (nast or {}).get("linia"),
                "drugi_kurs": (nast or {}).get("kurs"),
                "drugi_p": round(p_nast, 3) if p_nast is not None else None,
                # „wchodził w 5 z 8 meczów" — argument, którym typer uzasadnia
                # drugi szczebel; karta ma go pokazać zamiast samego procentu
                "drugi_traf": pok_nast.get("traf"),
                "drugi_z": pok_nast.get("z"),
                # SKŁADNIKI SZANSY DRUGIEGO SZCZEBLA, PRZED korektą strumienia
                # (2026-08-13). Korekta jest zmierzona na szczeblach HERO,
                # a nakładana na każdy szczebel drabinki — patrz
                # `_z_korekta_strumienia` w budowie drabinki. Bez tych dwóch
                # liczb w księdze pytanie „czy drugi szczebel wolno ścinać tą
                # samą deltą" zostaje nierozstrzygalne wstecz: rozliczenie zna
                # tylko liczbę PO ścięciu. Z nimi da się po kilkudziesięciu
                # rozliczeniach porównać obie deklaracje z tą samą prawdą.
                "drugi_p_bazowe": (nast or {}).get("p_bazowe"),
                "drugi_korekta": (nast or {}).get("korekta"),
                # DRUGA LICZBA z modelu uczonego dla OBU szczebli (2026-08-17).
                # Hero niesie ją pod `p_uczony` (kopiowane ze szczebla niżej),
                # a następnik pod `drugi_p_uczony` — bez tego drugi szczebel
                # byłby jedynym miejscem produktu bez porównania rachunków,
                # a to on jest „celem polowania" na karcie.
                "drugi_p_uczony": (nast or {}).get("p_uczony"),
            }
            # OCENA KARTY LICZY SIĘ Z PARY SZCZEBLI, nie z jednej linii
            # (2026-08-08). Dotąd wygrywała karta z najlepszą pojedynczą linią,
            # więc na górę listy szła ta, która ma świetny pierwszy szczebel
            # i nic dalej — dokładne przeciwieństwo tego, po co ktoś otwiera
            # Drabinki. Średnia z dwóch przewag premiuje kartę, w której OBA
            # szczeble są warte zagrania.
            # Szczebel pomiarowy pary nie ma (brama go nie dotyczy), więc dla
            # niego zostaje sama przewaga — i tak nie rywalizuje o nagłówek.
            if nast is not None and p_nast is not None:
                edge_nast = p_nast - 1.0 / nast["kurs"]
                ocena = (edge + edge_nast) / 2.0
            else:
                ocena = edge
            # premia za cenę startu w paśmie, w którym drabinki realnie
            # zarabiają (patrz OKNO_CENY_PREF_*) — kolejność, nie brama
            if OKNO_CENY_PREF_OD <= s["kurs"] <= OKNO_CENY_PREF_DO:
                ocena += BONUS_OKNA_CENY
            # różnica kursów między bukmacherami — lepszy z pary szczebli
            _w_roz = max(wartosc_rozjazdu(s), wartosc_rozjazdu(nast))
            if _w_roz > PROG_WARTOSCI_ROZJAZDU:
                ocena += WAGA_WARTOSCI_ROZJAZDU * (_w_roz - PROG_WARTOSCI_ROZJAZDU)
            trafiony["wartosc_rozjazdu"] = round(_w_roz, 3)
            # SIŁA LINII zamiast twardego sita (nota przy WAGA_POKRYCIA_SILY):
            # w obrębie karty wygrywa linia z najwyższą WARTOŚCIĄ PAKIETU
            # (siła × cena + realność następnika); linia poniżej progu siły
            # nie jest hero, a karta bez takiej linii odpada z nazwanym
            # powodem — rentgen mówi, co realnie tnie podaż.
            _rywal = float((((r.get("kontekst") or {}).get("rywal") or {})
                            .get("mnoznik")) or 1.0)
            _krotkie = w.get("krotkie_wystepy5")
            _xi = w.get("xi") is True
            _sl = sila_linii(p, s.get("pokrycie5"), _krotkie, udzial, _xi, _rywal)
            _sl2 = (sila_linii(pok_nast, (nast or {}).get("pokrycie5"), _krotkie,
                               udzial, _xi, _rywal)
                    if nast is not None and pok_nast.get("z") else None)
            sito_powod = "pomiarowy" if pomiarowy else (_sl or {}).get("powod")
            sito = sito_powod is None
            _f5 = s.get("pokrycie5") or {}
            trafiony["sito"] = sito
            trafiony["sito_wersja"] = SITO_WERSJA
            # forma obu szczebli — do księgi (build_wc_fast `_charakter_drabinki`)
            trafiony["traf5"] = _f5.get("traf")
            trafiony["z5"] = _f5.get("z")
            _f5_nast = (nast or {}).get("pokrycie5") or {}
            trafiony["drugi_traf5"] = _f5_nast.get("traf")
            trafiony["drugi_z5"] = _f5_nast.get("z")
            # SKŁADNIKI PAKIETU do księgi — bez nich progów nie da się
            # przeliczyć z rozliczeń ([[ciche-odrzucenia-zasada]])
            trafiony["sila"] = (_sl or {}).get("sila")
            trafiony["sila_skladniki"] = (
                {"pokrycie": _sl["pokrycie"], "forma": _sl["forma"],
                 "kary": _sl["kary"], "premia": _sl["premia"]} if _sl else None)
            trafiony["drugi_sila"] = (_sl2 or {}).get("sila")
            trafiony["p_sila"] = szansa_z_sily((_sl or {}).get("sila"), p_final)
            trafiony["drugi_p_sila"] = szansa_z_sily((_sl2 or {}).get("sila"), p_nast)
            _wart = (wartosc_pakietu(trafiony["p_sila"], s["kurs"], trafiony["drugi_p_sila"])
                     if _sl and trafiony["p_sila"] is not None else None)
            trafiony["wartosc_pakietu"] = _wart
            trafiony["ocena_modelu"] = round(ocena, 3)
            if sito:
                # KTÓRY WYJĄTEK WPUŚCIŁ — stempel do księgi; bez niego
                # „wyjątek rywala" i „XI ratuje minuty" nie dadzą się zmierzyć
                trafiony["sito_wyjatek"] = ",".join(_sl["wyjatki"]) or None
            elif not pomiarowy:
                lokalne[sito_powod] += 1
            # CENA I WETO (nota przy MIN_KURS_HERO) — tylko dla linii mocnych
            hero_ok = sito
            if sito:
                _f5n = (nast or {}).get("pokrycie5") or {}
                _nast_realny = (
                    nast is not None and pok_nast.get("z")
                    and pok_nast["traf"] / pok_nast["z"] >= MIN_POKRYCIE_NASTEPNIKA_TANIEGO
                    and (_f5n.get("traf") or 0) >= MIN_FORMA_NASTEPNIKA_TANIEGO)
                if s["kurs"] < MIN_KURS_HERO and not _nast_realny:
                    hero_ok = False
                    lokalne["sito_tania_bez_realnego_drugiego"] += 1
                elif p_final is not None and p_final < 1.0 / s["kurs"] - WETO_MODELU_PP:
                    hero_ok = False
                    lokalne["sito_weto_modelu"] += 1
                else:
                    trafiony["powod_szczebla"] = (
                        "perla" if s["kurs"] >= PROG_PERLY
                        else "najwyzsza_mocna" if s["kurs"] >= MIN_KURS_HERO
                        else "tania_z_drugim")
            trafiony["hero_ok"] = hero_ok
            klucz = (1 if hero_ok else 0,
                     float(s["kurs"]) if hero_ok else 0.0,
                     _wart if (hero_ok and _wart is not None) else 0.0, ocena)
            if pomiarowy:
                if ocena > pomiar_score:
                    pomiar_score, pomiar_s = ocena, trafiony
            elif bez_karty:
                # tylko linia, która PRZESZŁA sito — mierzymy dokładnie to,
                # co poszłoby na kartę po zdjęciu banu, nic słabszego
                if hero_ok and ocena > pomiar_rynku_score:
                    pomiar_rynku_score = ocena
                    pomiar_rynku_s = {**trafiony,
                                      "powod_pomiaru": POWOD_POMIARU_RYNKU}
            elif best_s is None or klucz > best_klucz:
                best_klucz, best_s = klucz, trafiony
                # RANKING KART po wartości pakietu (właściciel 17.09: model
                # nie rządzi kolejnością); klasa karty dalej z `edge` hero
                best_score = (trafiony["wartosc_pakietu"]
                              if hero_ok and trafiony.get("wartosc_pakietu") is not None
                              else ocena)
    if pomiar_out is not None and pomiar_s is not None:
        pomiar_out.append(pomiar_s)
    if pomiar_out is not None and pomiar_rynku_s is not None:
        pomiar_out.append(pomiar_rynku_s)
    if best_s is not None and not best_s.get("hero_ok"):
        # KARTA BEZ LINII SITOWEJ NIE POWSTAJE (2026-09-17). Powód = najczęstsza
        # brama sita wśród jej linii — licznik w rentgenie, nie cisza
        # ([[ciche-odrzucenia-zasada]]).
        if powody is not None:
            _sitowe = [(k, v) for k, v in lokalne.items()
                       if k.startswith("sito_")]
            powody[max(_sitowe, key=lambda kv: kv[1])[0]
                   if _sitowe else "poza_sitem"] += 1
        return 0.0, None
    if powody is not None and best_s is None:
        # najczęstszy powód odpadnięcia tej karty — bez tego nie wiadomo,
        # czy pusta lista to słaby dzień, czy zbyt ostry próg
        powody[
            lokalne.most_common(1)[0][0] if lokalne else "brak_drabinki"
        ] += 1
    return (best_score if best_s is not None else 0.0), best_s


def _klasa_karty(edge: float, miejsce: int = 1, ile: int = 1) -> str:
    """Klasa jakości karty: próg bezwzględny ORAZ miejsce w stawce dnia.

    Sam próg bezwzględny nie wystarcza w obie strony: w dobry dzień „top"
    dostawałoby 25 kart naraz (etykieta przestaje cokolwiek znaczyć), a w słaby
    — żadna, mimo że któraś jest najlepsza z dostępnych. Dlatego „top" wymaga
    przewagi >= PROG_KLASY[0] I bycia w czubie stawki (max z 3 kart i górnego
    kwintyla). Progi bezwzględne są ZAŁOŻENIEM do skalibrowania z rozliczeń
    strumienia drabinek — patrz rozliczanie.skutecznosc_strumieni.
    """
    prog_top, nazwa_top = PROG_KLASY[0]
    if edge >= prog_top and miejsce <= max(3, round(0.2 * max(ile, 1))):
        return nazwa_top
    for prog, nazwa in PROG_KLASY[1:]:
        if edge >= prog:
            return nazwa
    return "solidny"


def _sezony_wpisu(player_sezon: dict | None, pid: int | None) -> list[dict]:
    """Sekcja `sezony` wpisu z cache Supabase `player_sezon` (worker domowy).

    Średnie CAŁYCH sezonów (bieżący + poprzednie) per rynek — /mecz i /90.
    Pusta lista, gdy worker jeszcze nie pobrał gracza."""
    if not player_sezon or not pid:
        return []
    rec = player_sezon.get(str(pid)) or player_sezon.get(int(pid)) or {}
    sez = rec.get("sezony") or []
    # ⚑ RYNEK WYCOFANY ZNIKA TAKŻE Z SEZONÓW (decyzja właściciela 18.08:
    # „zdejmij odbiory całkowicie"). Sekcja `sezony` to średnie opisowe,
    # a nie zakład — ale karta pokazuje je pod tą samą etykietą co rynki
    # („odbiory 0,94 na 90 min"), więc zostawienie ich znaczyłoby, że rynek
    # wycofany dalej jest na stronie. Patrz `betting.RYNKI_WYCOFANE`.
    return [
        {**s,
         **{pole: {k: v for k, v in (s.get(pole) or {}).items()
                   if not betting.rynek_wycofany(k)}
            for pole in ("na90", "na_mecz") if isinstance(s.get(pole), dict)}}
        for s in sez[:MAX_SEZONOW_WPISU]
    ]


# Do ilu procent różnicy uznajemy, że dwa cenniki MÓWIĄ TO SAMO. Poniżej tego
# druga księga jest potwierdzeniem naszej wyceny.
PROG_ZGODNEGO_RYNKU_PCT = 8.0

# ...a OD ILU nazywamy to okazją i malujemy na bursztynowo (2026-08-04).
#
# MIERZONE W PUNKTACH SZANSY, NIE W PROCENTACH KURSU — i to jest sedno.
# Procent znaczy co innego przy różnych cenach, więc jeden próg procentowy
# musiałby być jednocześnie za ostry i za luźny:
#
#     kursy         procent   punkty szansy
#     4,00 / 5,00      25%       5,0 pp     <- prawie sama marża
#     1,20 / 1,50      25%      16,7 pp     <- realna niezgoda
#
# Ten sam procent, dwa zupełnie różne zdarzenia. Punkty szansy mierzą w obu
# przypadkach to samo: o ile obie księgi rozjeżdżają się co do tego, jak
# prawdopodobne jest zdarzenie.
#
# 12 punktów bierze się z dwóch niezależnych stron i dlatego mu ufam:
#   * układ „pewniak taniej" (1,45 wobec 1,75) to 11,8 pp na swojej granicy —
#     dwie bramy mówiące o tym samym nie mogą stać w dwóch różnych miejscach,
#   * przykłady usera: odrzucone 1,59/1,82 daje 7,9 pp, a akceptowane
#     1,70/2,30 i 1,70/2,50 dają 15,3 i 18,8 pp. Próg trafia w tę szczelinę.
#
# Poniżej progu druga cena NIE ZNIKA — dalej stoi przy szczeblu jako „BC 1,82".
# Przestaje tylko udawać okazję: karta jest wtedy zwykłą drabinką.
PROG_OKAZJI_PP = 12.0


def podsumuj_rozjazdy_karty(w: dict) -> bool:
    """Wyciągnij na wierzch karty rozjazd przy szczeblu `hero` i układ
    „pewniak taniej". Zwraca True, gdy taki układ znaleziono.

    WYDZIELONE Z `_dopnij_betclic` (2026-08-08), bo od tej pory druga cena
    dopinana jest DWA RAZY w różnych momentach: przed selekcją (żeby rozjazd
    mógł wpuścić kartę — patrz `MIN_ROZJAZD_WEJSCIA`) i po niej (żeby
    podsumowanie liczyło się względem ostatecznego `hero`). Przed selekcją
    `hero` jeszcze nie istnieje, więc podsumowanie musi być osobnym krokiem.
    """
    hero = w.get("hero") or {}
    wszystkie = [s for r in w.get("rynki") or []
                 for s in r.get("drabinka") or [] if s.get("rozjazd")]
    for r in w.get("rynki") or []:
        if r.get("rynek_kod") != hero.get("rynek_kod"):
            continue
        for s in r.get("drabinka") or []:
            if (s.get("rozjazd")
                    and float(s["linia"]) == float(hero.get("linia", -1))):
                w["rozjazd_hero"] = s["rozjazd"]
    # UKŁAD „PEWNIAK TANIEJ": jeden bukmacher mówi „to niemal pewne"
    # (kurs <= 1,45), drugi płaci za to 1,75+. To jest ten rodzaj rozjazdu,
    # na którym stoją wpisy typerów — wyciągamy go na wierzch karty, żeby front
    # mógł go wyróżnić, a nie topić w liście szczebli.
    pewniaki = [s for s in wszystkie
                if s["rozjazd"].get("typ") == "pewniak_taniej"]
    if not pewniaki:
        return False
    najlepszy = max(pewniaki, key=lambda s: s["rozjazd"]["przewaga_pct"])
    w["rozjazd_pewniak"] = {"linia": najlepszy["linia"], **najlepszy["rozjazd"]}
    return True


def _klucz_zawodnika(nazwa: str) -> str:
    """Klucz tożsamości zawodnika do scalania dubli.

    NIE `superbet.norm_name` — tamten wycina tokeny krótsze niż dwa znaki,
    więc gubi cyfry i skróty; dwie różne osoby potrafią zejść się do jednego
    klucza (wyłapane testem: „Gracz 1" i „Gracz 7" dawały ten sam klucz).
    Tu zostawiamy liczby, a kolejność słów dalej nie ma znaczenia, żeby
    „Semedo, Lisandro" i „Lisandro Semedo" były tą samą osobą.
    """
    s = unicodedata.normalize("NFKD", str(nazwa or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    tokeny = [t for t in re.split(r"[^a-z0-9]+", s) if len(t) > 1 or t.isdigit()]
    return " ".join(sorted(tokeny))


def _profil_gry(w: dict) -> str | None:
    """Jak się tę kartę gra: „pewna", „value" albo nic — patrz stałe wyżej.

    Bierzemy szczebel `hero` (ten, który zdecydował o wyborze karty) i szczebel
    NASTĘPNY w tym samym rynku. Karta bez realnego drugiego szczebla nie dostaje
    etykiety: cała rzecz w tym, żeby oba dały się zagrać.
    """
    hero = w.get("hero") or {}
    mk, linia = hero.get("rynek_kod"), hero.get("linia")
    if mk is None or linia is None:
        return None
    drabinka = next((r.get("drabinka") or [] for r in (w.get("rynki") or [])
                     if r.get("rynek_kod") == mk), [])
    idx = next((i for i, s in enumerate(drabinka)
                if float(s.get("linia", -1)) == float(linia)), None)
    if idx is None:
        return None
    p_hero = drabinka[idx].get("p_final")
    kurs_hero = drabinka[idx].get("kurs")
    p_drugi = (drabinka[idx + 1].get("p_final")
               if idx + 1 < len(drabinka) else None)
    if p_hero is None or kurs_hero is None or p_drugi is None:
        return None
    if p_hero >= PEWNA_MIN_P_HERO and p_drugi >= PEWNA_MIN_P_DRUGI:
        return "dwa_szczeble"
    if (kurs_hero >= VALUE_MIN_KURS_HERO and p_hero >= VALUE_MIN_P_HERO
            and p_drugi >= VALUE_MIN_P_DRUGI):
        return "wyzszy_kurs"
    return None


GODZINA_DOMKNIECIA_DOBY = 6


def dzien_karty(ts) -> str:
    """Doba produktowa karty („YYYY-MM-DD", 6:00 → 6:00 czasu polskiego) —
    ta sama definicja co `build_wc_fast.dzien_listy` i `kluczDnia` na froncie
    (test pilnuje zgodności). Mecz o 2:00 należy do dnia poprzedniego."""
    import datetime as _dt
    if not ts:
        return ""
    try:
        from zoneinfo import ZoneInfo
        d = _dt.datetime.fromtimestamp(int(ts), _dt.timezone.utc).astimezone(
            ZoneInfo("Europe/Warsaw"))
    except Exception:                                          # pragma: no cover
        d = _dt.datetime.fromtimestamp(int(ts))
    if d.hour < GODZINA_DOMKNIECIA_DOBY:
        d -= _dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def sila_linii_z_trendu(tr, linia: float, xi: bool = False) -> dict | None:
    """Siła linii policzona WPROST z historii zawodnika — ta sama miara co na
    szczeblach drabinki (okno `_grane`[:OSTATNIE_N], forma z 5 ostatnich,
    krótkie występy z surowych minut), dla listy dnia (2026-09-18).

    Bez udziału startów i rywala: lista ma własne bramy składu i kontekstu.
    None = za krótka próba (mniej niż MIN_PROBA_SCORE rozegranych).
    """
    if tr is None:
        return None
    okno = _grane(tr)[:OSTATNIE_N]
    if len(okno) < MIN_PROBA_SCORE:
        return None
    lin = float(linia)
    okno5 = okno[:OKNO_FORMY_SITA]
    return sila_linii(
        {"traf": sum(1 for c, _, _ in okno if c > lin), "z": len(okno)},
        {"traf": sum(1 for c, _, _ in okno5 if c > lin), "z": len(okno5)},
        krotkie_wystepy(tr), None, bool(xi))


def prog_nastepnika(kurs_poprzednika) -> float:
    """Minimalna szansa następnika — niższa za perełką (nota przy PROG_PERLY)."""
    try:
        return (MIN_P_NASTEPNIKA_PERLY if float(kurs_poprzednika or 0) >= PROG_PERLY
                else MIN_P_DRUGIEGO_SZCZEBLA)
    except (TypeError, ValueError):
        return MIN_P_DRUGIEGO_SZCZEBLA


def karta_ma_realny_drugi_szczebel(w: dict) -> bool | None:
    """Czy `hero` GOTOWEJ karty ma następnik, którego wolno polować.

    Ta sama reguła co przy wyborze hero (patrz MIN_POKRYCIE_DRUGIEGO), tylko
    zadana kartcie już zbudowanej. PO CO OSOBNO: karta zapisana w rejestrze
    publikacji wraca na listę w kolejnych cyklach z zamrożoną treścią, więc
    reguły wprowadzone PO jej publikacji nigdy jej nie dotykały. Zmierzone
    2026-08-08, dzień po wdrożeniu wymogu drugiego szczebla: wszystkie 23
    karty na stronie pochodziły z rejestru, a 10 z nich miało jeden szczebel —
    czyli nowa reguła nie zmieniła na stronie niczego ([[wznowione-omijaly-bramy]]
    dla typów, tu ten sam mechanizm dla kart).

    Trzy odpowiedzi, nie dwie. `None` znaczy „nie ma czego oceniać" (karta bez
    zapisanej drabinki rynku hero) i NIE jest odmową: brak pola nie dowodzi
    braku szczebla, a zdejmowanie karty na tej podstawie byłoby cichym
    odrzuceniem z fałszywej przesłanki ([[ciche-odrzucenia-zasada]]).
    """
    hero = w.get("hero") or {}
    mk, linia = hero.get("rynek_kod"), hero.get("linia")
    if mk is None or linia is None:
        return None
    drabinka = next((r.get("drabinka") or [] for r in (w.get("rynki") or [])
                     if r.get("rynek_kod") == mk), [])
    idx = next((i for i, s in enumerate(drabinka)
                if float(s.get("linia", -1)) == float(linia)), None)
    if idx is None:
        return None
    nast = drabinka[idx + 1] if idx + 1 < len(drabinka) else None
    if nast is None:
        return False          # hero jest ostatnim szczeblem — nie ma co polować
    pok = nast.get("pokrycie") or {}
    if pok.get("z") and pok["traf"] / pok["z"] < MIN_POKRYCIE_DRUGIEGO:
        return False
    p_nast = _p_po_strzyzeniu(nast)
    return p_nast is not None and p_nast >= prog_nastepnika(hero.get("kurs"))


def sila_linii(
    pokrycie: dict | None, forma5: dict | None, krotkie: int | None,
    udzial: float | None, xi: bool, rywal: float = 1.0,
) -> dict | None:
    """Siła jednej linii drabinki (nota przy WAGA_POKRYCIA_SILY).

    Zwraca {sila, pokrycie, forma, kary, premia, powod, wyjatki}; `powod`
    = None, gdy linia może być hero; inaczej nazwa bramy do rentgenu
    (pierwsza kara, której zdjęcie wystarczyłoby, żeby przejść). `wyjatki`
    = co wpuściło linię mimo kar („xi", „rywal") — stempel do księgi.
    None = brak pokrycia (nie ma z czego liczyć).
    """
    if not pokrycie or not pokrycie.get("z"):
        return None
    pok = pokrycie["traf"] / pokrycie["z"]
    forma = (forma5["traf"] / forma5["z"]
             if forma5 and (forma5.get("z") or 0) >= OKNO_FORMY_SITA else None)
    kary: dict[str, float] = {}
    if forma is None:
        kary["brak_formy"] = KARA_BRAK_FORMY
    if not xi:
        if krotkie is None:
            kary["brak_minut"] = KARA_BRAK_MINUT
        elif krotkie >= MIN_KROTKICH_KARY:
            kary["krotkie_wystepy"] = KARA_KROTKICH_WYSTEPOW
        if udzial is not None and udzial < MIN_UDZIAL_SITA:
            kary["udzial"] = KARA_UDZIALU
    premia = (PREMIA_RYWALA if rywal >= MNOZNIK_RYWALA_WYJATKU
              else -PREMIA_RYWALA if rywal <= MNOZNIK_RYWALA_SKAPEGO else 0.0)
    baza = (WAGA_POKRYCIA_SILY * pok
            + WAGA_FORMY_SILY * (forma if forma is not None else pok))
    sila = round(baza - sum(kary.values()) + premia, 3)
    powod = None
    if pok < PROG_POKRYCIA_SILY:
        powod = "sito_pokrycie_ponizej_7_z_10"
    elif sila < PROG_SILY_HERO:
        nazwy = {"krotkie_wystepy": "sito_krotki_wystep_w_ostatnich_5",
                 "brak_minut": "sito_bez_minut_ostatnich_meczow",
                 "udzial": "sito_rzadko_w_pierwszym_skladzie",
                 "brak_formy": "sito_bez_formy_ostatnich_5"}
        powod = next((nazwy[k] for k, v in sorted(kary.items(), key=lambda kv: -kv[1])
                      if sila + v >= PROG_SILY_HERO), "sito_sila_ponizej_progu")
    wyjatki: list[str] = []
    if powod is None:
        if xi and (krotkie is None or krotkie >= MIN_KROTKICH_KARY
                   or (udzial is not None and udzial < MIN_UDZIAL_SITA)):
            wyjatki.append("xi")
        if premia > 0 and sila - premia < PROG_SILY_HERO:
            wyjatki.append("rywal")
    return {"sila": sila, "pokrycie": round(pok, 2),
            "forma": round(forma, 2) if forma is not None else None,
            "kary": kary, "premia": premia, "powod": powod, "wyjatki": wyjatki}


def szansa_z_sily(sila: float | None, p_final: float | None) -> float | None:
    """Szansa szczebla do wartości pakietu: pół z siły linii (historia:
    pokrycie × forma × rotacja), pół z p_final (pokrycie Wilsona po korekcie
    kontekstowej — rywal, sędzia, scenariusz). Sama siła nie widzi rywala,
    samo p_final nie widzi formy i rotacji; obie liczby jadą do księgi."""
    if sila is None:
        return None if p_final is None else float(p_final)
    if p_final is None:
        return round(SKALA_SILY * sila, 3)
    return round(0.5 * SKALA_SILY * sila + 0.5 * float(p_final), 3)


def wartosc_pakietu(p_hero: float, kurs: float, p_nast: float | None) -> float:
    """Wartość pary szczebli (nota przy WAGA_POKRYCIA_SILY): własna przewaga
    po cenie plus realność następnika (szansa, nie przewaga — drugi szczebel
    w księdze przegrywa z ceną w każdym przekroju)."""
    return round(float(p_hero) - 1.0 / float(kurs)
                 + WAGA_NASTEPNIKA * float(p_nast or 0.0), 3)


def karta_przez_sito(w: dict) -> bool | None:
    """Czy hero GOTOWEJ karty przechodzi sito — na zapisanych liczbach karty.

    Ta sama reguła co w `_oceń_karte` (nota przy PROG_POKRYCIA_SITA), zadana
    karcie wznowionej z rejestru publikacji. PO CO OSOBNO: karta wraca
    z zamrożoną treścią i bez tej bramy każda reguła wprowadzona po jej
    publikacji omija cały wznowiony strumień — dokładnie tak sito v1 z 16.09
    nie dosięgło kart z 15.09, a wymóg drugiego szczebla kart z 07.08
    (patrz `karta_ma_realny_drugi_szczebel`).

    Karta sprzed 17.09 nie ma `pokrycie5` ani `krotkie_wystepy5`, ale niesie
    `rynki[].ostatnie` (liczniki 10 ostatnich, od najnowszego) i `minuty`
    — to te same liczby, z których powstało sito, więc liczymy z nich.
    `None` = nie ma z czego ocenić i NIE jest odmową ([[ciche-odrzucenia-zasada]]).
    """
    hero = w.get("hero") or {}
    mk, linia = hero.get("rynek_kod"), hero.get("linia")
    if mk is None or linia is None:
        return None
    r = next((r for r in (w.get("rynki") or []) if r.get("rynek_kod") == mk),
             None)
    if r is None:
        return None
    s = next((s for s in (r.get("drabinka") or [])
              if float(s.get("linia", -1)) == float(linia)), None)
    if s is None:
        return None
    pok = s.get("pokrycie") or {}
    if not pok.get("z"):
        return None
    if pok["z"] < MIN_PROBA_SCORE:
        return False
    f5 = s.get("pokrycie5")
    if not f5 or not f5.get("z"):
        ost = r.get("ostatnie")
        if not ost:
            return None
        o5 = list(ost)[:OKNO_FORMY_SITA]
        f5 = {"traf": sum(1 for c in o5 if float(c) > float(linia)),
              "z": len(o5)}
    if f5["z"] < OKNO_FORMY_SITA:
        return None
    _rywal = float((((r.get("kontekst") or {}).get("rywal") or {})
                    .get("mnoznik")) or 1.0)
    xi = w.get("xi") is True
    krotkie = w.get("krotkie_wystepy5")
    if krotkie is None:
        mins = r.get("minuty")
        if mins:
            krotkie = sum(1 for m in list(mins)[:OKNO_FORMY_SITA]
                          if float(m) < MIN_MINUT_PELNEGO_WYSTEPU)
    if krotkie is None and not xi:
        return None
    sl = sila_linii(pok, f5, krotkie, w.get("udzial_startow"), xi, _rywal)
    if sl is None:
        return None
    return sl["powod"] is None


def _kategoria_karty(w: dict) -> str:
    """Rodzaj karty — po czym front dobiera kolor i etykietę.

    Cztery rodzaje, od najsłabszego dowodu do najmocniejszego:
      * `analiza`        — druga cena niedostępna, karta stoi na naszej analizie
      * `rynek_zgodny`   — obie księgi wyceniają to prawie tak samo
      * `rozjazd`        — druga księga płaci zauważalnie więcej
      * `pewniak_taniej` — jedna mówi „to niemal pewne", druga płaci sensownie
    Kolejność jest istotna: karta dostaje NAJMOCNIEJSZY rodzaj, jaki ma.
    """
    if w.get("rozjazd_pewniak"):
        return "pewniak_taniej"
    rozjazdy = [s["rozjazd"] for r in w.get("rynki") or []
                for s in r.get("drabinka") or [] if s.get("rozjazd")]
    if not rozjazdy:
        return "analiza"
    if max(r.get("roznica_pp") or 0.0 for r in rozjazdy) >= PROG_OKAZJI_PP:
        return "rozjazd"
    return "rynek_zgodny"


# DRUGI CENNIK (Betclic) — ile sekund wolno na to zużyć w jednym przebiegu.
# Dociągamy PO selekcji, tylko dla kart, które przeszły: kart jest do 30,
# meczów kilkanaście, a każde zapytanie do Betclica to kilka sekund.
BUDZET_BETCLIC_S = 150.0


def _dopnij_betclic(
    wpisy: list[dict],
    events_meta: dict[int, dict],
    paczki_bc: dict[int, dict] | None = None,
    podsumuj_karty: bool = True,
    sb_cache: dict[int, dict] | None = None,
) -> None:
    """Dopnij do szczebli drugą cenę (Betclic) i rozjazd wobec Superbetu.

    PO CO: wzorzec z wpisów typerów — gra się tam, gdzie płacą więcej, a niski
    kurs drugiego bukmachera jest dowodem, że zdarzenie jest pewne.

    OD 2026-08-08 TO NIE JEST JUŻ SAM DODATEK: przy `paczki_bc` (oferta pobrana
    raz przez cykl) dopinamy drugą cenę PRZED selekcją, więc różnica kursów może
    wpuścić kartę, której model sam by nie wystawił — patrz `MIN_ROZJAZD_WEJSCIA`
    i „hybryda" w `_oceń_karte`. Bez paczek zachowanie zostaje stare: dociągamy
    po selekcji, tylko dla kart, które przeszły.

    `podsumuj_karty=False` robi wyłącznie krok pierwszy (rozjazdy przy
    szczeblach). Podsumowanie karty liczy się względem `hero`, którego przed
    selekcją jeszcze nie ma.

    Wszystko w bezpiecznej klamrze — Betclic jest źródłem pomocniczym i jego
    awaria (albo zmiana protokołu) nie ma prawa wywalić całego przebiegu.
    Budżet czasu pilnuje, żeby cron nie urósł: co pominięte, ląduje w logu,
    bo cicha obcinka wygląda jak „sprawdzone wszystko".
    """
    if not wpisy:
        return
    start = time.time()
    try:
        mids = sorted({w["mecz_id"] for w in wpisy})
        nasze = []
        for mid in mids:
            meta = events_meta.get(mid) or {}
            if meta.get("home") and meta.get("away"):
                nasze.append({"klucz": mid, "home": meta["home"],
                              "away": meta["away"], "kickoff_ts": meta.get("ts")})
        if not nasze:
            return
        # PACZKI Z ZEWNĄTRZ: cykl pobiera ofertę Betclica raz, na potrzeby
        # silnika typów, i podaje ją tutaj gotową. Dzięki temu drugą cenę da się
        # dopiąć PRZED selekcją kart (rozjazd jako przepustka) bez ani jednego
        # dodatkowego zapytania — dawniej ten sam mecz pobierałyby dwa miejsca.
        if paczki_bc:
            pary = {mid: {"id": mid, "nazwa": (events_meta.get(mid) or {}).get("label", "")}
                    for mid in mids if paczki_bc.get(mid)}
        else:
            pary, _luka = betclic.paruj_mecze(nasze)
        wpisy_mid: dict[int, list[dict]] = defaultdict(list)
        for w in wpisy:
            wpisy_mid[w["mecz_id"]].append(w)

        n_szczebli = n_kart = n_pewniakow = 0
        pominiete = 0
        # KAŻDE ZEJŚCIE Z DROGI MA SIĘ LICZYĆ (2026-08-04). Log mówił tylko
        # „karty z drugą ceną 0/4" i ta jedna liczba znaczyła cztery różne
        # rzeczy naraz: Betclic nie ma oferty / nie ma tego zawodnika / nie ma
        # tego rynku / drabinki się nie zeszły. Prześledzenie tego ręcznie
        # zajęło godzinę — tyle kosztuje cichy `continue`.
        odpadki: Counter = Counter()
        for mid, bc in pary.items():
            if paczki_bc:
                paczka = paczki_bc.get(mid) or {}
            else:
                if time.time() - start > BUDZET_BETCLIC_S:
                    pominiete += 1
                    continue
                try:
                    paczka = betclic.kursy_zawodnikow(int(bc["id"]))
                except (RuntimeError, OSError, ValueError) as e:
                    print(f"Drabinki/Betclic: mecz {bc.get('nazwa')} — {e}")
                    odpadki["blad_pobrania"] += 1
                    continue
            gracze = paczka.get("players") or {}
            if not gracze:
                # mecz sparowany, ale Betclic nie kwotuje ANI JEDNEGO zawodnika
                odpadki["mecz_bez_zawodnikow"] += 1
                continue
            for w in wpisy_mid.get(mid, []):
                rynki_bc = betclic.znajdz_zawodnika(gracze, w.get("podmiot") or "")
                if not rynki_bc:
                    # Betclic kwotuje 26-30 zawodników (podstawowy skład),
                    # a nasze karty coraz częściej stoją na graczach z głębi
                    # kadry — odkrywamy ich z oferty Superbetu, która ma 40-66.
                    # Taka karta NIE MA jak dostać drugiej ceny.
                    odpadki["zawodnika_brak_u_bc"] += 1
                    continue
                trafil = False
                # ⚑ CZYSTY SUPERBET, NIE SCALONA SIATKA (2026-09-15). Siatka
                # kart (`linie_pelne`) niesie już WYŻSZY kurs z obu cenników
                # (`build_wc_fast._scal_oferty_zawodnika`), więc porównanie jej
                # z Betclikiem było porównaniem Betclica z samym sobą, gdy tylko
                # Betclic płacił więcej. Zmierzone na radarze 15.09: 15 z 20
                # porównań to fałszywe „0,0 pp", ani jednego „lepiej w Betclicu",
                # 5 z 8 etykiet „rynek zgodny" nieprawdziwych — czyli value
                # z rozjazdu działało tylko w jedną stronę.
                rynki_sb = None
                if sb_cache is not None:
                    rynki_sb = superbet.znajdz_zawodnika(
                        (sb_cache.get(mid) or {}).get("players") or {},
                        w.get("podmiot") or "") or {}
                for r in w.get("rynki") or []:
                    # nasza drabinka w kształcie porównywalnym z Betclikiem —
                    # rozjazdy liczy JEDNA funkcja (razem z bramą wspólnych
                    # linii), żeby karta i porównywarka nie miały dwóch
                    # różnych definicji tego samego
                    # SPRAWDZAMY NA PEŁNEJ LIŚCIE, POKAZUJEMY NA DRABINCE
                    # — patrz `linie_pelne` w `_rynki_wpisu`. Bez tego karta
                    # jednoszczeblowa nigdy nie zbierze dwóch wspólnych linii,
                    # więc porównanie cen odpada zanim w ogóle spojrzy na ceny.
                    if rynki_sb is not None:
                        nasze_linie = {
                            float(l): {"over": (v or {}).get("over")}
                            for l, v in (rynki_sb.get(r.get("rynek_kod")) or {}).items()
                            if (v or {}).get("over")
                        }
                        if not nasze_linie:
                            odpadki["rynku_brak_u_superbetu"] += 1
                            continue
                    else:
                        nasze_linie = {
                            float(l): {"over": kurs}
                            for l, kurs in (r.get("linie_pelne") or {}).items()
                            if kurs
                        } or {
                            float(s["linia"]): {"over": s.get("kurs")}
                            for s in r.get("drabinka") or [] if s.get("kurs")
                        }
                    bc_linie = rynki_bc.get(r.get("rynek_kod")) or {}
                    if not bc_linie:
                        odpadki["rynku_brak_u_bc"] += 1
                        continue
                    rozjazdy = betclic.porownaj_drabinke(nasze_linie, bc_linie)
                    if not rozjazdy:
                        odpadki["drabinki_nie_zeszly_sie"] += 1
                    for s in r.get("drabinka") or []:
                        r_oc = rozjazdy.get(float(s["linia"]))
                        if not r_oc:
                            continue
                        s["kurs_betclic"] = r_oc["betclic"]
                        s["kurs_superbet"] = r_oc["superbet"]
                        s["rozjazd"] = r_oc
                        n_szczebli += 1
                        trafil = True
                if trafil:
                    n_kart += 1
                    if podsumuj_karty and podsumuj_rozjazdy_karty(w):
                        n_pewniakow += 1
        if podsumuj_karty:
            for w in wpisy:
                w["kategoria"] = _kategoria_karty(w)
                w["profil_gry"] = _profil_gry(w)
        print(f"Drabinki — drugi cennik (Betclic): mecze {len(pary)}/{len(nasze)}, "
              f"karty z drugą ceną {n_kart}/{len(wpisy)}, szczebli {n_szczebli}, "
              f"układów „pewniak taniej” {n_pewniakow}"
              + (f", pominięte mecze (budżet czasu): {pominiete}" if pominiete else ""))
        # GDZIE UCIEKŁA RESZTA — bez tego „0/4" wygląda tak samo przy braku
        # oferty Betclica, jak przy naszym błędzie odczytu
        if odpadki:
            print("Drabinki — druga cena nie doszła: " + ", ".join(
                f"{k}={v}" for k, v in odpadki.most_common()))
        # CO ODRZUCIŁY BRAMY — bez tego obcinka jest cicha i „karty z drugą
        # ceną 1/3" wygląda tak samo, gdy Betclic nie ma oferty, jak wtedy,
        # gdy ma, ale liczy co innego (patrz betclic.ODRZUCONE_ROZJAZDY)
        odrzucone = {k: v for k, v in betclic.ODRZUCONE_ROZJAZDY.items() if v}
        if odrzucone:
            print("Drabinki — porównania cen odrzucone: " + ", ".join(
                f"{k}={v}" for k, v in sorted(
                    odrzucone.items(), key=lambda kv: -kv[1])
            ))
    except Exception as e:  # źródło pomocnicze — nigdy nie wywala przebiegu
        print(f"Drabinki — drugi cennik pominięty ({type(e).__name__}: {e})")
    finally:
        # każda karta MUSI mieć rodzaj, także gdy Betclic w ogóle nie odpowiedział
        for w in wpisy:
            w.setdefault("kategoria", _kategoria_karty(w))
            w.setdefault("profil_gry", _profil_gry(w))


def zbuduj(
    trends: list[statshub.StatshubTrend],
    events_meta: dict[int, dict],
    odds_grid: dict[int, dict[int, dict[str, dict[str, float]]]],
    sb_cache: dict[int, dict],
    model_pokrycie: list[dict],
    players_out: dict[int, dict],
    nazwy_pl: dict[str, str],
    teraz: int,
    player_sezon: dict | None = None,
    sedzia_by_mid: dict[int, dict] | None = None,
    koncesje_tab=None,
    poza_skladem: set[tuple[int, int]] | None = None,
    xi_znany: dict[tuple[int, int], bool] | None = None,
    margines_startu_s: int = 0,
    korekta_logit: float = 0.0,
    pomiar_out: list | None = None,
    bc_cache: dict[int, dict] | None = None,
    zrodla_grid: dict[int, dict] | None = None,
    wagi_modelu: dict | None = None,
    kalendarz_druzyn: dict[int, list[int]] | None = None,
    tabela_rywali: dict | None = None,
    # unia występów per zawodnik z cyklu (build_wc_fast), już DOCIĄGNIĘTA
    # z performance dla podejrzanych — bramy składu karty liczą z niej
    wystepy_pelne: dict[int, statshub.StatshubTrend] | None = None,
    # IMIENNY RENTGEN (2026-09-21): {(mecz_id, podmiot_id): {brama, …}} —
    # brama, na której para odpadła, albo „karta"; patrz `radar_imienny`
    imienny_out: dict | None = None,
) -> list[dict]:
    """Złóż wpisy radaru/drabinek ze zbiorów, które cykl i tak ma w pamięci.

    `bc_cache` — oferta Betclica pobrana raz przez cykl (mecz -> paczka
    `kursy_zawodnikow`). Podana tutaj pozwala dopiąć drugą cenę PRZED selekcją,
    więc różnica kursów może wpuścić kartę („hybryda", patrz
    MIN_ROZJAZD_WEJSCIA) — i przy okazji oszczędza zapytania, bo bez niej ten
    sam mecz pobierałyby dwa miejsca w cyklu.

    DRABINKI (przebudowa 2026-07-24, decyzja produktowa): wpis dostaje KAŻDY
    kwotowany przez Superbet gracz z historią statshub — drabina linii z
    kursami + pełna analiza (ostatnie występy, forma okno-vs-baza, kontekst
    rywala, średnie sezonowe z cache workera). Detektory transfer/forma/
    debiutant zostają jako PLAKIETKI i priorytet sortowania, nie bramy.

    KONTEKST MECZU (2026-07-26): każdy szczebel dostaje `p_final` — pokrycie
    Wilsona skorygowane o to, co czeka zawodnika W TYM meczu (koncesje rywala
    na tym konkretnym rynku, sędzia przy faulach, scenariusz meczu z kursów
    1X2, forma, prognoza minut, średnie sezonowe). Selekcja i kolejność kart
    idą po realnej przewadze nad kursem, nie po surowym „trafione 8/10".

    WŁASNE UCZENIE (2026-07-29): `korekta_logit` to delta ze strumienia
    drabinek (rozliczanie.korekta_strumienia) — o ile ich szanse okazały się
    przeszacowane na rozliczeniach. Wchodzi w `p_final`, czyli i w liczbę na
    karcie, i w bramę przewagi: gdy strumień przeszacowuje, przez bramę
    przechodzi mniej kart. `pomiar_out` zbiera szczeble tuż pod progiem
    pokrycia do rozliczenia w tle (patrz NEAR_POKRYCIA).

    Zwraca listę do radar.json — posortowaną: transfery, debiutanci, serie
    formy, reszta drabinek; wewnątrz rodzaju po godzinie meczu. Kickoffem,
    który minął, zajmuje się web (tylkoNadchodzace), nie my."""
    konsensus = liga_konsensus(trends)
    trendy_pm: dict[tuple[int, int], dict[str, statshub.StatshubTrend]] = {}
    for t in trends:
        if t.event_id and t.player_id:
            slot = trendy_pm.setdefault((t.event_id, t.player_id), {})
            prev = slot.get(t.market_code)
            if prev is None or len(t.counts) > len(prev.counts):
                slot[t.market_code] = t
    # KONCESJE RYWALI z historii całego feedu (fallback tam, gdzie statshub
    # nie podaje gotowych agregatów — cała ścieżka `performance`, m.in.
    # Ekstraklasa, oraz rynki spoza piątki rdzeniowej)
    koncesje = kd.zbuduj_koncesje(trendy_pm, teraz)
    # TEMPO MECZU z kursów 1X2/total Superbetu (scenariusz: otwarty mecz,
    # faworyt/underdog) — liczone raz na mecz, nie na kartę
    tempo_by_mid: dict[int, dict | None] = {}

    def _tempo(mid: int) -> dict | None:
        if mid not in tempo_by_mid:
            try:
                tempo_by_mid[mid] = tempo_mod.tempo_from_match_odds(
                    (sb_cache.get(mid) or {}).get("match")
                )
            except Exception:
                tempo_by_mid[mid] = None
        return tempo_by_mid[mid]
    p_model_idx: dict[tuple[str, str, float], float] = {}
    for r in model_pokrycie:
        if r.get("strona") == "powyzej":
            p_model_idx[(r["podmiot"], r["rynek_kod"], float(r["linia"]))] = (
                float(r["p_model"])
            )

    poza_skladem = poza_skladem or set()
    xi_znany = xi_znany or {}

    wpisy: list[dict] = []
    # GDZIE GINIE DRUGI SZCZEBEL — licznik na etapie BUDOWY drabinki, nie
    # selekcji. `_oceń_karte` widzi drabinkę już przyciętą, więc „karta ma jeden
    # szczebel" wygląda tam identycznie niezależnie od tego, czy bukmacher nie
    # kwotował kolejnej linii, czy myśmy ją ucięli progiem. To rozróżnienie
    # decyduje, który próg ruszyć, gdy kart jest za mało.
    diag_drabinki: Counter = Counter()
    # ⚑⚑ RENTGEN LEJKA (2026-08-20). Do dziś radar liczył WYŁĄCZNIE to, gdzie
    # ginie drugi szczebel — czyli sam koniec drogi. Etapy wcześniejsze (mecz →
    # oferta → zawodnik → historia → pokrycie) nie miały ani jednego licznika,
    # więc na pytanie „czemu nie ma karty na tego zawodnika" nie dało się
    # odpowiedzieć inaczej niż zgadywaniem — i wracaliśmy do tematu co kilka
    # dni.
    #
    # Zgłoszenie właściciela 20.08 (Mickels, Sabah FK): konkurencja wystawiła
    # drabinkę na strzały, my nie mieliśmy tego zawodnika NIGDZIE — ani na
    # karcie, ani wśród 15 130 odrzuceń. Bez tych liczników jedyną drogą do
    # przyczyny było czytanie kodu ścieżka po ścieżce.
    #
    # Zasada jest ta sama co przy typach: [[ciche-odrzucenia-zasada]] — licznik
    # przy KAŻDEJ bramie, próg w jednostce decyzji.
    lejek: Counter = Counter()
    lejek["1_meczow_z_oferta"] = len(odds_grid)
    lejek["2_par_zawodnik_rynek"] = sum(len(g) for g in odds_grid.values())

    def _ri(mid: int, pid: int, brama: str, **kw) -> None:
        """Imienny rentgen: werdykt pary + to, co o niej wiemy w tym miejscu."""
        if imienny_out is None:
            return
        info = players_out.get(pid) or {}
        meta_m = events_meta.get(mid) or {}
        radar_imienny.odnotuj(
            imienny_out, mid, pid, brama,
            mecz=meta_m.get("label"), kickoff_ts=meta_m.get("ts"),
            podmiot=kw.pop("podmiot", None) or info.get("nazwa"),
            druzyna=kw.pop("druzyna", None) or info.get("druzyna"),
            **kw,
        )

    for mid, gracze in odds_grid.items():
        meta = events_meta.get(mid)
        if not meta:
            lejek["3_odpadl_mecz_bez_meta"] += 1
            for pid in gracze:
                _ri(mid, pid, "mecz_bez_meta")
            continue
        # ZAPAS NA OBSTAWIENIE: nowa karta nie powstaje tuż przed gwizdkiem.
        # Karta już opublikowana wraca z rejestru (scal_karty_z_publikacjami)
        # i zostaje do końca — chodzi wyłącznie o to, żeby nic NOWEGO nie
        # wskakiwało na listę w ostatniej chwili (zgłoszenie: Club Necaxa).
        if margines_startu_s and (meta.get("ts") or 0) <= teraz + margines_startu_s:
            lejek["4_odpadl_mecz_za_blisko_gwizdka"] += 1
            # werdykt z wcześniejszego cyklu (gdy oferta była do wzięcia)
            # jest już w tabeli — tu dopisujemy tylko tych, których nie było
            for pid in gracze:
                if imienny_out is not None and (mid, pid) not in imienny_out:
                    _ri(mid, pid, "mecz_za_blisko_gwizdka")
            continue
        for pid, drabinki in gracze.items():
            # POZA SKŁADEM: znamy jedenastkę i jego w niej nie ma. Karta na
            # takiego zawodnika to zakład o to, że wejdzie z ławki — a cała
            # analiza pod spodem liczy z minut, których nie zagra.
            if (mid, pid) in poza_skladem:
                lejek["5_odpadl_zawodnik_poza_skladem"] += 1
                _ri(mid, pid, "zawodnik_poza_skladem")
                continue
            trendy_mk = trendy_pm.get((mid, pid))
            if not trendy_mk:
                # ⚑ TU ZGINĄŁ MICKELS. Bukmacher go kwotuje, my nie mamy
                # historii — bo albo statshub jej nie oddał, albo nie
                # zapytaliśmy (mecz poza budżetem `DOCIAG_MAX`).
                lejek["6_odpadl_zawodnik_bez_historii"] += 1
                _ri(mid, pid, "zawodnik_bez_historii",
                    rynki_oferty=sorted(drabinki or {}))
                continue
            tr_ref = max(trendy_mk.values(), key=lambda t: len(t.counts))
            # ŚWIEŻOŚĆ PRÓBY: dotąd pilnowały jej tylko detektory transferu
            # i formy, czyli plakietki. Zwykła drabinka mogła stać na historii
            # sprzed pół roku — dla zawodnika po kontuzji albo poza rotacją
            # „trafił 8/10" opisuje kogoś, kto już tak nie gra.
            grane_ref = _grane(tr_ref)
            if not grane_ref:
                lejek["7_odpadla_historia_niesw" + "ieza"] += 1
                _ri(mid, pid, "historia_nieswieza", podmiot=tr_ref.player_name,
                    druzyna=tr_ref.team_name, wystepow=0)
                continue
            # ŚWIEŻOŚĆ: liczona w MECZACH DRUŻYNY, gdy znamy jej kalendarz
            # (patrz `MAX_OPUSZCZONYCH_MECZOW`). Kalendarzowy próg zostaje
            # tylko dla drużyn spoza magazynu — tam nie mamy czym policzyć
            # lepiej, a zupełny brak bramy wpuściłby historię sprzed lat.
            _opuscil = magazyn_druzyn.opuszczone_mecze(
                kalendarz_druzyn or {}, tr_ref.team_id, grane_ref[0][2]
            )
            if _opuscil is None:
                if teraz - grane_ref[0][2] > MAX_DNI_SWIEZOSC * 86400:
                    lejek["7_odpadla_historia_niesw" + "ieza"] += 1
                    lejek["7a_w_tym_bez_kalendarza_druzyny"] += 1
                    _ri(mid, pid, "historia_nieswieza",
                        podmiot=tr_ref.player_name, druzyna=tr_ref.team_name,
                        dni_od_ostatniego=(teraz - grane_ref[0][2]) // 86400)
                    continue
            elif _opuscil > MAX_OPUSZCZONYCH_MECZOW:
                lejek["7_odpadla_historia_niesw" + "ieza"] += 1
                _ri(mid, pid, "historia_nieswieza",
                    podmiot=tr_ref.player_name, druzyna=tr_ref.team_name,
                    opuszczone_mecze=_opuscil)
                continue
            elif teraz - grane_ref[0][2] > MAX_DNI_SWIEZOSC * 86400:
                # przeszedł WYŁĄCZNIE dzięki nowej mierze — licznik pokaże,
                # ile materiału odzyskała zmiana i czy te karty trafiają
                lejek["7b_odzyskane_nowa_miara_swiezosci"] += 1
            liga_dr, utidy_dr = konsensus.get(
                tr_ref.team_id or -1, (None, set())
            )
            transfer = sygnal_transferu(tr_ref, liga_dr, utidy_dr, teraz)
            forma = None
            forma_mk = None
            if transfer is None:
                for mk, tr in trendy_mk.items():
                    linie = {
                        float(l): k for l, k in (drabinki.get(mk) or {}).items()
                    }
                    if not linie:
                        continue
                    s = sygnal_formy(tr, linie, teraz)
                    if s and (
                        forma is None
                        or (s["trafienia"], s["kurs"])
                        > (forma["trafienia"], forma["kurs"])
                    ):
                        forma, forma_mk = s, mk
            info = players_out.get(pid) or {}
            # średnia minut z ostatnich 6 występów — "gra pełne mecze"
            # vs "wchodzi z ławki" to pierwsze pytanie każdej analizy.
            # Liczona PRZED drabinką, bo jest prognozą ekspozycji w p_final.
            gr_ref = grane_ref[:6]
            minuty_sr6 = (
                round(sum(m for _, m, _ in gr_ref) / len(gr_ref))
                if gr_ref else None
            )
            sez = _sezony_wpisu(player_sezon, pid)
            # dom/wyjazd z meta meczu (tr.is_home bywa puste na ścieżce
            # performance, a meta ma id gospodarza zawsze)
            is_home = (
                bool(tr_ref.team_id == meta.get("hid"))
                if meta.get("hid") and tr_ref.team_id else None
            )
            opp_id = (
                (meta.get("aid") if is_home else meta.get("hid"))
                if is_home is not None else (tr_ref.opponent_id or None)
            )
            _powody_rynkow: dict = {}
            rynki = _rynki_wpisu(
                drabinki, trendy_mk, p_model_idx,
                tr_ref.player_name, nazwy_pl,
                powody_rynkow=_powody_rynkow,
                sedzia=(sedzia_by_mid or {}).get(mid),
                tempo=_tempo(mid),
                is_home=is_home,
                koncesje=koncesje,
                koncesje_nazw=koncesje_tab,
                nazwa_rywala=tr_ref.opponent_name or meta.get(
                    "away" if is_home else "home"
                ),
                nazwa_druzyny=tr_ref.team_name,
                opp_id=opp_id,
                minuty_proj=minuty_sr6,
                sezony=sez,
                teraz=teraz,
                korekta_logit=korekta_logit,
                diag=diag_drabinki,
                zrodla=((zrodla_grid or {}).get(mid) or {}).get(pid),
                wagi_modelu=wagi_modelu,
                tabela_rywali=tabela_rywali,
            )
            if not rynki:
                lejek["8_odpadly_puste_drabinki"] += 1
                _ri(mid, pid, "puste_drabinki", podmiot=tr_ref.player_name,
                    druzyna=tr_ref.team_name,
                    rynki_oferty=sorted(drabinki or {}),
                    rynki=_powody_rynkow or None)
                continue  # same puste drabinki (kursy-szum) = nie ma karty
            # unia występów: trendy tej karty + unia z cyklu (dociągnięta
            # z performance dla podejrzanych — patrz dociagnij_pelne_wystepy)
            _unia = polacz_wystepy(
                list(trendy_mk.values())
                + ([wystepy_pelne[pid]] if wystepy_pelne and wystepy_pelne.get(pid) else [])
            ) or tr_ref
            wpis = {
                "minuty_sr6": minuty_sr6,
                # krótkie występy w ostatnich 5 — brama sita (rotacja), z UNII
                # występów jak udział startów
                "krotkie_wystepy5": krotkie_wystepy(
                    _unia),
                "ostatni_wystep_min": ostatni_wystep_min(_unia),
                # ile z ostatnich meczów zaczynał w pierwszym składzie —
                # brama karty i konkret na karcie („gra od pierwszej minuty
                # w 9 z 10 ostatnich"), zamiast samej średniej minut
                # ⚑ względem MECZÓW DRUŻYNY, gdy znamy jej kalendarz —
                # rezerwowy z trzema pełnymi występami nie jest starterem
                # ⚑ z UNII występów ze wszystkich rynków (2026-09-16) — jeden
                # rynek z feedu zna tylko mecze, które kwotowano
                "udzial_startow": udzial_startow(
                    _unia,
                    kalendarz=kalendarz_druzyn, teraz=teraz),
                "nie_gral_ostatnio": nie_gral_ostatnio(
                    _unia,
                    kalendarz_druzyn, teraz),
                "rodzaj": (
                    "transfer" if transfer else
                    "forma" if forma else "drabinka"
                ),
                "mecz_id": mid, "mecz": meta["label"],
                "kickoff_ts": meta["ts"],
                "podmiot_id": pid,
                "podmiot": tr_ref.player_name,
                "druzyna": tr_ref.team_name,
                "przeciwnik": tr_ref.opponent_name,
                "pozycja": info.get("pozycja") or tr_ref.position or "?",
                # tri-state: True = jest w składzie, False = poza składem,
                # None = składu jeszcze nie ogłoszono. Dawne `info["xi"]`
                # zwracało False w obu ostatnich przypadkach naraz, więc karta
                # nie umiała odróżnić „ławka" od „nie wiemy". `info["xi"]`
                # zostaje jako źródło pozytywnego sygnału (True znaczy tam
                # dokładnie „jest w przewidywanym XI"); jego False odrzucamy,
                # bo nie niesie informacji.
                "xi": (
                    xi_znany.get((mid, pid))
                    if (mid, pid) in xi_znany
                    else (True if info.get("xi") else None)
                ),
                "rynki": rynki,
            }
            if transfer:
                wpis.update(transfer)
                wpis["_liga_druzyny_utid"] = liga_dr
            elif forma:
                wpis["powod"] = "seria"
                wpis["forma_rynek"] = forma_mk
                wpis["forma"] = forma
            if sez:
                wpis["sezony"] = sez
            wpisy.append(wpis)

    # debiutanci: Superbet kwotuje, statshub milczy. Priorytet budżetu
    # wyszukiwań: NAJPIERW mecze BEZ ŻADNYCH trendów (ligi poza feedem
    # propsów UK — Ekstraklasa! — żyją wyłącznie tą ścieżką), potem reszta;
    # wewnątrz po kickoffie. Bez tego budżet przepalał się na ławkach
    # meczów, które i tak mają karty z trendów (bug zmierzony 2026-07-25:
    # Superbet kwotował 41 graczy Lecha, kart nie było).
    budzet = [0]
    # shotmapy historycznych meczów — WSPÓLNE dla graczy tej samej drużyny
    # (ta sama historia), więc koszt ~10 zapytań na drużynę, nie na gracza
    sm_cache_cykl: dict[int, list] = {}
    budzet_shotmap = [MAX_SHOTMAP_CYKL]
    mids_z_trendami = {m for (m, _p) in trendy_pm}
    for mid, meta in sorted(
        events_meta.items(),
        key=lambda kv: (kv[0] in mids_z_trendami, kv[1].get("ts") or 0),
    ):
        if (meta.get("ts") or 0) <= teraz + margines_startu_s:
            continue  # mecz trwa albo startuje za chwilę — szkoda budżetu
        sb = sb_cache.get(mid)
        if not sb or not (meta.get("hid") and meta.get("aid")):
            continue
        znane = sorted({
            t.player_name for (m, _), sl in trendy_pm.items() if m == mid
            for t in sl.values()
        })
        for d in debiutanci_meczu(
            sb, znane, (meta["hid"], meta["aid"]), budzet
        )[:MAX_DEBIUTANTOW_MECZU]:
            profil = d["profil"]
            if (mid, profil.get("id")) in poza_skladem:
                continue  # poza ogłoszonym składem — patrz komentarz wyżej
            druzyna = (
                meta.get("home") if profil.get("team_id") == meta["hid"]
                else meta.get("away")
            )
            przeciwnik = (
                meta.get("away") if profil.get("team_id") == meta["hid"]
                else meta.get("home")
            )
            wiek = None
            if profil.get("birth_ts"):
                wiek = int((teraz - int(profil["birth_ts"])) // (365.25 * 86400))
            sez_deb = _sezony_wpisu(player_sezon, profil.get("id"))
            # UCZCIWA ETYKIETA (fix 2026-07-25): gdy mecz nie ma ŻADNYCH
            # trendów, to nie „debiutant bez historii", tylko CAŁA liga jest
            # poza feedem propsów UK (Ekstraklasa). Nazywanie Luisa Palmy
            # czy Nika Prelca „debiutantem, którego rynek wycenia w ciemno"
            # byłoby po prostu nieprawdą — historia istnieje, my jej tu
            # nie mamy. Średnie sezonowe dociąga worker (Sofascore).
            bez_feedu = mid not in mids_z_trendami
            # HISTORIA SPOZA FEEDU PROPSÓW (odkrycie 2026-07-25):
            # /player/{id}/performance daje 10 ostatnich meczów ze
            # statystykami dla KAŻDEJ ligi — Ekstraklasa dostaje pełną
            # drabinkę z pokryciem linii zamiast gołych kursów.
            trendy_perf: dict[str, statshub.StatshubTrend] = {}
            if profil.get("id"):
                try:
                    trendy_perf = statshub.trendy_z_performance(
                        int(profil["id"]), d["nazwa"], profil.get("team_id"),
                        statshub.fetch_player_performance(int(profil["id"])),
                        sm_cache=sm_cache_cykl, budzet=budzet_shotmap,
                    )
                except Exception:
                    trendy_perf = {}
            # prognoza minut z historii performance (ta sama rola co
            # minuty_sr6 na ścieżce trendów: ekspozycja w p_final)
            gr_deb = (
                _grane(max(trendy_perf.values(), key=lambda t: len(t.counts)))[:6]
                if trendy_perf else []
            )
            minuty_sr6_deb = (
                round(sum(m for _c, m, _t in gr_deb) / len(gr_deb))
                if gr_deb else None
            )
            is_home_deb = (
                bool(profil.get("team_id") == meta["hid"])
                if profil.get("team_id") else None
            )
            opp_id_deb = (
                (meta["aid"] if is_home_deb else meta["hid"])
                if is_home_deb is not None else None
            )
            wpisy.append({
                **({"sezony": sez_deb} if sez_deb else {}),
                # z historią z performance to pełnoprawna drabinka, nie
                # „same kursy" — etykieta idzie za realną zawartością karty
                "rodzaj": (
                    "drabinka" if (bez_feedu and trendy_perf)
                    else "bez_feedu" if bez_feedu else "debiutant"
                ),
                "mecz_id": mid, "mecz": meta["label"],
                "kickoff_ts": meta["ts"],
                "podmiot_id": profil.get("id"),
                "podmiot": d["nazwa"],
                "druzyna": druzyna or "",
                "przeciwnik": przeciwnik or "",
                "pozycja": (profil.get("position") or "?")[:1],
                "xi": xi_znany.get((mid, profil.get("id"))),
                **({"powod": "poza_feedem"} if bez_feedu and not trendy_perf
                   else {"powod": "brak_historii"} if not bez_feedu else {}),
                "minuty_sr6": minuty_sr6_deb,
                "krotkie_wystepy5": (
                    krotkie_wystepy(max(trendy_perf.values(),
                                        key=lambda t: len(t.counts)))
                    if trendy_perf else None
                ),
                "ostatni_wystep_min": (
                    ostatni_wystep_min(max(trendy_perf.values(),
                                           key=lambda t: len(t.counts)))
                    if trendy_perf else None
                ),
                "udzial_startow": (
                    udzial_startow(max(trendy_perf.values(),
                                       key=lambda t: len(t.counts)))
                    if trendy_perf else None
                ),
                "profil": {
                    "wzrost": profil.get("height"),
                    "wiek": wiek,
                    "kraj": profil.get("country"),
                    "noga": profil.get("foot"),
                },
                "rynki": _rynki_wpisu(
                    {
                        mk: {
                            str(l): v["over"]
                            for l, v in linie.items() if v.get("over")
                        }
                        for mk, linie in (
                            (sb.get("players") or {}).get(d["klucz_sb"]) or {}
                        ).items()
                    },
                    trendy_perf, {}, d["nazwa"], nazwy_pl,
                    sedzia=(sedzia_by_mid or {}).get(mid),
                    tempo=_tempo(mid),
                    is_home=is_home_deb,
                    koncesje=koncesje,
                    koncesje_nazw=koncesje_tab,
                    nazwa_rywala=przeciwnik,
                    nazwa_druzyny=druzyna,
                    opp_id=opp_id_deb,
                    minuty_proj=minuty_sr6_deb,
                    sezony=sez_deb,
                    teraz=teraz,
                    korekta_logit=korekta_logit,
                    diag=diag_drabinki,
                    wagi_modelu=wagi_modelu,
                    tabela_rywali=tabela_rywali,
                ),
            })

    # etykiety starych lig (drobny koszt: kilka utid-ów z cache w statshub)
    # + siatka bezpieczeństwa na fazy jednej ligi pod różnymi utid-ami:
    # „Liga MX, Apertura" vs „Liga MX, Clausura" to nie transfer
    przefiltrowane = []
    for w in wpisy:
        liga_dr = w.pop("_liga_druzyny_utid", None)
        utid = w.get("stara_liga_utid")
        if utid:
            nazwa_starej = statshub.fetch_tournament_name(int(utid)) or None
            w["stara_liga"] = nazwa_starej
            if nazwa_starej and liga_dr:
                nazwa_nowej = statshub.fetch_tournament_name(int(liga_dr))
                if nazwa_nowej and _ten_sam_cykl_ligi(
                    nazwa_starej, nazwa_nowej
                ):
                    continue
        przefiltrowane.append(w)
    wpisy = przefiltrowane

    # SORTOWANIE (przebudowa 2026-07-24): po MECZACH chronologicznie,
    # w meczu po jakości (score) — sygnały wyróżnia plakietka na karcie,
    # nie kolejność listy (stary radar sortował rodzajami, co przy wielu
    # kartach rozrzucało jeden mecz po całej liście). Sufit per mecz
    # trzyma eksplozję: każdy kwotowany gracz = kandydat na kartę.
    # TWARDE BRAMY: karta bez ani jednej linii z realną przewagą odpada,
    # niezależnie od rodzaju. Sygnał to plakietka, nie przepustka.
    #
    # DRUGA CENA PRZED SELEKCJĄ (2026-08-08): mając ofertę Betclica pobraną raz
    # przez cykl, dopinamy rozjazdy do WSZYSTKICH kandydatów, zanim cokolwiek
    # ocenimy. Dopiero wtedy różnica kursów może wpuścić kartę, której model sam
    # by nie wystawił. Bez `bc_cache` nic tu nie robimy — dociąganie po selekcji
    # zostaje jak było, żeby nie palić budżetu czasu na setki kandydatów.
    if bc_cache:
        _dopnij_betclic(wpisy, events_meta, paczki_bc=bc_cache,
                        podsumuj_karty=False, sb_cache=sb_cache)
    ocenione = []
    powody_odpadniecia: Counter = Counter()
    pomiar_kandydaci: list[dict] = []
    powody_pomiaru: Counter = Counter()
    statystyki_przewagi: Counter = Counter()
    for w in wpisy:
        pom: list[dict] | None = [] if pomiar_out is not None else None
        # powody TEJ karty osobno — imienny rentgen dostaje je po nazwisku,
        # sumy zbiorcze idą dalej do `powody_odpadniecia`
        _pw: Counter = Counter()
        score, hero = _oceń_karte(
            w, _pw, pomiar_out=pom,
            powody_pomiaru=powody_pomiaru, statystyki=statystyki_przewagi,
        )
        powody_odpadniecia.update(_pw)
        _ri(w["mecz_id"], w.get("podmiot_id") or 0,
            "ocena_przeszla" if hero is not None
            else (_pw.most_common(1)[0][0] if _pw else "bez_szczebla_do_oceny"),
            podmiot=w.get("podmiot"), druzyna=w.get("druzyna"),
            powody=dict(_pw) or None,
            minuty_sr6=w.get("minuty_sr6"),
            udzial_startow=w.get("udzial_startow"),
            xi=w.get("xi"),
            krotkie5=w.get("krotkie_wystepy5"),
            rynki=radar_imienny.opis_rynkow(w.get("rynki")))
        if pom:
            # jeden pomiar na zawodnika w meczu I RODZAJ pomiaru: najlepszy
            # szczebel spod progu pokrycia oraz — osobno — najlepsza linia
            # rynku bez karty (POWOD_POMIARU_RYNKU); to dwa różne pytania
            for _rodzaj in sorted({s.get("powod_pomiaru") or "" for s in pom}):
                _grupa = [s for s in pom if (s.get("powod_pomiaru") or "") == _rodzaj]
                pomiar_kandydaci.append({
                    "mecz_id": w["mecz_id"], "mecz": w["mecz"],
                    "kickoff_ts": w["kickoff_ts"],
                    "podmiot_id": w.get("podmiot_id") or 0,
                    "podmiot": w["podmiot"],
                    **max(_grupa, key=lambda s: s["edge"]),
                })
        if hero is None:
            continue
        w["_score"] = score
        w["hero"] = hero    # najlepsza linia karty — front pokazuje ją w nagłówku
        ocenione.append(w)
    if pomiar_kandydaci:
        # sufit na pomiarze: bierzemy te z największą przewagą, bo to one
        # najbardziej wyglądają na karty, których nie wystawiliśmy
        pomiar_kandydaci.sort(key=lambda s: -s["edge"])
        if pomiar_out is not None:
            # sufit OSOBNO na każdy rodzaj pomiaru — rynek bez karty nie ma
            # prawa wypychać pomiaru progu pokrycia ani odwrotnie
            for _rodzaj in sorted({s.get("powod_pomiaru") or "" for s in pomiar_kandydaci}):
                pomiar_out.extend([
                    s for s in pomiar_kandydaci
                    if (s.get("powod_pomiaru") or "") == _rodzaj
                ][:MAX_POMIAROW_CYKLU])
    diagnostyka.zapisz_rentgen("drabinki_przewaga", statystyki_przewagi)
    if statystyki_przewagi:
        # rozkład tego, co odpada na braku przewagi — materiał pod decyzję
        # o drugiej ścieżce wejścia (mocna seria zamiast przewagi)
        print("Drabinki — odrzucone na przewadze wg jakości: " + ", ".join(
            f"{k}={v}" for k, v in statystyki_przewagi.most_common()
        ))
    diagnostyka.zapisz_rentgen("drabinki_pomiar_progu", powody_pomiaru)
    if powody_pomiaru:
        # PUSTY POMIAR TO TEŻ WYNIK: bez tej linijki „zero typów pomiarowych"
        # wygląda tak samo jak „bukmacher nie kwotuje takich linii", a to
        # zupełnie inna diagnoza (patrz MIN_EDGE_POMIARU).
        print("Drabinki — pomiar progu: " + ", ".join(
            f"{k}={v}" for k, v in powody_pomiaru.most_common()
        ) + f" (do księgi: {min(len(pomiar_kandydaci), MAX_POMIAROW_CYKLU)})")

    # SELEKCJA: globalny TOP po jakości, max MAX_WPISOW_MECZ na mecz i BEZ
    # gwarantowanego slotu — słaby mecz nie dostaje nic (decyzja usera:
    # „tylko najlepsze, nie randomowe"). Wcześniejszy round-robin dawał
    # kartę każdemu meczowi, także takiemu z ujemną przewagą.
    # ⚑ RENTGEN — jedna linia, cała droga od oferty do kandydata. Czytać
    # od lewej: pierwsza liczba, która spada nieproporcjonalnie, wskazuje
    # bramę do naprawy.
    lejek["9_kandydatow_do_oceny"] = len(wpisy)
    # ⚑ RENTGEN PRZEŻYWA CYKL (2026-08-21). `print` idzie do logu Actions,
    # który znika po kilku dniach i wymaga tokena admina — a to są jedyne
    # liczby, na których wolno ruszać progi drabinek. Patrz
    # `diagnostyka.zapisz_rentgen`.
    diagnostyka.zapisz_rentgen("drabinki_lejek", lejek)
    print("Drabinki — LEJEK: " + " | ".join(
        f"{k.split('_', 1)[1].replace('_', ' ')}: {v}"
        for k, v in sorted(lejek.items()) if v
    ))
    diagnostyka.zapisz_rentgen(
        "drabinki_kandydaci_odrzuceni",
        {**powody_odpadniecia, "_przeszlo": len(ocenione)},
    )
    if powody_odpadniecia:
        print("Drabinki — kandydaci odrzuceni: " + ", ".join(
            f"{k}={v}" for k, v in powody_odpadniecia.most_common()
        ) + f" (przeszło: {len(ocenione)})")
    diagnostyka.zapisz_rentgen("drabinki_drugi_szczebel", diag_drabinki)
    if diag_drabinki:
        # dlaczego drabinka skończyła się na pierwszym szczeblu — cztery różne
        # przyczyny, cztery różne lekarstwa (patrz komentarz przy diag_drabinki)
        print("Drabinki — gdzie ginie drugi szczebel: " + ", ".join(
            f"{k}={v}" for k, v in diag_drabinki.most_common()
            if not k.startswith("p2_")
        ))
        rozklad = sorted(
            (k[3:], v) for k, v in diag_drabinki.items() if k.startswith("p2_")
        )
        if rozklad:
            print("Drabinki — szansa drugiego szczebla (przed cięciem): "
                  + ", ".join(f"{k}={v}" for k, v in rozklad))
    # JEDEN ZAWODNIK = JEDNA KARTA W MECZU. Zgłoszenie usera 2026-07-28:
    # „w drabinkach są 4 typy, a 2 są na tego samego zawodnika". Powód:
    # kartę buduje DWIE ścieżki — po historii z trendów i po profilu
    # (debiutanci/transfery) — a id zawodnika w feedzie propsów bywa inne niż
    # kanoniczne ([[drabinki-analiza-zawodnika]], pułapka 3), więc ten sam
    # człowiek wchodził dwoma wejściami. Rozstrzygamy po NAZWISKU, nie po id,
    # i zostawiamy lepszą kartę.
    najlepsza: dict[tuple, dict] = {}
    for w in sorted(ocenione, key=lambda w: -w["_score"]):
        _k = (w["mecz_id"], _klucz_zawodnika(w.get("podmiot") or ""))
        if _k in najlepsza and najlepsza[_k] is not w:
            _ri(w["mecz_id"], w.get("podmiot_id") or 0, "duplikat_zawodnika",
                podmiot=w.get("podmiot"))
        najlepsza.setdefault(_k, w)
    if len(najlepsza) < len(ocenione):
        print(f"Drabinki — dublety tego samego zawodnika: "
              f"{len(ocenione) - len(najlepsza)} kart scalonych")
    ocenione = list(najlepsza.values())

    per_mecz_n: dict[int, int] = {}
    per_dzien_n: dict[str, int] = {}
    wybrane: list[dict] = []
    for w in sorted(ocenione, key=lambda w: -w["_score"]):
        if len(wybrane) >= MAX_WPISOW:
            _ri(w["mecz_id"], w.get("podmiot_id") or 0, "limit_wpisow",
                podmiot=w.get("podmiot"))
            continue
        if per_mecz_n.get(w["mecz_id"], 0) >= MAX_WPISOW_MECZ:
            _ri(w["mecz_id"], w.get("podmiot_id") or 0, "limit_kart_meczu",
                podmiot=w.get("podmiot"))
            continue
        _dz = dzien_karty(w.get("kickoff_ts"))
        if per_dzien_n.get(_dz, 0) >= MAX_KART_DZIEN:
            _ri(w["mecz_id"], w.get("podmiot_id") or 0, "limit_kart_dnia",
                podmiot=w.get("podmiot"))
            continue
        per_mecz_n[w["mecz_id"]] = per_mecz_n.get(w["mecz_id"], 0) + 1
        per_dzien_n[_dz] = per_dzien_n.get(_dz, 0) + 1
        wybrane.append(w)
    wpisy = wybrane
    # OCENA na karcie: miejsce w rankingu dnia + klasa jakości. Front sortuje
    # i oznacza WYŁĄCZNIE tym — nie ma drugiej definicji „najlepszego typu"
    # po stronie web (rozjazd backend/front byłby nie do wytłumaczenia userowi).
    for miejsce, w in enumerate(
        sorted(wpisy, key=lambda w: -w["_score"]), start=1
    ):
        hero = w.get("hero") or {}
        # KOLEJNOŚĆ liczy się z pary szczebli (`_score`), ale KLASA i liczba
        # „przewaga" na karcie zostają przy pierwszym szczeblu — to jego cenę
        # user widzi w nagłówku i to ją porównuje z bukmacherem. Wpisanie tu
        # średniej z dwóch szczebli zmieniłoby znaczenie pola, którego front
        # używa jako „o ile bijemy cenę".
        edge_hero = float(
            hero.get("edge") if hero.get("edge") is not None else w["_score"]
        )
        _ri(w["mecz_id"], w.get("podmiot_id") or 0, "karta",
            podmiot=w.get("podmiot"), miejsce=miejsce,
            hero=f"{hero.get('rynek_kod')} {hero.get('linia')}@{hero.get('kurs')}")
        w["ocena"] = {
            "miejsce": miejsce,
            "klasa": _klasa_karty(edge_hero, miejsce, len(wpisy)),
            "edge": round(edge_hero, 3),
            # NA CZYM STOI KARTA: „przewaga" (nasza szansa bije cenę) albo
            # „seria" (mocne pokrycie przy grywalnej cenie, bez przewagi).
            # Front pisze to wprost — karta bez przewagi nie ma prawa
            # wyglądać jak karta z przewagą.
            "powod_wejscia": hero.get("powod_wejscia") or "przewaga",
            # SITO (2026-09-17): 7/10 + forma 4/5 na tej linii, pełne występy
            # w ostatnich 5 (albo XI), udział startów — front pokazuje to
            # zdaniem; `sito_wyjatek` mówi, który wyjątek wpuścił kartę
            "sito": bool(hero.get("sito")),
            "sito_wyjatek": hero.get("sito_wyjatek"),
            # dlaczego TEN szczebel (18.09, nota przy MIN_KURS_HERO): „perla”,
            # „najwyzsza_mocna”, „tania_z_drugim” — front pisze to zdaniem
            "powod_szczebla": hero.get("powod_szczebla"),
            "p_final": hero.get("p_final"),
            "p_bazowe": hero.get("p_bazowe"),
            "korekta": hero.get("korekta"),
            # wodospad z rynku, który wygrał kartę — front pokazuje go
            # w rozwinięciu jako „dlaczego"
            "kontekst": next(
                (r.get("kontekst") for r in w.get("rynki", [])
                 if r.get("rynek_kod") == hero.get("rynek_kod")),
                None,
            ),
        }
    # drugi przebieg: rozjazdy są już przy szczeblach (albo dociągamy je teraz,
    # gdy cykl nie podał oferty), a tu liczy się PODSUMOWANIE karty — rozjazd
    # przy `hero`, układ „pewniak taniej", kategoria i profil gry. Wszystko to
    # zależy od `hero`, którego przed selekcją jeszcze nie było.
    if bc_cache:
        for w in wpisy:
            podsumuj_rozjazdy_karty(w)
            w["kategoria"] = _kategoria_karty(w)
            w["profil_gry"] = _profil_gry(w)
    else:
        _dopnij_betclic(wpisy, events_meta, sb_cache=sb_cache)
    wpisy.sort(key=lambda w: (w["kickoff_ts"], w["mecz_id"], -w["_score"]))
    for i, w in enumerate(wpisy, start=1):
        w.pop("_score", None)
        w["id"] = i
    return wpisy

