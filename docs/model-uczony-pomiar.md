# Model uczony kontra dzisiejsza maszyneria — pomiar 2026-08-17

Zadanie właściciela: „chcę prosty system z prostym modelem, dobrze nauczonym —
nie wiem, czy on się w ogóle uczy". Ten dokument jest odpowiedzią zmierzoną,
nie opinią.

## 1. Dlaczego model się nie uczył

Nie z powodu algorytmu. **Nie miał pamięci.**

| co | ile | czego dotyczy |
|---|---|---|
| `trend_lib` | 176 718 obserwacji | **tylko zawodnicy** (shots, fouls, tackles, sot) |
| `druzyny_profil` | 289 drużyn | **tylko agregaty** („notuje 6,8 / dopuszcza 2,4") |
| `typy_log` | 6 452 rozliczenia | przesunięcia wyniku |

Rynki drużynowe to 93% produkcji, a ich historia meczowa była pobierana
w każdym cyklu, używana i wyrzucana. Ze średniej z 40 meczów nie da się
nauczyć modelu — średnia nie wie, przeciw komu, u siebie czy na wyjeździe
i kiedy. Dlatego uczyło się **dziesięć warstw korekt na wyjściu** formuły,
a sam rachunek (λ ze średnich × pięć ręcznie wpisanych mnożników) nie miał
ani jednego parametru z danych.

To tłumaczy też, dlaczego strumień zawodniczy się **poprawiał**, a drużynowy
**psuł**: zawodnicy mieli bank, drużyny nie miały nic.

## 2. Magazyn (wdrożony, `4d45bb7`)

```
289 drużyn, 11 036 meczów, 143 665 obserwacji statystyk
historia 2020-08-08 → 2026-08-17, pokrycie pól 78–91%
```

Rekord = jeden mecz jednej drużyny: 15 pól własnych, te same 15 po stronie
rywala (koncesje zmierzone, nie przybliżane), wynik, liga, dom/wyjazd, czas.

Dwie rzeczy sprawdzone przed ustaleniem formatu:
1. `statistics` u źródła należy do drużyny **pytanej**, nie do gospodarza —
   44 z 45 pól `statistics(A)` = `opponentStatistics(B)` na meczu zapytanym
   z obu stron. Gdyby odwrotnie, cały zbiór miałby zamienione strony przy
   meczach wyjazdowych i nie dałoby się tego rozpoznać po fakcie.
2. Brak pola nie zapisuje się jako zero.

## 3. Zbiór treningowy

54 205 wierszy (8,7–9,9 tys. na rynek). Cel: liczba zdarzeń w tym meczu.
Cechy **wyłącznie z meczów wcześniejszych**: własne średnie w oknach 3/6/12,
średnia u siebie/na wyjeździe, koncesje rywala (6/12), średnia ligi,
dom/wyjazd, statystyki powiązane (posiadanie, dośrodkowania, wejścia w tercję,
strzały z pola i z dystansu, spalone, odbiory, xG) i długość historii.

Model: regresja Poissona, IRLS z karą L2, `numpy` + `scipy` (bez nowych
zależności — `sklearn` nie jest i nie musi być w produkcji).

## 4. Model kontra uproszczona formuła (test czasowy 70/30)

| rynek | dewiancja: dziś → model | Brier: dziś → model |
|---|---|---|
| team_cards | 1,117 → 1,053 | 0,2263 → 0,2185 |
| team_corners | 1,793 → 1,642 | 0,2454 → 0,2296 |
| team_fouls | 1,300 → 1,192 | 0,2431 → 0,2283 |
| team_goals | 1,355 → 1,251 | 0,2475 → 0,2325 |
| team_shots | 2,145 → 1,985 | 0,2461 → 0,2306 |
| team_sot | 1,447 → 1,358 | 0,2440 → 0,2332 |
| **średnio** | **1,526 → 1,413 (−7,4%)** | **0,2421 → 0,2288 (−5,5%)** |

Lepszy na **każdym** rynku, bez wyjątku.

## 5. ⚑ TEST DEFINITYWNY: model kontra to, co poszło na stronę

4398 rozliczonych typów drużynowych z meczów po 24.07. Model trenowany
wyłącznie na danych starszych; `p_model` z księgi to liczba po CAŁEJ dzisiejszej
maszynerii (pięć mnożników, kalibracja rynku, korekta strumienia, korekta
strony, prior grupowy).

```
                       deklaruje   weszło    luka       Brier    log-loss
DZIŚ (produkcja)         65,1%     50,6%   −14,4 pp    0,2434    0,6943
MODEL UCZONY             51,4%     50,6%    −0,7 pp    0,2291    0,6572
```

Per rynek luka spada z −12…−15 pp do −5…+1 pp (rożne −15,5 → −0,9;
gole −13,9 → −0,5; kartki −14,5 → +0,5; celne −11,9 → +0,9;
faule −11,9 → +1,2; strzały −15,1 → −4,8).

**To jest ta sama luka, którą dziesięć warstw korekt ścigało tygodniami.**

## 6. Czy uczciwe liczby pozwalają lepiej WYBIERAĆ

Ten sam zbiór 4398 typów, filtrowany raz dzisiejszymi liczbami, raz liczbami
modelu. Margines = trafność − 1/kurs (dodatni = bijemy cenę).

| filtr | n | trafia | margines | po podatku |
|---|---|---|---|---|
| wszystko, co przeszło stare bramy | 4398 | 50,6% | −3,0 pp | −10,3 pp |
| dzisiejsza szansa ≥ 70% | 1743 | 68,2% | −3,1 pp | −12,8 pp |
| dzisiejsza wartość ≥ 20% | 2217 | 40,1% | −2,7 pp | −8,6 pp |
| **szansa modelu ≥ 60% i kurs ≥ 1,50** | **549** | **59,9%** | **+1,2 pp** | **−6,9 pp** |
| wartość modelu ≥ 5% i szansa ≥ 55% | 911 | 63,9% | −0,3 pp | −9,0 pp |
| wartość modelu ≥ 5% | 1253 | 53,9% | −2,0 pp | −9,6 pp |

⚑ Na dzisiejszych liczbach **żaden** filtr nie schodzi poniżej −2,7 pp — bo
filtruje się po liczbie zawyżonej o 14 pp. Na liczbach modelu ten sam pomysł
daje pierwszy dodatni margines w historii projektu.

## 7. Czego ten pomiar NIE mówi

* **+1,2 pp jest w szumie** (549 typów, błąd standardowy 2,1 pp). Kierunek jest
  spójny we wszystkich wariantach, ale to nie jest jeszcze pewnik.
* **Po podatku wciąż −6,9 pp.** To najlepszy zmierzony wynik (poprzedni −8,3),
  ale do zysku netto brakuje 7 pp. Przy podatku 12% od stawki próg trafień to
  `1 / (0,88 × kurs)` — przy kursie 1,50 aż 75,8%.
* **Podaż spadnie** z ~62 do ~21 typów na dobę. Model deklaruje średnio 51%
  zamiast 65%, więc typów „powyżej 60% szansy" jest po prostu mniej.
* Kursy historyczne mamy tylko dla typów, które przeszły stare bramy — więc
  selekcji na pełnej ofercie ten pomiar nie obejmuje.
* Model nie widzi kursu i to jest decyzja właściciela (17.08): tylko tak da się
  uczciwie mierzyć, czy bijemy cenę.

## 8. Kolejność wdrożenia

1. Magazyn — **zrobione** (`4d45bb7`), job codzienny 6:20.
2. Moduł uczenia w produkcji: `zbiór → Poisson → wagi do Supabase`, trening
   osobnym jobem raz na dobę, cykl tylko mnoży macierze.
3. Nowy model liczy **obok** starego, oba stemplowane w księdze. Porównanie na
   tych samych typach, paired Brierem.
4. Warstwy schodzą po jednej, każda wtedy, gdy pomiar pokaże, że model bez niej
   jest lepszy niż stary z nią (decyzja właściciela 17.08).
5. Widełki przeliczone na liczbach modelu — osobne dla półki „wysoka szansa"
   i „value", bo to dwie różne obietnice.
6. Zawodnicy i drabinki przechodzą na ten sam silnik (decyzja właściciela).

---

# 9. WIDEŁKI NA LICZBACH MODELU — pomiar 2026-08-17, część 2

Cel produktu ustalony przez właściciela: **trafność w obu zakładkach**
(„wysoka szansa" i „wyższe kursy"). Podatek i margines nad ceną zostają
miarami jakości modelu, ale nie decydują o widełkach. Wprost:
„zależy nam na trafialności typów, zarówno wysoka szansa jak i value"
oraz „chcę wyższe kursy realnie przeanalizowane przez model, bez zbędnych
widełek".

## Czy sortowanie po szansie modelu podnosi trafność w pasmie kursu

| pasmo kursu | n | trafność | top 50% modelu | top 25% modelu | top 25% DZIŚ |
|---|---|---|---|---|---|
| 1,20–1,50 | 1163 | 71,7% | 74,9% | 73,8% | 76,2% |
| 1,50–1,80 | 825 | 60,8% | 64,1% | 66,5% | 65,5% |
| 1,80–2,20 | 865 | 46,5% | 50,2% | 50,9% | 48,6% |
| 2,20–3,00 | 739 | 36,4% | 33,6% | **31,0%** | 41,3% |
| 3,00+ | 800 | 25,5% | 25,8% | 26,0% | 25,0% |

## ⚑ GDZIE MODEL PRZESTAJE PORZĄDKOWAĆ: KURS 2,20

Wąskie pasma, górna tercja szansy modelu kontra dolna:

| pasmo | n | średnia | górna tercja | dolna tercja | różnica |
|---|---|---|---|---|---|
| 2,00–2,20 | 357 | 41,2% | 42,9% | 38,7% | **+4,2 pp** |
| 2,20–2,40 | 235 | 38,7% | 38,5% | 41,0% | −2,6 pp |
| 2,40–2,80 | 360 | 37,8% | 30,8% | 46,7% | **−15,8 pp** |
| 2,80–3,50 | 421 | 30,6% | 28,6% | 34,3% | −5,7 pp |
| 3,50+ | 523 | 22,4% | 21,3% | 21,8% | −0,6 pp |

**Powyżej 2,20 nasze typy są ANTY-SYGNAŁEM.** Przy 2,40–2,80 typy z najwyższą
szansą modelu trafiają 30,8%, a z najniższą 46,7% — lepiej byłoby grać
odwrotnie. To nie jest widełka wymyślona przy biurku: to granica, za którą
model sam pokazuje brak pokrycia.

## Proponowane widełki: cztery liczby, żadnych progów wartości

```
PÓŁKA „WYSOKA SZANSA"   kurs 1,20–1,80   15 typów/dobę   trafność ~73%
PÓŁKA „WYŻSZE KURSY"    kurs 1,80–2,20    6 typów/dobę   trafność ~53%
```

Kolejność w obu: szansa modelu. Bez wartości, bez EV, bez progów szansy.

Zmierzone (dane jak wyżej, 22 dni):

| zakres | limit | n | średni kurs | trafność | margines |
|---|---|---|---|---|---|
| 1,20–1,80 | 10/d | 222 | 1,28 | 72,5% | −5,8 pp |
| 1,20–1,80 | 15/d | 333 | 1,29 | 73,3% | −4,8 pp |
| 1,20–1,80 | 20/d | 444 | 1,30 | 74,1% | −3,5 pp |
| 1,80–2,20 | 4/d | 88 | 1,93 | 53,4% | +1,5 pp |
| 1,80–2,20 | 6/d | 133 | 1,93 | 53,4% | +1,3 pp |
| 1,80–2,20 | 12/d | 266 | 1,93 | 51,5% | −0,3 pp |

## ⚑ DO ZBADANIA: model jest ZBYT PEWNY na samej górze rozkładu

Na półce wysokiej szansy **top 6 typów trafia 71,4%, a top 20 — 74,1%**.
Sortowanie po szansie powinno dawać odwrotnie. Wygląda na nieliniowość przy
p → 0,9 (model za pewny przy skrajnych deklaracjach) i prawdopodobnie da się
to naprawić jedną kalibracją izotoniczną — ale trzeba to najpierw zmierzyć,
a nie założyć. To samo zjawisko może stać za odwróceniem powyżej kursu 2,20.
