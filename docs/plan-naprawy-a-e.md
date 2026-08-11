# FootStats — jak to działa, jak ma działać, i co naprawiamy

Dokument dla audytora zewnętrznego. Zakłada, że czytelnik **nie zna tego
projektu**, więc zaczyna od podstaw: czym jest produkt, co znaczą pojęcia,
jak przebiega cykl, skąd biorą się dane. Dopiero potem — stan faktyczny
i plan naprawy punkt po punkcie.

Wszystkie liczby pochodzą z produkcyjnej księgi (`typy_log`, 3471 rekordów)
i z dry-runów na żywych danych, wykonanych 11.08.2026. To nie są szacunki.

Osobny dokument — `docs/ustalenia-2026-08-11.md` — opisuje naprawę odwróconego
znaku kalibracji, która wyszła w trakcie tej samej sesji i już weszła do kodu.

---

# CZĘŚĆ I — CZYM JEST TEN PRODUKT

## 1.1 W jednym zdaniu

Serwis analityczny dla zakładów piłkarskich: liczymy prawdopodobieństwa
zdarzeń w nadchodzących meczach, porównujemy je z kursami bukmacherów
i publikujemy na stronie te zakłady, które według nas są warte zagrania.

Produkt ma być sprzedawany klientom, więc liczby na stronie muszą się bronić
w zderzeniu z realnymi wynikami.

## 1.2 Co to jest „typ"

Jeden typ to konkretny zakład na konkretne zdarzenie, opisany pięcioma rzeczami:

```
mecz          Bolívar – São Paulo
podmiot       Bolívar                    (drużyna albo zawodnik)
rynek         Rzuty rożne drużyny
linia         4,5
strona        poniżej
```

czyli: „Bolívar wykona mniej niż 4,5 rzutu rożnego". Bukmacher wycenia to na
przykład na 1,65 — to jest **kurs**. My liczymy własne prawdopodobieństwo
(`p_model`) i porównujemy je z tym, co wynika z kursu.

**Linia jest zawsze połówkowa** (0,5 / 1,5 / 2,5 …), żeby nie było remisu.
Każda linia ma dwie strony:

- **„powyżej"** — zdarzeń będzie WIĘCEJ niż linia,
- **„poniżej"** — MNIEJ.

To są zdarzenia dopełniające: `p_poniżej = 1 − p_powyżej`. Ta tożsamość jest
w tym systemie kluczowa i wraca w części o kalibracji.

## 1.3 Wartość zakładu (EV)

```
EV = p_model × kurs − 1
```

Przy `p = 0,60` i kursie 1,80: `0,60 × 1,80 − 1 = +8%`. Zakład jest wart
zagrania, jeśli EV > 0 — czyli jeśli **nasza szansa jest wyższa niż ta,
którą wycenił bukmacher**.

W Polsce od stawki pobierany jest podatek 12%, więc rozróżniamy:
- **EV brutto** — bez podatku (na tym stoją dziś bramy publikacji),
- **EV netto** — po podatku (pokazywane na karcie).

## 1.4 Dwa światy: drużyny i zawodnicy

To są zupełnie różne dane, różne źródła i różne ryzyko — dlatego mają osobne
zakładki i osobne kalibracje.

**Typy drużynowe** (`team_goals`, `team_corners`, `team_cards`, `team_shots`,
`team_sot`, `team_fouls` oraz `match_*` dla całego meczu):
liczone z historii meczowej drużyny. Nie wymagają znajomości składu. To dziś
~93% naszej produkcji.

**Typy zawodnicze** (`shots`, `sot`, `tackles`, `fouls_committed`, `fouls_won`,
`interceptions`, `shots_outside_box`, `headed_shots` …): liczone z historii
występów konkretnego zawodnika. **Wymagają wiedzy, czy zawodnik zagra**
i ile minut — bez składu nie ma typu.

Wszystkie typy zawodnicze są po stronie **„powyżej"** (bukmacherzy kwotują
„Messi odda 2+ strzały", nie „mniej niż 2"). Ta asymetria ma znaczenie
techniczne — patrz część o kalibracji.

## 1.5 Co to jest drabinka

Drabinka to karta jednego zawodnika, pokazująca **kilka linii tego samego
rynku naraz** — od najtańszej do najdroższej:

```
Ross Sykes (Union Saint-Gilloise) — Strzały
  szczebel 1:  0,5+  @ 1,55    trafione w 9 z 10 ostatnich meczów
  szczebel 2:  1,5+  @ 2,60    trafione w 5 z 10
```

