# Dlaczego nasze typy nie wchodzą i co trzeba zrobić, żeby wchodziły

**16.08.2026.** Pytanie właściciela postawione wprost: *„robimy chujowe typy,
skuteczność wszędzie jest koło 50%, celem jest 75%, bo inaczej to nie jest
narzędzie ani model analityczny"*. Odpowiedź policzona na **4907 rozliczeniach
bieżącej epoki** (z typami pomiarowymi, bo pytanie brzmi „co model UMIE", a nie
„co przepuściły bramy").

---

# 1. ⚑⚑⚑ 75% TRAFIEŃ JEST OSIĄGALNE OD RĘKI — I NIE WYMAGA POPRAWY MODELU

**Trafność to prawie wyłącznie wybór kursu.** Nasze dane:

```
kurs            n     deklaruje   TRAFIA     luka      ROI
1,00–1,25     418       90,9%     80,6%    -10,2     -2,2%
1,25–1,45     864       84,3%     72,2%    -12,1     -3,7%
1,45–1,65     625       74,5%     63,8%    -10,7     -1,4%
1,65–1,85     586       67,4%     53,4%    -14,0     -7,4%
1,85–2,10     627       60,6%     46,7%    -13,8     -9,1%
2,10+        1787       47,4%     31,3%    -16,0     -8,9%
```

Progi wprost:

```
kurs maks.    typów   /dobę   TRAFIA     ROI
1,30            709    23,6    78,8%   -2,4%
1,40           1141    38,0    76,2%   -2,7%
1,50           1477    49,2    73,4%   -3,7%
1,75           2259    75,3    69,1%   -2,7%
```

**Publikując wyłącznie typy z kursem ≤ 1,40 mamy 76% trafień i 38 typów na
dobę — od jutra, bez jednej linijki w modelu.** Dziś średnia to ~56%, bo
publikujemy też pasmo 1,85–2,10, gdzie trafiamy 46,7%.

⚑ **To jest cała odpowiedź na „czemu mamy 50%".** Nie dlatego, że model jest
zły — dlatego, że gramy kursy, przy których 50% to norma. Przy kursie 2,00
trafienie 50% jest DOKŁADNIE wynikiem przeciętnym.

---

# 2. ⚑⚑⚑ ALE TRAFNOŚĆ TO NIE TO SAMO CO ZYSK — I TU JEST HACZYK

Przy kursie 1,30 do wyjścia na zero trzeba **76,9%** trafień (1 / 1,30).
Trafiamy 78,8% — czyli teoretycznie +2%. A wychodzi **−2,4%**, bo:

* część typów ma kurs niższy niż 1,30 przy tej samej trafności,
* dochodzi podatek 12% od stawki.

```
próg p_model   typów   /dobę   TRAFIA      ROI    bilans 10 zł
75%             1597    53,2    72,4%    -2,0%      -318 zł
80%             1213    40,4    75,1%    -1,7%      -202 zł
85%              801    26,7    77,7%    -1,1%       -87 zł
90%              391    13,0    77,2%    -2,8%      -108 zł
```

**Żaden próg nie daje zysku.** Im wyżej podnosimy poprzeczkę, tym mniej
tracimy — ale zawsze tracimy. To nie jest przypadek ani pech.

---

# 3. ⚑⚑⚑ MODEL DZIAŁA JAKO SORTOWNIK — I TO JEST DOBRA WIADOMOŚĆ

```
p_model        n     deklaruje   TRAFIA     luka
0–55%       1549       44,5%     30,9%    -13,6
55–65%       876       60,1%     44,5%    -15,6
65–75%       885       69,9%     56,6%    -13,3
75–85%       796       80,1%     67,1%    -13,0
85–100%      801       90,4%     77,7%    -12,7
```

Trafność rośnie **monotonicznie** z deklarowaną szansą: 31% → 78%.
**Model umie odróżnić pewniaka od loterii.** To nie jest generator losowy.

⚑ **Ale luka jest STAŁA: −13 pp w KAŻDYM paśmie.** To nie jest szum ani brak
umiejętności — to jest jedno systematyczne przesunięcie. Model mówi 90%,
wchodzi 78%. Mówi 60%, wchodzi 45%.

---

# 4. SKĄD SIĘ BIERZE TE −13 pp (to już wiemy z wcześniejszych pomiarów)

* Na **całym rozkładzie** bias wynosi 1,00 — model jest poprawny.
* Na **górnych 5% λ** bias to 1,46 — tam, gdzie powstają typy, przeszacowuje.
* Model dobrze się kalibruje **tam, gdzie zgadza się z kursem** (przewaga ≤0 pp
  → luka −1,6 pp), a psuje się proporcjonalnie do tego, jak bardzo się z nim
  nie zgadza (przewaga +12..20 pp → luka −22,5 pp).
* Ponad sam kurs model wnosi AUC **0,530** — czyli praktycznie nic.

**To jest klasyczna klątwa zwycięzcy: selekcjonujemy typy po „przewadze nad
kursem", czyli systematycznie wybieramy własne błędy.** Im większa
deklarowana przewaga, tym większa szansa, że to pomyłka modelu, a nie błąd
bukmachera.

---

# 5. GDZIE NAPRAWDĘ ZARABIAMY — cztery segmenty, jeden pewny

Segmenty z n ≥ 40, posortowane po trafności:

```
segment                    n    deklaruje   TRAFIA     ROI
match_cards|ponizej      132      69,0%     63,6%    +4,9%
team_fouls|ponizej       114      70,1%     63,2%    +9,2%
team_sot|ponizej         222      68,8%     62,2%   +10,8%
match_sot|ponizej         66      63,6%     60,6%   +10,1%
match_corners|powyzej     83      70,1%     61,4%    +2,1%
--- poniżej zera ---
team_goals|ponizej       985      65,0%     53,1%    -3,7%
team_corners|ponizej    1157      68,2%     51,3%    -5,1%
team_corners|powyzej     373      63,9%     50,1%    -5,1%
```

**Test stabilności** (dzieli data meczu — ten sam, który dziś trzy razy
obalił rekomendacje):

```
segment                 I połowa            II połowa
team_sot|ponizej      119 / 61,3% / +9,0%  103 / 63,1% / +12,8%   ⚑ STABILNY
match_cards|ponizej    26 / 80,8% / +10,9% 106 / 59,4% /  +3,5%   dodatni w obu
team_fouls|ponizej     44 / 59,1% /  -1,7%  70 / 65,7% / +16,0%   niestabilny
match_corners|powyzej  26 / 69,2% /  -8,2%  57 / 57,9% /  +6,8%   niestabilny
```

⚑ **`team_sot|ponizej` to jedyny segment dodatni w OBU połowach próby** —
i to jest ten sam segment, który wyszedł jako zyskowny już wcześniej.
Razem z `match_cards|ponizej` daje ~354 rozliczenia i ~12 typów na dobę.

⚑ Ale ich trafność to **62%, nie 75%**. Segmenty, które zarabiają, i typy,
które wchodzą, to **dwa różne zbiory**.

---

# 6. ⚑⚑⚑ SEDNO: TRZEBA WYBRAĆ, CZYM JEST PRODUKT

Przy obecnym modelu **nie da się mieć obu naraz**, bo model nie ma przewagi
nad kursem (AUC ponad kurs 0,530). Do wyboru:

## Ścieżka A — PRODUKT NA TRAFNOŚCI (to, o co prosisz)

```
reguła:      publikujemy tylko kurs <= 1,40  (i/lub p_model >= 80%)
efekt:       ~76% trafień, ~38 typów na dobę
ROI:         -2,7%   (dziś -5,7% na liście dnia)
```

* Klient widzi „trzy z czterech typów wchodzą" — to jest sprawdzalne i prawdziwe.
* Produkt wygląda i działa jak narzędzie analityczne, dokładnie jak SmartBet.
* **Uczciwie:** to jest produkt informacyjny, nie inwestycyjny. Nie wolno przy
  nim obiecywać zysku — ale nie trzeba, bo konkurencja też go nie dowozi,
  a bierze 79 zł miesięcznie.
* Wdrożenie: **jeden próg kursu w selekcji.** Godzina pracy.

## Ścieżka B — PRODUKT NA ZYSKU

```
reguła:      publikujemy tylko segmenty stabilnie dodatnie
efekt:       ~12 typów na dobę, trafność ~62%
ROI:         +5..10%  (na dzisiejszej próbie)
```

* Uczciwy zysk, ale mała podaż i niska trafność — klient widzi, że co trzeci
  typ nie wchodzi.
* **Ryzyko:** to selekcja po wyniku na tej samej próbie. Stabilny jest tylko
  JEDEN segment; reszta może być szumem.
* Wdrożenie: biała lista segmentów. Też godzina pracy.

## Ścieżka C — OBIE NARAZ, ROZDZIELONE W PRODUKCIE

```
„Pewne typy"        kurs <= 1,40, trafność ~76%   <- twarz produktu
„Wyszukane okazje"  segmenty dodatnie, ~12/dobę   <- dla grających na zysk
```

To jest to, co robi konkurencja: SmartBet ma „prognozy dnia" (pewne) obok
„value bets" (ryzykowne). **Nie udajemy, że to jedno i to samo.**

---

# 7. DLACZEGO DOTĄD NIC NIE SZŁO DO PRZODU

Bo każda sesja poprawiała **poprawność** — kalibrację, bramy, stemple,
pomiary — a nie **produkt**. Wszystkie te naprawy były potrzebne i żadna nie
była zmarnowana (bez nich powyższe liczby byłyby fałszywe), ale żadna nie
odpowiadała na pytanie, które trzeba było zadać na początku:

> **Czym jest ten produkt: narzędziem, które trafia, czy modelem, który zarabia?**

To pytanie nie zostało nigdy rozstrzygnięte, więc silnik był strojony pod
jedno (zysk), a oceniany po drugim (trafność). Stąd wrażenie, że kręcimy się
w kółko — bo faktycznie kręcimy.

**Dobra wiadomość: model jest lepszy, niż wygląda.** Sortuje poprawnie
(31% → 78%), a jego jedyna wada to jedno stałe przesunięcie −13 pp,
wynikające ze sposobu SELEKCJI, nie z rachunku.

---

# 8. CO ROBIĆ — konkretnie

1. **Decyzja właściciela: A, B czy C.** Bez tego każda kolejna zmiana będzie
   znowu strojeniem pod niewiadomy cel.
2. **Po decyzji: jedna zmiana w selekcji** (próg kursu albo biała lista
   segmentów) — godzina pracy, nie tydzień.
3. **Potem dopiero** rzeczy z analizy silnika: ruch kursu, drugi bukmacher
   dla rynków drużynowych, połowy meczu.

⚑ **Czego NIE robić:** kolejnego audytu, kolejnego dry-runu i kolejnej warstwy
uczenia, zanim nie zapadnie decyzja z punktu 1. Model nie jest dziś wąskim
gardłem — jest nim brak definicji produktu.
