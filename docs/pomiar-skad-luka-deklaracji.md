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

## Jak to odtworzyć

Skrypty pomiarowe (jednorazowe, katalog roboczy sesji): dyspersja Pearsona,
kalibracja siły ściągania, test tau, test selekcji po percentylach, rozkład λ
na czynniki, pomiar jednostek priora. Wszystkie czytają księgę i żywy feed,
żaden nic nie zapisuje. Kluczowe filtry: epoka ligowa, `_z_martwej_epoki`
odsiane, `faktyczna` bywa tekstem (`"5:9"` — wynik meczu zamiast liczby
zdarzeń), walidacja zawsze czasowa.
