# Skąd bierze się luka deklaracji — siedem mechanizmów sprawdzonych po kolei

**Pomiar 2026-08-13**, księga produkcyjna (2045 rozliczeń epoki ligowej)
i żywy feed statshub (1284 obserwacje zawodnik×mecz z walidacją czasową).

Pytanie: model deklaruje ~72% i trafia ~60%. Luka −12 pp trzyma się od
tygodni, mimo trzech warstw naprawczych. **Gdzie dokładnie powstaje.**

---

## Odpowiedź w jednym zdaniu

**Model liczy poprawnie — zawyża selekcja.** Prognoza na wszystkich meczach
jest nieobciążona (bias 1,00), ale typ powstaje tam, gdzie estymata wyszła
wysoko, a wysoka estymata jest średnio zawyżona.

```
wycinek rozkładu λ      n      λ     faktycznie   bias
WSZYSTKIE             212    2,88      2,89       1,00
górne 50%             106    3,52      3,18       1,11
górne 25%              53    3,79      3,36       1,13
górne 10%              21    4,05      3,38       1,20
górne  5%              10    4,25      2,90       1,46
dolne 25%              53    1,65      1,89       0,87   <- myli się w drugą stronę
```

To nie jest usterka w żadnym pojedynczym miejscu. To własność wybierania
maksimum z zaszumionej estymaty — im węższy wycinek góry, tym większe
przeszacowanie. Dolne 25% jest **niedoszacowane**, co wyklucza „model
po prostu zawyża".

⚑ **Dlatego luka jest jednolita w całym produkcie** — nie ma zepsutego rynku:

```
DRUŻYNY     1895 rozliczeń   luka -12,3 pp
ZAWODNICY     56 rozliczeń   luka -12,0 pp
shots        114 rozliczeń   luka -12,5 pp
```

I dlatego kalibracja rynku, korekta strumienia i ściąganie do ceny dawały
po kilka punktów każda: leczą właściwą przyczynę, ale każda od innej strony
i żadna nie zna jej mechanizmu.

---

## Co zostało sprawdzone i ODRZUCONE

Wszystko poniżej zmierzone, nie oszacowane. **Nie wracać do tych tropów bez
nowych danych.**

| hipoteza | werdykt | liczba |
|---|---|---|
| naddyspersja per rynek | odrzucona | wpływ na deklarację **0–2 pp** |
| za słaby prior (ściąganie) | **odwrotnie** | dziś 5,0 ≈ optimum (2–5) |
| zawyżona historia zawodnika | odrzucona | per-90 policzone poprawnie |
| zawyżone minuty | odrzucona | błąd **1,04×** |
| mnożniki kontekstu | odrzucona | iloraz fakt/λ **0,92–1,01** |
| ważenie świeżością (tau) | odrzucona | tau=180 vs bez ważenia: **0,5%** |
| klątwa zwycięzcy globalna | słaba | bias pub 1,06 vs zdjęte 1,03 |

### Naddyspersja — dlaczego nie działa

Policzona **właściwie** (statystyka Pearsona wobec przewidywania, nie surowa
wariancja — ta miesza różnice między zawodnikami z szumem meczowym):

```
team_corners 1,81   team_shots 1,75   shots 2,38   ← grubsze ogony
team_goals   0,83   team_cards 0,69   fouls 0,77   ← węższy rozkład
```

Rozrzut jest realny (0,69–2,38 przy modelu zakładającym 1,00), ale linie stoją
blisko średniej, a dyspersja rusza **ogony**, nie środek. Symulacja NB o tej
samej średniej: `team_corners` +0,0 pp, `team_shots` −1,7 pp, `match_cards`
+0,6 pp. Przy luce −12 pp to nie jest przyczyna.

### Siła ściągania — pomiar odwrócił hipotezę

Walidacja czasowa, 1284 obserwacje, średnia grupy liczona **z innych
zawodników** (inaczej zawodnik ściąga sam siebie):

