# Dwie warstwy uczenia POGARSZAJĄ prognozę — zmierzone na 1159 rekordach

**16.08.2026.** Znalezione przy szukaniu odpowiedzi na pytanie właściciela
„czemu nasze typy nie wchodzą". To jest odkrycie klasy naprawy odwróconego
znaku z 11.08 — i tym razem widać je wprost, bez rekonstrukcji, bo stempel
`rachunek` niesie **naszą własną liczbę przed i po warstwach**.

---

# 1. WYNIK

Na 1159 rozliczonych rekordach bieżącej epoki, które mają pełny stempel
(`p_over_raw` → `p_over_final`):

```
wariant                        deklaruje   trafia    luka     Brier   logloss
PRZED warstwami (surowe)           56,9%    49,7%    -7,2    0,2389    0,6781
PO warstwach (to publikujemy)      62,9%    49,7%   -13,2    0,2485    0,6963
```

**Kalibracja rynku i korekta strumienia razem:**
* podnoszą deklarowaną szansę o **+6,0 pp**,
* pogłębiają lukę z −7,2 do **−13,2 pp**,
* pogarszają Briera o **4,0%** i log-loss o **2,7%**.

To są warstwy, których jedynym zadaniem jest **leczyć przeszacowanie**.
Robią dokładnie odwrotnie.

---

# 2. TEST STABILNOŚCI — przeszedł (w odróżnieniu od trzech dzisiejszych rekomendacji)

```
próba          n   trafia   luka PRZED   luka PO   Brier PRZED   Brier PO
I połowa     579    47,3%        -9,8     -16,0        0,2569     0,2614
II połowa    580    52,1%        -4,6     -10,4        0,2208     0,2357
CAŁOŚĆ      1159    49,7%        -7,2     -13,2        0,2389     0,2485
```

Kierunek ten sam w obu połowach. Do tego **wszystkie dziewięć rynków** psuje
się osobno:

```
rynek              n     Brier PRZED -> PO
match_corners    194     0,2175 -> 0,2315   +6,5%
team_cards       134     0,2392 -> 0,2589   +8,2%
team_shots       111     0,2734 -> 0,2943   +7,6%
match_shots       45     0,2865 -> 0,3036   +6,0%
match_cards      111     0,2106 -> 0,2148   +2,0%
team_fouls        58     0,2506 -> 0,2542   +1,4%
team_sot         105     0,2579 -> 0,2607   +1,1%
team_corners     236     0,2322 -> 0,2332   +0,5%
match_sot         70     0,2313 -> 0,2317   +0,2%
```

Ani jeden rynek nie zyskuje. To wyklucza przypadek.

---

# 3. CO WIDAĆ W SAMYCH DELTACH

Na tych samych rekordach:

```
kalibracja rynku:    średnia +0,283 logita   (794 z 1151 dodatnich)
korekta strumienia:  średnia -0,393 logita   (158 z 1178 dodatnich)
p_over:  46,6% surowo  ->  43,9% po warstwach   (-2,8 pp)
strony:  772 „poniżej"  /  387 „powyżej"
```

Dwie warstwy ciągną `p_over` w **przeciwne strony** — jedna podnosi o 0,28,
druga obniża o 0,39. To jest podpis oscylacji: obie uczą się z tej samej
księgi, ale druga widzi już efekt pierwszej.

⚑ **Naprawa orientacji z 11.08 (`w_orientacji_over`) JEST wdrożona i działa** —
sprawdzone w kodzie, obie warstwy jej używają. To NIE jest powrót tamtego
błędu. To jest problem KIERUNKU i WZAJEMNEGO ZNOSZENIA SIĘ warstw, nie
orientacji strony.

⚑ Znany, udokumentowany mechanizm, który to tłumaczy: `compute_bias_full`
**nie odejmuje własnej poprzedniej delty** — uczy się na `p_model`, które już
zawiera korektę. Obejściem była zamrożona mapa (`KALIBRACJA_ZAMROZONA`), ale
zamrożono ją **z tymi deltami w środku**, więc obejście utrwaliło błąd
zamiast go usunąć.

---

# 4. CO TO ZNACZY DLA TYPÓW

Zawyżone `p` nie jest tylko kosmetyką na karcie. **Wartość zakładu liczy się
z `p`** (`ev = p × kurs − 1`), a selekcja i kolejność listy stoją na wartości
i na `moc_listy = p × √kurs`. Skoro `p` jest zawyżone o 6 pp:

* typy dostają „wartość", której nie mają,
* na górę listy trafiają te, którym model najbardziej dosypał,
* brama okna zgody porównuje z kursem liczbę już przesuniętą.

To jest ta sama klątwa zwycięzcy, którą widać w pomiarze „luka to selekcja,
nie model" — **tylko że tutaj mamy jej źródło policzone co do punktu
procentowego**.

---

# 5. CO ZROBIĆ

## Krok 1 — natychmiastowy, odwracalny

**Zneutralizować obie warstwy** (delta = 0) i zostawić surowy rachunek.
Spodziewany efekt, wprost z tabeli wyżej:

```
luka        -13,2 pp  ->  -7,2 pp
Brier       0,2485    ->  0,2389   (-4,0%)
deklaracja  62,9%     ->  56,9%
```

