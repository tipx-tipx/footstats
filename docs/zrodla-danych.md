# Źródła danych — co mamy, czego nie używamy, czego brakuje (2026-08-07)

Pytanie właściciela: „czy statshub daje wszystkie statystyki, czy trzeba szukać
innego źródła — darmowego albo płatnego?".

Krótka odpowiedź: **statshub daje 49 pól na mecz, a my używamy pięciu.** Zanim
zaczniemy płacić za dane, warto sięgnąć po to, co już mamy w ręku — bo dla
naszego największego rynku nieużywane pola przewidują **lepiej** niż te, którymi
liczymy dzisiaj.

## 1. Co dostajemy, a czego nie czytamy

Sonda na żywym feedzie (drużyna 3205, 40 meczów historii): **49 różnych pól**
w każdym meczu. Konsumujemy pięć: `totalShotsOnGoal`, `shotsOnGoal`, `cards`,
`cornerKicks`, `fouls`.

Wśród nieużywanych są m.in.: `expectedGoals` (xG), `totalShotsInsideBox`,
`totalShotsOutsideBox`, `touchesInOppBox`, `finalThirdEntries`,
`bigChanceCreated/Missed/Scored`, `ballPossession`, `pass_accuracy`,
`accurateCross`, `throwIns`, `goalKicks`, `freeKicks`, `totalTackle`,
`interceptionWon`, `duelWonPercent`, `groundDuelsPercentage`,
`aerialDuelsPercentage`, `dispossessed`, `totalClearance`, `offsides`,
`goalsPrevented`, oraz `yellowCards` i `redCards` osobno (my mamy tylko sumę).

**Do tego `opponentStatistics`** — te same ~40 pól po stronie rywala w każdym
meczu historii, czyli **koncesje zmierzone zamiast przybliżanych**. Sonda:
wypełnione w 40/40 meczów (Gimnasia, Santos) i 16/21 (Ljungskile). Kod pobiera
to pole i **nigdzie go nie czyta** — pada wyłącznie w docstringu
(`sources/statshub.py:492-496`).

## 2. Test: czy nieużywane pola przewidują lepiej

536 par „historia 10 meczów → następny mecz", 19 drużyn z bieżącej listy.
Korelacja średniej z 10 meczów z wynikiem meczu następnego (★ = pole, którego
używamy dzisiaj).

**Rożne drużyny — nasz predyktor jest DOPIERO SZÓSTY:**

| predyktor | korelacja |
|---|---:|
| strzały z pola karnego | **+0,145** |
| dotknięcia w polu rywala | **+0,126** |
| ★ strzały | +0,123 |
| wznowienia bramkarza | −0,102 |
| xG | +0,097 |
| celność podań | +0,089 |
| ★ **rożne** (tym liczymy) | **+0,082** |

Historia rożnych przewiduje rożne **gorzej** niż strzały z pola karnego. To
tłumaczy pomiar z `czy-model-mysli.md`: na `team_corners` (577 rozliczeń,
największy rynek) nasza liczba nie wnosi nad kurs **nic** (AUC 0,499).

**Kartki — nasz predyktor jest najlepszy, ale nie jedyny:**
kartki +0,265 ★, dotknięcia w polu rywala −0,209, faule +0,206 ★,
wrzuty +0,203, celność podań −0,196, pojedynki powietrzne +0,130.

**Strzały:** strzały +0,217 ★, celność podań +0,190, wznowienia −0,183.

**Faule:** faule +0,307 ★, kartki +0,256 ★, wrzuty +0,207, wykreowane
okazje −0,201.

Wniosek: dla kartek, strzałów i fauli liczymy właściwym polem, ale zostawiamy na
stole **niezależne sygnały** (wrzuty, celność podań, pojedynki — wszystkie mówią
o stylu gry). Dla rożnych liczymy gorszym polem, niż mamy dostępne.

## 3. Największe dziury w danych — nie tam, gdzie się wydaje

1. **Kontuzje, zmęczenie, rotacja — zero danych.** Pole
   `injured_or_suspended` istnieje (`engine.py:83`) i jest konsumowane przez
   model minut (`model/minutes.py:65,80`), ale w produkcji **nikt nigdy go nie
   ustawia** — jedyne przypisanie `True` jest w teście. Rotowire ma sekcję
   kontuzji i świadomie ją odcinamy (`sources/rotowire.py:8-10`). Odstęp między
   meczami, podróż i strefa czasowa nie występują w kodzie w ogóle. Dotyczy
   wszystkich rynków zawodniczych, bo wchodzi w oczekiwane minuty.
2. **Kontekst rywala nieobecny albo dziedziczony.** Ścieżka `performance`
   (jedyna dla Ekstraklasy, kwalifikacji i części Ameryki Płd.) zwraca
   `opponent_average=None`, więc czynnik rywala jest neutralny. Osiem rynków
   dziedziczy koncesje po „rynku-rodzicu" z wagą 0,5. A dane są w ręku —
   patrz `opponentStatistics` wyżej.
3. **Korelacja między drużynami zmierzona tylko dla rożnych** (ρ = −0,127).
   Osiem z dziesięciu rynków `match_*` / `wiecej_*` jedzie na założeniu
   niezależności (ρ = 0), co zawyża sumy i zaniża „kto więcej". Skrypt
   `scripts/zmierz_korelacje.py` już istnieje — brakuje przebiegu.