```
pseudo    Brier all   Brier góra20%   bias góra20%
2           0,1769       0,1974           1,03
5           0,1782       0,1961           0,96   <- DZIŚ
20          0,1885       0,2079           0,85
80          0,2024       0,2326           0,79
```

Dzisiejsze 5,0 jest blisko optimum. **Wzmocnienie priora pogorszyłoby model** —
przy 20 bias spada do 0,85, czyli λ zaczyna być zaniżana.

---

## ⚑ ZNALEZIONA PRZYCZYNA: prior ściągał zawodnika DO NIEGO SAMEGO

`model/counts.py` obiecuje w nagłówku: *„Prior (alpha0, beta0) pochodzi
z grupy porównawczej (pozycja × rola × liga) — empiryczny Bayes: zawodnik
z małą próbą jest »ściągany« do średniej grupy"*.

`build_wc_fast.group_prior_from_context` wpisywała w `mean_per90` **średnią
tego samego zawodnika**. Prior nie ściągał więc do niczego zewnętrznego —
a bez ściągania do populacji wysoka estymata zostaje wysoka. To jest dokładnie
mechanizm klątwy zwycięzcy opisany wyżej, tyle że wprost w kodzie.

Pomiar (1284 obserwacje na rynek, walidacja czasowa, średnia grupy liczona
z **innych** zawodników, ta sama siła `pseudo = 5`, wspólna linia i wspólny
zbiór górny dla obu wariantów):

| rynek | wariant | Brier all | Brier góra 20% | bias góra 20% |
|---|---|---|---|---|
| shots | własna (było) | 0,1784 | 0,2000 | **1,09** |
| | **grupowa** | 0,1782 | **0,1944** | **0,95** |
| sot | własna | 0,1438 | 0,2418 | **1,18** |
| | **grupowa** | 0,1426 | **0,2357** | **0,99** |
| fouls_committed | własna | 0,1801 | 0,2580 | **1,24** |
| | **grupowa** | 0,1758 | **0,2412** | **1,07** |
| tackles | własna | 0,1734 | 0,2608 | **1,16** |
| | **grupowa** | 0,1697 | **0,2404** | **0,98** |

**Prior grupowy wygrywa w każdym rynku i w obu miarach**, a bias na górze
rozkładu — czyli tam, gdzie realnie powstają typy — schodzi praktycznie do
jedności. Wariant mieszany 50/50 wypadał konsekwentnie pośrodku, co
potwierdza, że działa ten mechanizm, a nie przypadek.