Karty pokażą liczby **niższe o ~6 pp** i to będzie poprawne — dokładnie jak
przy ściąganiu do ceny 12.08. Podaż typów spadnie, bo część przestanie mieć
dodatnią wartość: to jest cel, nie skutek uboczny.

---

# ⚑⚑⚑ DIAGNOZA (dopisane 16.08 wieczorem) — PRZYCZYNA JEST W ARCHITEKTURZE

Właściciel wybrał „najpierw diagnoza". Zrobiona — i **obala pierwszą hipotezę
z tego dokumentu**. Warstwy nie są policzone odwrotnie. Problem jest głębszy.

## 1. Obie strony zakładu przeszacowują

Na surowym `p` (przed warstwami), 1197 rekordów drużynowych ze stemplem:

```
strona      n     deklaruje   trafia     luka
poniżej   813       57,9%     54,5%     -3,5 pp
powyżej   384       54,8%     40,1%    -14,7 pp
```

Delta potrzebna, żeby każdą stronę sprowadzić do prawdy:

```
poniżej   -0,165
powyżej   -0,654
```

## 2. Jedna delta na `p_over` NIE MOŻE tego naprawić — to TRANSFER, nie redukcja

Obie warstwy nakładają deltę na `p_over`, a „poniżej" powstaje jako
`1 − p_over`. Więc **ściągnięcie `p_over` automatycznie PODNOSI `p` typu
„poniżej"**. Jedną liczbą nie da się obniżyć obu stron naraz — można tylko
przesuwać masę z jednej na drugą.

Nasza korekta strumienia (−0,4 na `p_over`) robi dokładnie to:

```
„powyżej":  p_over ↓  ->  p typu ↓   ✓ w dobrą stronę (potrzeba -0,654)
„poniżej":  p_over ↓  ->  p typu ↑   ✗ w złą (potrzeba -0,165, dostaje +0,4)
```

I to widać w liczbach: „poniżej" PRZED −4,1 pp → PO −10,7 pp. Pogorszenie
o 6,6 pp, czyli dokładnie tyle, ile wynosi nałożona delta. **Ponieważ 2/3
publikowanych typów to „poniżej", wypadkowa jest szkodliwa** — mimo że sama
korekta jest w orientacji `p_over` policzona POPRAWNIE.

⚑ Sprawdzone i **odrzucone** po drodze (nie wracać):
* orientacja `w_orientacji_over` — wdrożona i używana przez obie warstwy;
* naddyspersja rozkładu — test out-of-sample (φ z I połowy na II) dał
  poprawę Briera 0,2411 → 0,2396, czyli w granicach szumu;
* `_p_surowe` odejmuje tylko jedną z dwóch delt — to PRAWDA i było
  naprawione, ale naprawa **wzmacnia** korektę (−0,382 → −0,514), więc
  bez zmiany architektury POGŁĘBIA problem „poniżej". Zmiana wycofana.

## 3. Właściwa naprawa: korekta per (RYNEK, STRONA), nałożona na `p` TYPU

To jest ten sam wniosek, który wyszedł już przy kwarantannach: **jednostką
decyzji jest (rynek, strona), nie sam rynek**. Warstwa uczenia musi:

* uczyć się na `p` WYBRANEGO ZAKŁADU (jak `szansa_pokazywana`), nie na
  `p_over`;
* mieć osobną deltę dla „powyżej" i „poniżej" w każdym rynku;
* być uczona na `rachunek.p_over_raw`, czyli liczbie sprzed wszystkich warstw
  (mamy ją w stemplu od 12.08, a od dziś także przy typach zawodniczych
  i pomiarowych).

Spodziewany efekt: luka „powyżej" −14,7 → ~0, „poniżej" −3,5 → ~0. Deklaracja
spadnie z 62,9% do ~50%, ale **będzie prawdziwa** — a wartość zakładu i
kolejność listy przestaną stać na liczbie zawyżonej o 6 pp.

## Krok 2 — dopiero potem diagnoza

Dlaczego kalibracja wychodzi dodatnia, skoro model przeszacowuje. Kandydaci:
uczenie na `p_model` z własną deltą w środku, zamrożona mapa z 12.08,
wzajemne znoszenie się z korektą strumienia. **Nie blokować kroku 1
diagnozą** — warstwa, która mierzalnie szkodzi, ma być wyłączona, zanim
zrozumiemy, dlaczego.

## Krok 3 — odbudowa

Jedna warstwa zamiast dwóch, uczona na `p_over_raw` (mamy go teraz w stemplu
przy każdym typie), z twardym testem out-of-sample przed włączeniem:
**φ z pierwszej połowy próby, sprawdzone na drugiej**. Ten test dziś
przeszedł tylko ten jeden wniosek — trzy inne obalił.

---

# 6. CZEGO TA ANALIZA **NIE** MÓWI

* **Nie mówi, że model jest dobry.** Surowy rachunek też przeszacowuje
  o 7,2 pp. Warstwy dokładają drugie tyle.
* **Nie mówi, że trafność wzrośnie.** Trafność zależy głównie od kursu
  (`docs/dlaczego-typy-nie-wchodza.md`). To poprawia **kalibrację i selekcję**,
  czyli sprawia, że wybieramy lepsze typy — nie że te same typy zaczną wchodzić.
* **Nie dotyczy `szansa_pokazywana` ani ściągania do ceny** — to warstwy
  nakładane PO wyborze strony, mierzone osobno.