## 4. Czego statshub NIE daje (i skąd to bierzemy)

* **Sędzia** — z 365Scores. Profil ma sens dla ~10% arbitrów (444 w bazie,
  210 z jednym meczem).
* **Faule drużynowe w feedzie propsów** — brak; idą z `performance` i z banku
  stylu (pokrycie 71,4%, najsłabsze ze wszystkich rynków z banku).
* **Kursy** — wyłącznie Superbet. Betclic świadomie poza modelem, STS wyłączony
  (blokuje adresy serwerowni).
* **Flaga „strzał spoza pola" w feedzie kłamie** (True dla 35 z 35 strzałów) —
  liczymy z geometrii.
* **Feed propsów jest lustrem oferty bukmacherów UK** — Ekstraklasy nie kwotuje
  w ogóle, na kwalifikacjach i pucharach stoi pusty (zmierzone 03.08: 25 z 26
  meczów bez ani jednego propsa).

## 5. Płatne alternatywy — ceny i pułapki (research 07.08)

| dostawca | koszt | co daje | uwagi |
|---|---|---|---|
| **API-Football Pro** | **$19/mies.** (~70 zł) | statystyki zawodnicze per mecz, kontuzje (od IV.2021), składy | licencja SŁABA: „nie zapewniamy licencji na publikację danych", osobna wzmianka o platformach bukmacherskich; brak zwrotów, brak zejścia na niższy plan |
| **SportMonks Growth** | €99/mies. (€79 rocznie) | 30 lig, **Advanced Player Stats** | jedyny, który wprost pozwala przechowywać dane i zarabiać na produktach pochodnych; kursy i xG to PŁATNE DODATKI; 14 dni triala bez karty |
| SportMonks Starter | €29 + €4/liga | 5 lig | tańsze przy 9–12 ligach, ale policzyć samemu |
| Goalserve | $200/mies. | jako jedyny w tej półce daje **przewidywany skład** (60 min przed) | brak Ligi Konferencji i kwalifikacji; zera wracają jako `""`; regulamin bez klauzul o danych |
| TheStatsAPI | $50/mies. | najlepsza dokumentacja, xG, połówki | **ODPADA**: regulamin zabrania przechowywania danych, a my potrzebujemy bazy na 2 sezony |
| Highlightly | $9,49/mies. | deklaruje 950+ lig | brak publicznej listy lig — taniej przetestować niż badać |

**Pułapka nazewnicza w SportMonks:** „Standard Player Stats" to tylko gole,
kartki i zmiany. To, czego potrzebujemy (strzały, faule, pojedynki, odbiory),
nazywa się **Advanced Player Stats** i ma je 125 z 2 335 lig. Nasze ligi są
w tej grupie — Brazylia A (#648) i B (#651), Argentyna Liga Profesional (#636),
Ekstraklasa (#453), Eliteserien (#444), Allsvenskan (#573), Superliga (#271),
MLS (#779), LM (#2), LE (#5), Konferencji (#2286).

**Domknięta dziura, której nie da się kupić:** argentyńska Primera Nacional
(#645). Goalserve nie ma, API-Football nie ma, SportMonks daje tylko Standard.
Ta liga musi jechać na samych danych drużynowych albo wypaść.

**Test rozstrzygający — pół godziny, zero złotówek** (zrobić PRZED zakupem):
1. darmowy klucz API-Football (500 zapytań wystarczy),
2. dla każdej z naszych rozgrywek `GET /leagues?id={id}` i sprawdzić
   `coverage.fixtures.statistics_players` **osobno dla każdego sezonu**,
3. dla jednego rozegranego meczu z każdej ligi `GET /fixtures/players?fixture={id}`
   i **policzyć, ile wartości nie jest `null`**.

Punkt 3 jest ważniejszy, niż wygląda: w ich własnym przykładzie z dokumentacji
`offsides`, `tackles.total` i `duels` wracają jako `null`. Obecność pola
w schemacie to nie to samo co wypełnienie. Ten test rozstrzyga między $19
a €99 miesięcznie.

Osobno sprawdzić empirycznie **kwalifikacje pucharów** — u obu dostawców nie są
osobnymi rozgrywkami, tylko rundami wewnątrz identyfikatorów 2 / 5 / 2286,
a znaczniki pokrycia stoją na poziomie całych rozgrywek. Trzeba wziąć konkretny
mecz kwalifikacyjny z lipca lub sierpnia i zobaczyć, czy statystyki przyszły.

## 6. Rekomendacja kolejności

1. **Zacząć czytać `opponentStatistics`** — koncesje mierzone zamiast
   przybliżanych, dla każdej drużyny i każdego rynku. Koszt: sam kod, dane już
   płyną. To zamyka dziurę nr 2 z listy wyżej.
2. **Dołożyć nowe pola jako predyktory**, zaczynając od rożnych (strzały z pola
   karnego, dotknięcia w polu rywala) — czyli tam, gdzie mamy najwięcej typów
   i zero przewagi nad kursem.
3. **Odpalić pomiar korelacji** dla pozostałych czterech rynków.
4. **Kontuzje** — najtańsze źródło to sekcja, którą już pobieramy z Rotowire
   i wyrzucamy; szersze pokrycie wymaga płatnego dostawcy.