⚑ **Pułapka pomiarowa, która złapała pierwszą wersję tego testu:** linia
liczona jako mediana λ **osobno w każdym wariancie** sprawia, że każdy jest
oceniany na innej linii i Briery przestają być porównywalne (wychodziło
0,098 wobec 0,196 dla `shots`, czyli dwukrotna „przewaga" wariantu gorszego).
Linia musi pochodzić z **faktycznych** wartości i być wspólna.

Wdrożone 13.08: `srednie_grupowe()` liczy średnią per-90 każdego rynku raz na
cykl z kompletu trendów, `group_prior_from_context` przyjmuje ją jako grupę
porównawczą. Grupa mniejsza niż `MIN_GRUPY_DO_PRIORU = 8` zawodników wraca do
historii samego zawodnika — lepiej nie ściągać wcale niż do średniej z kilku
przypadkowych osób. Pilnuje `tests/test_prior_grupowy.py` (10 testów).

## Co zostało NAPRAWIONE (2026-08-13)

**Pomyłka jednostek w priorze zawodniczym.** `group_prior_from_context`
wkładała średnią liczbę zdarzeń **na mecz** do pola `mean_per90`, czyli
„na 90 minut". Dla grającego pełne mecze to to samo; dla rotacyjnego prior
był zaniżony proporcjonalnie do brakujących minut.

```
zmierzone na 7 zawodnikach z realnymi typami (po ~40 meczów):
   prior zaniżał o 17%  (0,83)
   waga priora ~14%  ->  do posteriora przechodziło 2,5%
```

⚑ **Naprawione mimo małego efektu i mimo że kierunek jest przeciwny do luki.**
To pomyłka jednostek, nie parametr do strojenia — zostawiona w kodzie
fałszuje każdy następny pomiar priora, a mierzono przy niej już dwa razy.
Pilnuje `tests/test_prior_jednostki.py` (7 testów).

---

## Co z tego wynika na przyszłość

1. **Nie szukać dalej „zepsutego rynku"** — luka jest jednolita, bo ma jedną
   przyczynę wspólną dla wszystkich strumieni.
2. **Nie stroić rozkładu ani priora** — oba zmierzone, oba blisko optimum.
3. Korekta selekcyjna musi działać **na wybranym zbiorze**, nie na całym —
   bo na całym model jest nieobciążony i każda globalna korekta psuje dolną
   połowę rozkładu (ta jest dziś niedoszacowana o 13%).
4. Bias policzony na małej próbce rekordów z zapisaną λ potrafi mylić:
   `shots` wychodził na 2,03 przy 17 rekordach i −12,5 pp przy 114. **Zawsze
   sprawdzać, ile rekordów w ogóle ma `lambda`** (dziś 1144 z 2045).

---

## 7. Ile w ogóle da się przewidzieć — dopisane 13.08

Przy okazji sprawdzania 49 pól statshuba wyszła liczba, która porządkuje
wszystkie pozostałe. **Rożne drużyny są praktycznie nieprzewidywalne**:

```
model                      błąd prognozy (out-of-sample)   poprawa
sama średnia ligi                    2,406
historia rożnych (DZIŚ)              2,398                  +0,3%
samo posiadanie                      2,393                  +0,2%
rożne + posiadanie                   2,389                  +0,4%
```

Cały model rożnych na poziomie drużyny wnosi **0,3% ponad stwierdzenie
„w meczu jest około pięciu rożnych"**. A deklaruje na tym rynku 77% przy
58% trafień — stąd `team_corners` w kwarantannie.

⚑ **To nie jest problem doboru cech.** Sprawdzono 8 kandydatów z banku
i 35 pól zawodniczych; najlepszy obcy predyktor rożnych (`possession`) bije
bazę w korelacji o połowę (0,141 wobec 0,095), a w błędzie prognozy o 0,4%.
Przy tak słabym sygnale korelacja rośnie, a decyzje się nie zmieniają.

**Wniosek dla modelu:** różnica między rynkami nie polega na tym, że jednym
brakuje cech, tylko że jedne da się przewidzieć, a drugich nie:

```
przewidywalność (korelacja historii z następnym meczem)
   shots            0,567     fouls_won        0,481
   sot              0,492     tackles          0,436
   fouls_committed  0,282     rożne drużyny    0,095
```

Model traktuje wszystkie tak samo pewnie. Siła ściągania per rynek
(wdrożona 13.08 dla fauli) jest odpowiedzią na to samo pytanie —
`team_corners` jest naturalnym kolejnym kandydatem, ale wymaga własnego
pomiaru na ścieżce drużynowej, która ma inny prior niż zawodnicza.

## Jak to odtworzyć

Skrypty pomiarowe (jednorazowe, katalog roboczy sesji): dyspersja Pearsona,
kalibracja siły ściągania, test tau, test selekcji po percentylach, rozkład λ
na czynniki, pomiar jednostek priora. Wszystkie czytają księgę i żywy feed,
żaden nic nie zapisuje. Kluczowe filtry: epoka ligowa, `_z_martwej_epoki`
odsiane, `faktyczna` bywa tekstem (`"5:9"` — wynik meczu zamiast liczby
zdarzeń), walidacja zawsze czasowa.