**Szczebel** = jedna linia na karcie.
**Hero** = szczebel, który jest naszym właściwym typem (zwykle pierwszy).
**Pokrycie** = ile razy w ostatnich meczach zawodnik przebił tę linię
(„9 z 10"). To jest rdzeń analizy — dokładnie to, co typerzy wypisują ręcznie.

Sens produktowy: klient widzi bezpieczną podstawę i dołożoną wartość w jednym
miejscu. Karta z jednym szczeblem **nie jest drabinką** — to zwykły typ
zawodniczy.

Karta niesie też kontekst: profil rywala, sędzia, dom/wyjazd, udział
w pierwszym składzie, średnie minuty.

## 1.6 Co to jest kupon

Kupon to kilka typów połączonych w jeden zakład — wszystkie muszą trafić.
Pojedynczy typ w kuponie nazywamy **legiem**.

```
kupon „dzienny 2–3":  3 legi, kurs łączny 2,01, nasza szansa 66%
```

Kupony mają trzy horyzonty (`dzienny`, `dlugoterminowy`, `value`) i własne
urealnienie szansy, bo błąd pojedynczego typu podnosi się do potęgi: przy
sześciu legach pomyłka rzędu 15% robi z deklarowanych 17% realne 7%.

Problem, którego jeszcze nie rozwiązaliśmy: **legi między kuponami się
powtarzają**. Dziś jeden zakład siedzi w 4 z 5 kuponów — jedna pomyłka kładzie
komplet, a raport traktuje je jak niezależne próby.

## 1.7 Trzy stany typu w systemie

Każdy policzony typ trafia do księgi (`typy_log`) w jednym z trzech stanów.
Rozróżnienie jest ważne dla każdego pomiaru:

| stan | co znaczy | czy liczy się do skuteczności |
|---|---|---|
| **opublikowany** | stał na liście, klient go widział | TAK |
| **poza publikacją** | policzony, ale brama go zdjęła | nie — uczy w tle |
| **pomiarowy** (`odrzucony`) | minął się z progiem niewiele; celowo rozliczany, żeby wiedzieć, czy próg jest dobry | nie |

Dzięki temu wiemy nie tylko, jak wypadły typy pokazane, ale też **jak
wypadłyby te odrzucone** — bez tego nie da się ocenić, czy bramy działają.

---

# CZĘŚĆ II — SŁOWNIK POJĘĆ WEWNĘTRZNYCH

Terminy, które padają w kodzie i w dalszej części dokumentu.

**λ (lambda)** — przewidywana liczba zdarzeń w meczu (np. „Bolívar wykona
średnio 5,2 rożnego"). Z niej i z rozkładu liczymy `p` dla każdej linii.

**Posterior / prior** — model liczy rozkład intensywności zdarzeń metodą
bayesowską. `prior` to punkt wyjścia (średnia rozgrywek), `posterior` to
połączenie priora z historią tej drużyny. Im więcej własnej historii, tym
mniej znaczy prior.

**ESS (efektywna próba)** — ile meczów **realnie** stoi za prognozą po
uwzględnieniu wag świeżości. Drużyna z 20 meczami sprzed pięciu lat ma ESS ≈ 2;
drużyna z 8 meczami z ostatnich dwóch miesięcy ma ESS ≈ 7,5. Ta druga jest
lepiej opisana.

**Udział priora** — jaka część prognozy pochodzi ze średniej rozgrywek zamiast
z tej konkretnej drużyny. `prior / (prior + ESS)`.

**Kalibracja / bias / delta** — poprawka nakładana na surowe `p` modelu,
wyliczona z historycznych rozliczeń. W przestrzeni logitów:
`p' = sigmoid(logit(p) + delta)`. Delta ujemna ściąga szansę w dół, dodatnia
podnosi.

**Warstwy uczenia** — system ma dziewięć mechanizmów korygujących liczonych
z rozliczeń (kalibracja rynkowa, korekta strumienia, szansa pokazywana, wagi
zaufania, kary korelacji, kalibracja kuponów…). Dwie z nich są „krytyczne" —
ich awaria przerywa cykl.

**Strumień** — grupa typów uczona osobno: `pewniaki` (zawodnicy), `druzyny`,
`drabinki`.

**Ekran** — zakładka, na której typ się pokazał; zapisywany przy publikacji,
nie zgadywany po fakcie.

**Kwarantanna** — mechanizm wstrzymujący rynek albo stronę linii, gdy wypada
źle. **Właściciel zdecydował, że tego nie używamy** (patrz C3).

**Rejestr publikacji** — lista typów aktualnie stojących na stronie, trzymana
osobno od księgi. Dzięki niej typ raz pokazany nie znika, gdy feed na moment
zamilknie.

**Wznowienie** — typ, który wraca na listę z rejestru albo z księgi, bo wciąż
jest przed meczem. Niesie **zamrożoną cenę i szansę z chwili pierwszej
publikacji** — bo to je klient widział.

**Epoka produktu** — `mundial` (do 19.07) / `liga` (od 21.07). Rozliczenia
z zakończonej epoki nie uczą dzisiejszego modelu.

**Wersje** — stempel przy typie: `model`, `kalibracja`, `polityka`, `dane`.
Pozwala oddzielić w pomiarach typy policzone różnymi rachunkami.

**CLV** — różnica między kursem, po którym typ wystawiliśmy, a kursem tuż
przed meczem. Dodatni CLV znaczy, że rynek się do nas przesunął.

**Brier** — miara jakości prognozy probabilistycznej (średnia z kwadratów
błędów). Niżej = lepiej. Używamy jej do porównania „nasza liczba kontra
liczba wyczytana z kursu" — to jest **najważniejszy miernik w tym projekcie**.

---

# CZĘŚĆ III — JAK DZIAŁA CYKL

Cały produkt to jeden program (`build_league` → `build_wc_fast`), uruchamiany
w chmurze co ~30–90 minut. Jeden przebieg trwa 30–45 minut i wykonuje po kolei:

```
1. TERMINARZ
   Pobierz nadchodzące mecze (statshub) i sparuj je z ofertą bukmachera
   (Superbet). Dziś: 403 mecze statshub, 826 Superbet, sparowanych 317.

2. DANE HISTORYCZNE
   Dla każdej drużyny/zawodnika z terminarza pobierz historię występów.
   Budżety zapytań są ograniczone i regularnie się wyczerpują.

3. KONTEKST MECZU
   Sędzia (365Scores), tempo i spread z kursów meczowych, profil rywala
   (ile dopuszcza), dom/wyjazd, styl gry z banku.

4. MODEL
   Z historii + kontekstu policz λ, z niej rozkład liczby zdarzeń,
   z rozkładu p dla każdej kwotowanej linii.

5. KALIBRACJA
   Nałóż poprawki wyliczone z historycznych rozliczeń (warstwy uczenia).

6. BRAMY
   Odsiej typy, które nie spełniają progów: zbyt niska szansa, kurs poza
   widełkami, ujemna wartość, rozjazd z rynkiem, za stara historia…
   Odrzucone trafiają do rejestru odrzuceń z powodem.

7. SELEKCJA LISTY
   Z tego, co przeszło, wybierz listę dnia (limity: na dzień, na mecz,
   na rynek). Reszta zostaje w puli kuponów.

8. WZNOWIENIA
   Dołóż typy, które stały na liście wcześniej i wciąż są przed meczem —
   z zamrożoną ceną.

9. DRABINKI (radar)
   Osobna ścieżka: karty zawodników z kilkoma szczeblami.

10. KUPONY
    Złóż kupony z puli legów, z karą za korelację między meczami.

11. PUBLIKACJA
    Wypchnij wynik do bazy. Strona czyta z bazy.

12. ROZLICZENIE (osobny, lżejszy job)
    Po meczu sprawdź faktyczne wartości i zamknij typy w księdze.
    Rozliczony rekord jest ZAMROŻONY — błąd zostaje w danych na zawsze.
```

Kluczowa właściwość: **wszystko, co model zapisuje przy publikacji, jest
zamrożone** — cena, szansa, użyte poprawki, wersje. Rozliczenie porównuje
z tym, co obiecaliśmy w chwili, gdy klient to widział.

---

# CZĘŚĆ IV — ŹRÓDŁA DANYCH

## 4.1 Co mamy dzisiaj

| źródło | co daje | stan |
|---|---|---|
| **statshub** | terminarz, historia drużyn i zawodników, trendy, składy | główne; **49 pól na mecz, używamy 5** |
| **Superbet** | kursy (główny bukmacher), propsy zawodnicze | jedyne źródło cen na liście |
| **Betclic** | kursy zawodnicze (drugi cennik, gRPC-Web) | działa: 21 meczów, 980 zawodników; **0 typów na stronie** |
| **365Scores** | statystyki meczowe, bank stylu, sędziowie, rozliczenia | używane tylko do rozliczeń i sędziów |
| **Sofascore** | składy, pełne statystyki meczowe | **jedyne działające źródło składów** (13 z 307 meczów) |
| **Rotowire** | przewidywane składy | **daje 0 — pyta o zakończony mundial** |
| **eloratings** | siła drużyn | marginalne |
| **STS** | kursy (sugestie) | osobna, słabo wypadająca ścieżka |

## 4.2 Największa niewykorzystana rezerwa: statshub

Sonda na żywym feedzie: **49 różnych pól w każdym meczu, konsumujemy pięć**
(`totalShotsOnGoal`, `shotsOnGoal`, `cards`, `cornerKicks`, `fouls`).

Nieużywane m.in.: `expectedGoals` (xG), `totalShotsInsideBox`,
`touchesInOppBox`, `finalThirdEntries`, `bigChanceCreated/Missed/Scored`,
`ballPossession`, `pass_accuracy`, `accurateCross`, `throwIns`, `goalKicks`,
`totalTackle`, `interceptionWon`, `duelWonPercent`, `dispossessed`,
`totalClearance`, `offsides`, `goalsPrevented`, oraz `yellowCards`
i `redCards` osobno (my mamy tylko sumę).

**I to nie jest teoretyczna strata.** Pomiar na 536 parach „historia 10 meczów
→ następny mecz", 19 drużyn — korelacja z wynikiem następnego meczu
(★ = pole, którym liczymy dzisiaj):

```
RZUTY ROŻNE — nasz predyktor jest dopiero SZÓSTY:
  strzały z pola karnego        +0,145
  dotknięcia w polu rywala      +0,126
  ★ strzały                     +0,123
  wznowienia bramkarza          −0,102
  xG                            +0,097
  celność podań                 +0,089
  ★ ROŻNE (tym liczymy)         +0,082
```

Historia rożnych przewiduje rożne **gorzej** niż strzały z pola karnego.
To tłumaczy, dlaczego na `team_corners` — naszym największym rynku — nasza
liczba nie wnosi nad kurs nic (AUC 0,499).

Dla kartek, strzałów i fauli liczymy właściwym polem, ale zostawiamy na stole
niezależne sygnały (wrzuty, celność podań, pojedynki — wszystkie mówią o stylu
gry).

**`opponentStatistics`** — te same ~40 pól po stronie rywala w każdym meczu
historii, czyli **koncesje zmierzone zamiast przybliżanych**. Wypełnione
w 40/40 meczów w sondzie. Kod je pobiera i **nigdzie nie czyta**.

## 4.3 Dziury w danych — nie tam, gdzie się wydaje

1. **Kontuzje, zmęczenie, rotacja — zero danych.** Pole `injured_or_suspended`
   istnieje i jest konsumowane przez model minut, ale w produkcji **nikt nigdy
   go nie ustawia** — jedyne przypisanie `True` jest w teście. Rotowire ma
   sekcję kontuzji i świadomie ją odcinamy. Odstęp między meczami, podróż
   i strefa czasowa nie występują w kodzie w ogóle.
2. **Kontekst rywala nieobecny albo dziedziczony.** Ścieżka `performance`
   (jedyna dla Ekstraklasy, kwalifikacji i części Ameryki Płd.) zwraca
   `opponent_average = None`, więc czynnik rywala jest neutralny. Osiem rynków
   dziedziczy koncesje po „rynku-rodzicu" z wagą 0,5.
3. **Korelacja między drużynami zmierzona tylko dla rożnych** (ρ = −0,127).
   Osiem z dziesięciu rynków `match_*` / `wiecej_*` jedzie na założeniu
   niezależności, co zawyża sumy i zaniża „kto więcej".

## 4.4 Czego nie rekomendujemy

**Kupowania danych z SportMonks** (€99/mies. za 30 lig). Konkurencja na tym
stoi, ale dla nas to zamiana jednego problemu na drugi: dostaniemy komplet dla
lig, których w większości nie obstawiamy, a nasz zakres to Ameryka Południowa
i Skandynawia. Wrócić do tego, gdy własne źródła będą wyciśnięte.

---

# CZĘŚĆ V — JAK TO MA DZIAŁAĆ DOCELOWO

## 5.1 Cel nadrzędny właściciela

> **Model ma być samodzielny analitycznie, a nie przepisywać kursu.**

Dziś podejrzenie jest takie, że nasza prognoza to w praktyce przeskalowany kurs
bukmachera: bierzemy cenę, dokładamy kilka mnożników i wychodzi coś, co z ceną
koreluje, ale nie wnosi ponad nią informacji. Korelacja `p_model` z ceną
wynosi **0,965**.

Docelowo: model patrzy na dane sportowe (historia, forma, rywal, sędzia, tempo,
kontekst) i wyciąga wniosek **niezależnie** od tego, co wycenił bukmacher.
Kurs służy do dwóch rzeczy: (a) oceny opłacalności, (b) znalezienia okazji,
gdzie rynek się myli.

## 5.2 Struktura produktu

```
ZAWODNICY  →  Wysoka szansa  +  Drabinki
DRUŻYNY    →  Wysoka szansa  +  Value
```

Odrzucono propozycję trzech wspólnych zakładek: to inne dane, inne źródła
i inne ryzyko, więc mieszanie utrudniałoby diagnozę, gdy jeden strumień siądzie.

**Konsekwencja techniczna:** cztery strumienie znaczy **cztery osobne
kalibracje**. Dziś są trzy, a „value drużynowe" nie ma własnej — dziedziczy
korektę po pewniakach, czyli regułę wyliczoną na typach po kursie ~1,25.
To jedna z przyczyn, dla których value praktycznie nie powstaje.

**Dwa silniki oceny, nie jeden z dwoma progami:**

- **„wysoka szansa"** — ostrożność jest zaletą: dolna granica przedziału
  zostaje, próg na wysokiej szansie, kursy jakie wyjdą,
- **„value"** — liczba **środkowa**, nie dolna granica; kalibracja liczona
  wyłącznie na rozliczeniach z tej ścieżki; próg na przewadze nad ceną.

Uzasadnienie: value polega na tym, że nasza liczba jest **wyższa** od ceny,
a obecny silnik systematycznie ją zaniża — więc value nigdy nie powstaje.

## 5.3 Napięcie, które trzeba znać

Pomiar pokazuje, że **trafialność i zysk nie mieszkają w tym samym miejscu**:

```
typy z obietnicą ≥ 85%      n=189   trafia 83,6%   kurs 1,22   zwrot  +2,0%
gole drużyny 0,5 poniżej    n=113   trafia 43,4%   kurs 2,80   zwrot +19,7%
```

Drugi wiersz to jedyny typ w całej księdze, który realnie zarabia — i trafia
43 razy na 100. Pierwszy to produkt, który trafia 84 razy na 100 i wychodzi
na zero.

Właściciel chce obu, w osobnych zakładkach, z **różnymi obietnicami wobec
klienta**. Klient, który dostaje kurs 2,80 w zakładce nazwanej „pewne typy",
czuje się oszukany, nawet jeśli typ jest dobry.

---

# CZĘŚĆ VI — STAN FAKTYCZNY

## 6.1 Skuteczność (epoka ligowa, od 21.07)

```
razem widoczne     n=835   trafienia 57,0%   deklaracja 68,9%   ROI brutto −6,4%
główny model       n=748   trafienia 59,5%   deklaracja 70,8%   ROI brutto −4,0%
drabinki           n= 87   trafienia 35,6%   deklaracja 52,4%   ROI brutto −27,0%
```

Luka między obietnicą a rzeczywistością: **−12 punktów procentowych**.

## 6.2 Najważniejszy pomiar: czy bijemy cenę

Brier modelu kontra Brier wyczytany z kursu, 2438 rozliczeń (niżej = lepiej):

```
rynek              n     model     z kursu   kto lepszy
match_corners     150    0,1876    0,1840    kurs
shots             143    0,2472    0,2379    kurs
team_sot          126    0,2286    0,2192    kurs
team_goals        740    0,2217    0,2050    kurs
team_cards        153    0,2295    0,2106    kurs
team_shots         92    0,2758    0,2440    kurs
team_corners      865    0,2417    0,2061    kurs
RAZEM            2438    0,2304    0,2083    kurs — 0 rynków na 10 dla nas
```

Dodatkowo: tercyle deklarowanej przewagi **nie porządkują wyniku** — typy
z najwyższą deklarowaną przewagą trafiają najsłabiej (51,6%, Brier 0,257).
Czyli sygnał, którym sortujemy listę, jest odwrócony.

## 6.3 Stan strumieni

```
zakładka zawodnicza    bez typu od 05.08
drabinki               0 świeżych kart, 3 wznowione (2 z ujemną przewagą)
lista drużynowa        117 typów: 93% „poniżej", 62% gole drużyny
                       103 ze 117 to wznowienia, 44 starsze niż 2 dni
kupony                 długoterminowe 50/5 wygranych/−61,6%
                       value 10/0/−100%
                       dzienne pozornie +80%, ale cały plus to jeden dzień
```

## 6.4 Pokrycie danych

```
mecze sparowane                     317 z 403
w zakresie drużynowym                94 z 307
składy (pełne XI)                    13 z 307
historia goli drużyn                 18 ze 160 (budżet wyczerpany)
historia rożnych                     53 ze 160
zawodnicy poza znanym składem       199 par (mecz, zawodnik)
```

---

# CZĘŚĆ VII — PLAN NAPRAWY A–E

Numeracja z rozmowy z właścicielem. Przy każdym punkcie: stan, decyzja,
sposób wykonania.

---

# A. DANE

## A1. Wszystkie typy, nie 2–3 na mecz

**Dziś:** mediana 2 typy na mecz. Wąskie gardło jest przed limitami:

```
Rynki drużynowe: 94/307 meczów w zakresie
odpadło: kurs_poza_widelkami=1029, szansa_za_niska=719, brak_kursu=645,
         rozjazd_z_rynkiem=373, wartosc_ujemna=206, chwiejna_predykcja=109
```

Dwie trzecie meczów nie wchodzi w ogóle do liczenia, bo zakres jest zawężony
konfiguracją do „top 5 + Ekstraklasa + puchary".

**Decyzja:** typy mają powstawać dla wszystkich meczów, które są na stronie.

**Jak:**

1. **Zakres z danych, nie z listy lig.** Mecz wchodzi, jeśli obie drużyny mają
   ESS ≥ 5 w danym rynku. Kryterium: „czy mam świeżą historię", nie „czy to
   prestiżowa liga". Rozszerza się samo, w miarę dociągania danych.
2. **Widełki kursu jako routing, nie brama** (dziś największe cięcie):
   ```
   1,10–1,60  →  Wysoka szansa
   1,60–1,80  →  Wysoka szansa jeśli ESS ≥ 10, inaczej Value
   1,80+      →  Value
   > 8,0      →  poza listą (nie mamy czym mierzyć)
   ```
3. **Limit per mecz podnosimy dopiero po naprawie modelu** — dziś 6 typów
   z jednego spotkania to sześciokrotność tego samego błędu.

**Oczekiwany efekt:** ~118 → 300–400 typów dziennie. Przy zamrożonej liście
15–20 pozycji (C6) daje to realny wybór; dziś wybieramy 118 ze 137, czyli
praktycznie nie wybieramy.

## A2. Priorytet pobierania

**Dziś:** budżet dzieli się po kolejności w tablicy, kończy w połowie alfabetu.

**Jak:**

```
< 24 h do meczu    komplet danych, poza budżetem
24–72 h            historia podstawowa
> 72 h             z reszty budżetu
```

**Pamięć między cyklami — właściwa oszczędność.** Historia drużyny nie zmienia
się co 30 minut, a dziś pobieramy ją co cykl. Trzymamy 3 dni i odświeżamy tylko
drużyny, które w tym czasie zagrały (wiadomo z terminarza, bez zapytania).
**Zwalnia 60–70% budżetu bez dokładania zapytań.**

**Budżet proporcjonalny do składu listy z poprzedniego tygodnia.** Dziś:

```
team_cards=158, team_fouls=153, team_shots=153, team_sot=153   (komplet)
team_goals=18, team_corners=53                                  (a to 85% listy)
```

## A3. Składy z innych źródeł

**Dziś — usterka, nie ograniczenie:** `rotowire.py` odpytuje `league=WOC`,
czyli mistrzostwa świata zakończone 19.07. Trzy tygodnie pytania o turniej,
którego nie ma.

```
Składy: pełne XI dla 13 z 307 meczów (0 potwierdzonych; sofascore: 13)
Rotowire: przewidywane składy 0 drużyn
Poza znanym składem: 199 par — typy i karty nie powstają
```

To bezpośrednia przyczyna martwych drabinek i pustej zakładki zawodniczej.

**Jak — trzy warstwy:**

| źródło | dziś | docelowo |
|---|---|---|
| Sofascore | 13 meczów, jedyne działające | główne, budżet w górę |
| 365Scores | tylko rozliczenia | drugie źródło (ma `lineups`, wpięte) |
| statshub `team-lineup` | 0 | sprawdzić, czemu milczy |
| Rotowire | 0 | poprawne kody lig; obsłuży ~20% zakresu |

**Warstwa druga — skład zastępczy z rotacji.** Gdy nikt nie podaje XI, budujemy
jedenastkę z minut z ostatnich sześciu meczów: kto grał 90 minut w pięciu na
sześć, gra i teraz. Dane już policzone (`udzial_startow`, `minuty_sr6`) — dziś
służą tylko do oceny. Karta dostaje etykietę „skład przewidywany z rotacji".

**Warstwa trzecia — tej zabrakło najbardziej:**

```
Każde źródło ma zadeklarowany minimalny dorobek na cykl.
Trzy cykle z rzędu poniżej progu = cykl kończy się CZERWONY.
```

System ma dziewięć warstw uczenia z licznikami, z których dwie potrafią
przerwać cykl — a **źródła danych nie mają ani jednego strażnika**. To ta sama
dziura, która przepuściła mundial przez trzy tygodnie.

## A4. Limit zapytań (HTTP 429)

```
1. Ogranicznik tempa    stała liczba zapytań/s na źródło, JEDNA kolejka na cykl
                        (dziś każdy moduł wali w API niezależnie)
2. Ponowienie           przy 429: 2 s, 4 s, 8 s, potem odpuść
                        (dziś jedno 429 = trwała strata rekordu)
3. Pamięć negatywna     „nie mam" nie jest pytane ponownie przez dobę
```

Punkt trzeci: przy ~130 zawodnikach bez pary u bukmachera to kilkaset spalonych
zapytań dziennie na odpowiedzi „nie mam".

## A5. Skąd wziąć brakujące dane

1. **Wycisnąć `/team/{id}/performance`** — najtańsze źródło: **40 meczów
   historii za jedno zapytanie**, niezależnie od tego, czy ktokolwiek ten mecz
   kwotował. Dziś używane resztkowo, bo konkuruje o budżet z danymi
   zawodniczymi. Osobny budżet + pamięć z A2 = pokrycie rośnie z 94 do
   praktycznie wszystkich meczów. **Jedna zmiana załatwiająca większość braków.**
2. **Sparować 12 drużyn bez identyfikatora 365** — Lyon, Rapid Wiedeń, AGF,
   Helsingborg, Hearts, Borac Banja Luka i sześć innych. Godzina roboty,
   odblokowuje ich historię na stałe.
3. **Sięgnąć po nieużywane pola statshuba** (część IV.2) — zwłaszcza
   `opponentStatistics` i predyktory rożnych, które przewidują lepiej niż to,
   czym liczymy dziś. **To jest największa pojedyncza rezerwa jakości w całym
   projekcie.**

---

# B. MODEL

## B1. Historia kompletna i świeża

**Uwaga metodologiczna: pierwsza hipoteza była błędna.** „Model liczy średnią
z pięciu lat" — nieprawda. `fit_posterior` waży mecze wykładniczo
(`w = exp(−dni/180)`), więc mecz sprzed czterech lat wnosi 0,03%.

Prawdziwe problemy są dwa:

**(a) Opisy ciągnęły archiwum.** `tt.counts[:20]` brało dwadzieścia ostatnich
*rekordów*, nie meczów — karta pokazywała pod „ostatnie mecze" spotkania sprzed
pięciu lat (Bolívar: rożne z 2020; Raków: gole od 2022; 186 z ~960 meczów
starszych niż 400 dni). **→ NAPRAWIONE 11.08.**

**(b) Gdy własnej historii brakuje, model podstawia średnią rozgrywek
i publikuje to jako prognozę drużyny:**

```
drużyna              ESS     udział średniej ligi w prognozie
Boca Juniors        1,97              67%
Bolívar             2,68              60%
São Paulo           3,47              54%
mediana (48 drużyn) 10,3              28%
```

`counts.MIN_EFFECTIVE_MATCHES = 4.0` istnieje w kodzie od początku
i **nigdzie nie jest używany**.

**Jak:**

1. Twardy sufit wieku 18 miesięcy — **zrobione**. (Nie krócej: drużyna
   pucharowa gra sześć meczów w sezonie.)
2. Waga malejąca z wiekiem — już jest, tau = 180 dni.
3. **ESS jako kryterium, nie liczba meczów.**
4. **Przerwa sezonowa nie liczy się do wieku meczu** — inaczej karzemy ligi
   skandynawskie za zimę. Wykrywamy luki > 45 dni w kalendarzu drużyny
   i odejmujemy je od wieku. Dane mamy (timestampy).
5. **Rozdzielić „mało danych" od „słabe dane"** — dziś jedno i drugie kończy
   się brakiem typu, więc nie wiemy, czy dociągać dane, czy poprawiać model.
6. Na karcie: „liczone z 9 meczów, ostatni 6 dni temu".
7. **Codzienny raport pokrycia** — ile drużyn ma ESS ≥ 5 w każdym rynku, trend
   tydzień do tygodnia. Bez tego nie zauważymy, że pokrycie się sypie.

## B2. Segmenty, w których nasza liczba nic nie wnosi

**Dziś** silnik sam to wylicza i sam ignoruje:

```
team_corners|ponizej  w=0.00  (n=790, ROI −7%)
team_goals|powyzej    w=0.00  (n= 90, ROI −34%)
team_shots|ponizej    w=0.00  (n= 73, ROI −22%)
shots|powyzej         w=0.00  (n= 69)
```

**Decyzja: nie blokujemy** (C3). Zamiast tego routing:

```
waga ≥ 0,5    →  Wysoka szansa
waga 0,2–0,5  →  Wysoka szansa, ale wymaga ESS ≥ 10
waga < 0,2    →  Value (jedynym powodem wejścia jest cena)
```

**Waga per (rynek, strona, liga)**, nie globalnie — dziś „rożne poniżej" ma
jedną wagę dla Brasileirão i Allsvenskan, a kartki to 1,05 na drużynę
w Superlidze duńskiej i 2,56 w Brasileirão B.

## B3. Kalibracja per rynek

**Dziś:** jedna korekta na cały strumień drużynowy. A błędy idą w przeciwne
strony — gole przeszacowujemy o ~20%, rożne niedoszacowujemy o ~7%.

*Dowód, że to nie teoria: po naprawie znaku `team_goals` ma w trzecim przedziale
szansy deltę −0,26 przy globalnej +0,466 — w jednym paśmie model faktycznie
niedoszacowuje. Przy jednej korekcie na strumień było to niewidoczne.*

**Hierarchia z cofaniem się do rodzica:**

```
poziom 1  (rynek, strona, przedział szansy)  ≥ 25 rozliczeń → własna korekta
poziom 2  (rynek, strona)                    ≥ 25           → korekta rynku
poziom 3  strumień                           ≥ 25           → korekta strumienia
poziom 4  globalna                                          → ostatnia deska
```

Plus: **ściąganie proporcjonalne do próby** (komórka z 26 rozliczeniami nie
dostaje pełnej korekty) i **widoczne, ile stoi na czym** — dziś `18 z 76 na
własnych danych, 30 × wartość globalna, 28 × połowa korekty z poprzedniej
epoki`, czyli ponad połowa to zapożyczenia z innego produktu.

## B4. Podbicie w ostatniej warstwie

**Dziś:** trzecia warstwa dodaje drużynom **+0,104** — podnosi pokazywaną
liczbę o ~2 pp przy luce 12 pp w drugą stronę.

*Po naprawie znaku ta wartość prawie na pewno się zmieni — ta warstwa
kompensowała błąd piętro niżej. Nie ruszamy jej; niech pomiar pokaże nową
wartość na rozliczeniach V2.*

## B5. Kontrola „czy bijemy cenę"

**Decyzja: miernik, nie brama.** Ale musi być **jeden** — dziś dwa pomiary tej
samej rzeczy dają różne wyniki (0 z 10 kontra 3 z 10), bo liczą na innych
oknach.

```
jedna definicja   Brier modelu vs Brier z kursu (po zdjęciu marży)
jedno okno        ostatnie 90 dni, epoka bieżąca
jeden zbiór       wszystkie rozliczone, także mierzone w tle
jedna tabela      w Skuteczności, aktualizowana co cykl
```

---

# C. LISTA

## C1 / C2. Zakładki

Patrz część V.2. Nazwy dla klienta: **„Duża szansa"** i **„Wyszukane okazje"**
(zamiast „value" — po polsku, bez żargonu).

## C3. ⚑ Czarnej listy NIE MA

**Decyzja właściciela, kategoryczna.** Odrzucono propozycję wycięcia rynków
i linii, które dziś tracą najwięcej (rożne 2,5 poniżej: 17,9% trafień; strzały
0,5 powyżej: 33,3%; faule popełnione: 0 na 8).

Uzasadnienie: **to są dobre typy, tylko model jest zły.** Jeśli wycinek wypada
źle, przyczyną jest rachunek, a nie wycinek. Kwarantanny i czarne listy są
ostatecznością i traktujemy je jako przyznanie się do porażki modelu.

**Ta zasada jest nadrzędna wobec wszystkich innych punktów dokumentu.**

## C4. Jeden typ na mecz — najlepiej przeanalizowany

**Przyjęte.** Kryterium wyboru jest miejscem, gdzie jest najwięcej do ugrania,
bo dziś sortujemy po sygnałach **odwróconych** (114 rozliczeń, tercyle):

```
wg deklarowanej pewności   górna 1/3 −4,2%    dolna 1/3 +26,6%
wg deklarowanej przewagi   górna 1/3 −41,2%   dolna 1/3 +32,5%
wg wysokości kursu         górna 1/3 +18,9%   dolna 1/3 −10,2%
```

**Nowe kryterium:** (1) długość i świeżość historii, (2) jednoznaczność serii
(9/10 bije 6/10 nawet przy gorszym kursie), (3) zgodność źródeł, (4) dopiero
potem szansa i cena.

## C5. Horyzont publikacji ZOSTAJE

**Decyzja:** bez zmian. Typy z dnia meczu zarabiają (+3,3% / +4,0%), a odległe
tracą (−14,2% / −10,1%) — ale **to objaw błędu modelu, nie argument za
skróceniem horyzontu**. Model ma się nauczyć liczyć mecze odległe.

## C6. Zamrożona lista dnia

```
1. Lista dnia D domyka się o 6:00 rano dnia D.
2. Limit 15 typów w KAŻDYM strumieniu (zawodnicy/wysoka szansa,
   drużyny/wysoka szansa). Value i drabinki mają własne, mniejsze.
3. Po domknięciu typ NIE ZNIKA i NIE DOCHODZI nowy.
   Jedyna zmiana: adnotacja „cena spadła z 1,85 na 1,62".
4. Mecze nocne (Ameryka Płd. po 1:00) liczą się do dnia poprzedniego.
```

**Dlaczego 6:00:** klient wchodzi rano i widzi komplet na dzisiaj.

**Co to daje poza porządkiem:** dopiero wtedy da się uczciwie zmierzyć
skuteczność. Dziś typ może wejść na listę 20 minut przed gwizdkiem i policzyć
się tak samo jak stojący od rana.

**Warunek wstępny:** ma sens dopiero po A1.

---

# D. DRABINKI

## D1. Problem jest w modelu, nie w koncepcji

**Ustalenie właściciela**, poparte przysłanymi przykładami kart, gdzie drugi
szczebel jest wyraźnie osiągalny.

**Ta sama niepewność karana trzy razy:**

```
p_baz   = _wilson_low(traf, z)                    ← ścięcie 1
p_final = p_baz × korekta_kontekstu               ← ścięcie 2
          → + korekta_strumienia (−0,40 logit)    ← ścięcie 3
próg: p_final ≥ 0,25
```

**Ścięcie trzecie jest najgorsze: korekta strumienia została zmierzona na
PIERWSZYCH szczeblach** (tylko one trafiały na stronę i się rozliczały),
a stosuje się do drugich.

*Korekta wcześniejszego oszacowania: `WILSON_K = 0,674`, nie 1,96 — więc 5/8
daje 0,506, a nie 0,33. Przy kontekście 1,0 taki szczebel wychodzi na 0,407
i przechodzi; wypada dopiero przy kontekście ~0,55. Główną karą jest korekta
strumienia i mnożnik kontekstu, nie Wilson.*

**Liczniki (przeszło: 0):**

```
kandydaci odrzuceni: slabe_pokrycie=54, jednoszczeblowa_brak_kolejnej_linii=36,
  za_malo_minut=29, rzadko_w_pierwszym_skladzie=29, kurs_ponizej_progu=20
gdzie ginie drugi szczebel: start_pominiety_przez_cene=438,
  nastepnik_ponizej_progu_szansy=320, nastepnik_ucialy_sufit_linii=65
szansa drugiego szczebla: 00-10%=239, 10-20%=67, 20-25%=14, 30-40%=6, 40%+=1
```

**Naprawa w tej kolejności:**

1. **Zdjąć trzecie ścięcie z drugiego szczebla** — stosować korektę liczoną
   na drugich szczeblach albo żadną. Przenosi kartę 5/8 z ~22% na ~31%.
2. **Wilson tylko przy krótkiej próbie** (4–7 meczów). Przy 8+ wystarczy sam
   procent z lekkim ściągnięciem. Karta 5/8 wychodzi wtedy na ~48%.
3. **Pokrycie ma decydować, nie nasz procent** — komentarz we własnym kodzie to
   mówi, ale próg na procencie stoi przed pokryciem i wycina wcześniej.
4. **Dopiero potem zmierzyć, gdzie naprawdę leży próg.**

## D2. Kiedy karta jest drabinką, a kiedy pewniakiem

**Wyjaśnienie licznika:** `start_pominiety_przez_cene = 438` **nie jest
ubytkiem**. Drabinka startuje od pierwszej linii z ceną ≥ 1,45; tańsze
przewijamy. Licznik mówi, ile razy przewinęliśmy. Realny killer to
`nastepnik_ponizej_progu_szansy = 320`.

**Reguła routingu (ustalenie właściciela):**

```
pierwszy < 1,45  I  drugi < 2,20        →  Wysoka szansa (tani pewniak)
pierwszy ≥ 1,45                          →  Drabinki
pierwszy 1,20–1,45, ale drugi ≥ 2,20
    przy pokryciu drugiego ≥ 50%         →  Drabinki
```

Ten drugi warunek to **najciekawszy typ karty**: tani, pewny start plus drugi
szczebel po 2,20+, który realnie wchodzi. Dziś `MIN_KURS_PIERWSZEGO` wyrzuca
te karty do kosza, zamiast skierować do właściwej zakładki.

## D3. Bez składów nie ma kart

Patrz A3. **Do czasu naprawy:** karty wznowione bez świeżego przeliczenia nie
idą na stronę. Dziś stoją trzy, dwie z ujemną przewagą, wszystkie na rynku
w kwarantannie — to gorsze niż pusta zakładka.

---

# E. STRONA

**E1. ODRZUCONE** — zdejmowanie rynków przy rozjeździe deklaracji > 5 pp.
Spójne z C3: rozjazd jest informacją o błędzie modelu, nie powodem do ukrycia.

**E2. ODRZUCONE** — trafienia zamiast ROI na wierzchu. Zostaje jak jest.

**E3. PRZYJĘTE** — dowód historyczny na karcie. Zamiast „szansa 88%, przewaga
+9 pp" → **„nie przekroczyła tej linii w 9 z 10 ostatnich meczów, w tym 4 z 4
na wyjeździe"**. Wzorzec działa w drabinkach — przenieść na karty drużynowe.

**E4. PRZYJĘTE** — pusta zakładka zostaje pusta.

**E5. PRZYJĘTE** — nie pokazujemy tego, czego nie dowozimy. Nie eksponujemy
zwrotu, dopóki nie jest dodatni. Nie pokazujemy kuponów 18–25 z obietnicą
„+68% wartości" (50 kuponów, 5 wygranych, −61,6%). Nie cytujemy „dziennych
+80%" — cały plus to jeden dzień i jeden kupon; log rotuje po 21 dniach
zachowując wygrane, więc bilans jest z założenia zawyżony.

**E6. PRZYJĘTE** — koniec z jednym legiem w wielu kuponach. Dziś jeden zakład
siedzi w **4 z 5** kuponów. Potrzebne: limit ekspozycji na mecz, drużynę i leg;
metryki klastrowane; wspólny stan meczu zamiast iloczynu marginalnych szans
z ręczną karą.

---

# CZĘŚĆ VIII — CO JUŻ WESZŁO 11.08

1. **Sufit wieku historii — 18 miesięcy.** Maska na indeksach, nie na prefiksie
   (sortowanie `recentGames` z feedu nie jest gwarantowane naszym kodem — dziś
   trzyma się w 86 na 86 seriach, ale to obietnica cudzego API). Jedna maska
   obsługuje likelihood, średnią opisową, `kal_tau` i kartę.
   Wynik: mecze w historii kart 1455 → 1179, starsze niż 18 mies. 253 → 0,
   najstarszy 5,8 lat → 1,5 roku. Koszt: 9 legów na 165.
2. **Stempel `ess` i `udzial_priora`** przy każdym typie drużynowym — na karcie
   i w księdze. Świadomie stempel, nie brama.
3. **Nowa linia w logu cyklu** — mediana efektywnej próby i liczba legów
   poniżej progu.
4. **Naprawa odwróconego znaku kalibracji** — `docs/ustalenia-2026-08-11.md`.
   Dotyka B3 i B4.

**Stan testów: 943 zielone.**

---

# CZĘŚĆ IX — PYTANIA OTWARTE I GDZIE SZUKAĆ GAMECHANGERÓW

## 9.1 Konkretne pytania

1. **Czy ESS ≥ 5 to właściwa brama** wejścia rynku do liczenia, i czy
   `pseudo_matches = 4.0` w priorze nie jest za silne przy chudej próbie?
2. **Czy sufit 18 miesięcy nie powinien objąć `lg_mean` i priorów** — dziś
   maskujemy likelihood i opisy, ale norma ligi liczy się ze wszystkiego,
   co przyszło z feedu.
3. **Jak rozwiązać drugi szczebel drabinek**, żeby nie wymienić jednego błędu
   na drugi: obniżyć próg, zmienić definicję karty, czy przebudować rachunek?
4. **Czy „karta gracza" z kilku różnych rynków** tego samego zawodnika
   (strzały + faule wywalczone) to sensowna alternatywa dla drabinki z kilku
   linii jednego rynku? Argument przeciw: brak monotoniczności, trudniejsze
   zależności.
5. **Czy zamrożona lista dnia (C6) nie kłóci się** z zasadą „typ raz pokazany
   zostaje do gwizdka" przy meczach nocnych?
6. **Czy przy zakazie blokowania (C3) da się sensownie chronić klienta** przed
   rynkami, w których nasza liczba ma wagę 0 — czy routing do „value"
   wystarczy?

## 9.2 Gdzie podejrzewamy gamechangery

**(a) Nieużywane pola statshuba.** 44 z 49 pól leżą odłogiem, a pomiar
pokazuje, że dla rożnych — naszego największego rynku — **liczymy gorszym
predyktorem niż mamy dostępny**. `opponentStatistics` (koncesje zmierzone
zamiast przybliżanych) pobieramy i wyrzucamy. To jest największa pojedyncza
rezerwa jakości w projekcie i nie kosztuje ani jednego dodatkowego zapytania.

**(b) Model dostępności zawodnika.** Dziś mamy jedną liczbę (oczekiwane minuty).
Docelowo potrzeba osobno: szansa występu, start/ławka, rozkład minut warunkowy
na występ, rola w drużynie, prawdopodobieństwo zwrotu. Bez tego cała ścieżka
zawodnicza stoi na przybliżeniu.

**(c) Wspólny stan meczu zamiast niezależnych rynków.** Rożne, strzały i kartki
w jednym meczu są skorelowane przez tempo gry. Dziś każdy rynek liczymy osobno,
a korelację zmierzyliśmy tylko dla rożnych. To zawyża sumy meczowe i psuje
kupony.

**(d) Hierarchiczny model siły drużyn.** Zamiast osobnych priorów, mnożników
i banków — jeden model częściowego poolingu drużyna–liga–rynek z ewolucją siły
w czasie.

**(e) Trwała naddyspersja.** Rożne (variance/mean 1,55) i strzały (1,88) są
nad-dyspersyjne, ale gole (0,94) i kartki (0,86) **pod**-dyspersyjne. Jedna
zmiana rozkładu na wszystkie rynki byłaby błędem — trzeba per rynek.

## 9.3 Otwarte usterki spoza planu A–E

1. **Regulator `compute_bias_full` nie odejmuje własnej poprzedniej delty.**
   Uczy się na `p_model` zamrożonym w księdze, a to `p` już zawiera kalibrację
   z chwili publikacji. Objaw: przed naprawą znaku wszystkie duże rynki
   drużynowe siedziały dokładnie na dolnym capie. Obejście: mapa zamrożona.
   **Wymaga przebudowy pętli.**
2. **RLS** — anon czyta `typy_wyniki` (1,58 MB) z diagnostyką i raportem
   uczenia. Naprawa: allowlistowe `meta_public` / `typy_wyniki_public`,
   przełączenie frontendu, **dopiero potem** odebranie anonowi surowych kluczy.
   Migracji 0004 **nie wklejać ponownie w ciemno** — produkcja zachowuje się
   tak, jakby była aktywna.
3. **Endpoint `kupon-pomin`** nie sprawdza roli i ufa wartościom z przeglądarki.
4. **`TERMIN_BRAK_DANYCH_S = 7 dni`**, a dokumentacja w tym samym pliku mówi
   o 48 godzinach.
5. **Rozliczenie nie jest w pełni nieodwracalne** — mechanizm „superzmiany"
   potrafi zmienić rozliczony rekord z przegranej na wygraną.
