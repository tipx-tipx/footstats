# Czy cena należy do prognozy — pomiar z 12.08.2026

Krok 7 kolejki audytu („zbudować niezależne `p_sport` i dopiero po nim
dołączać cenę"). Zanim cokolwiek przebudujemy — dwa pomiary.

---

## 1. Test niezmienniczości: NIE PRZECHODZI

Audyt wymaga, żeby „zmiana kursu przy tych samych cechach nie zmieniała
rozkładu". Dziś zmienia. Ten sam mecz, te same cechy drużyny, rusza się
wyłącznie cena:

```
kurs gospodarza 1,20 -> 9,00     mnożnik scenariusza meczu
   team_corners / team_shots     1,200 -> 0,850     41% rozpiętości
   tackles / interceptions       0,850 -> 1,095     29%
   team_fouls                    0,996 -> 1,055      6%

sama linia goli (over 2,5 od 1,40 do 2,60), 1X2 BEZ ZMIAN
   team_corners                  1,151 -> 0,952     21%
```

Kanał: `tempo.tempo_from_match_odds` (kursy 1X2 + linia goli) →
`implied_spread` / `implied_total` → `context.game_script_factor` → λ → `p`.

Audyt ma więc rację co do faktu: **korelacja model–rynek jest częściowo
konstrukcyjna**, a „przewaga nad kursem" jest po części różnicą między dwoma
przetworzeniami tej samej informacji.

---

## 2. Ale cena POMAGA — i to najbardziej tam, gdzie działa najmocniej

Wniosek „skoro to przeciek, to trzeba go usunąć" nie wytrzymał pomiaru.

Metoda: księga zapisuje przy typie `lambda` (po wszystkich mnożnikach) i
`czynniki.scenariusz_meczu`, więc prognozę bez ceny da się odtworzyć wstecz
(`lambda / scenariusz_meczu`) i policzyć z niej `p_over` dla tej samej linii.
Porównanie na **tych samych** 409 rozliczeniach bieżącej epoki:

| wariant | Brier | log-loss | luka |
|---|---|---|---|
| z ceną (dziś) | **0,2173** | **0,6407** | −2,1 pp |
| bez ceny (`p_sport`) | 0,2239 | 0,6527 | −2,1 pp |

**Usunięcie ceny pogarsza prognozę o 3,1% Briera.**

Per rynek (zysk = ile daje usunięcie ceny):

```
team_shots     n=52   -21,0%     cena pomaga najmocniej
team_corners   n=93    -3,2%
team_sot       n=77    -1,2%
team_cards     n=65    -1,0%
team_goals     n=44    +2,7%     cena lekko szkodzi
team_fouls     n=40    +6,7%     cena szkodzi
```

Wg siły mnożnika:

```
|scenariusz-1|  0,00-0,05   n=167   -0,9%
                0,05-0,10   n= 76   +0,4%
                0,10-0,15   n= 49   +2,9%
                0,15+       n=117  -10,1%   <- im mocniej cena rusza, tym bardziej pomaga
```

---

## 3. Co z tego wynika

**Rozdzielenie `p_sport` ma sens jako NARZĘDZIE POMIARU, nie jako sposób na
poprawę typów.** Bez niego nie da się uczciwie odpowiedzieć na pytanie „czy
mamy przewagę ponad cenę", bo cena jest po obu stronach porównania. Ale
pomiar mówi wprost, że sama prognoza na tym straci.

To spina się z dwiema rzeczami zmierzonymi wcześniej:

* **waga rynku wobec modelu wychodzi 0,00 globalnie na lidze** — model nie
  wnosi mierzalnej informacji ponad cenę,
* **model jest dobrze skalibrowany tam, gdzie zgadza się z ceną** (przewaga
  ≤ 0 pp → luka −1,6 pp) **i psuje się proporcjonalnie do rozjazdu**
  (przewaga +12…20 pp → −22,5 pp).

Trzy niezależne pomiary pokazują to samo: **wartość jest w cenie, a nasze
odchylenia od niej są w większości błędem.**

### Zastrzeżenia, żeby nikt nie przecenił tego pomiaru

1. „Bez ceny" to **nie jest** prawdziwe `p_sport` — to dzisiejszy model
   z wyłączonym jednym czynnikiem. Prawdziwy `p_sport` byłby przebudowany
   i przekalibrowany od nowa, więc mógłby wypaść inaczej.
2. Próba to 409 z 1777 rozliczeń — tylko te ze stemplem `czynniki`, który
   wszedł 07.08. Rynki zawodnicze i drabinki są poza pomiarem.
3. Model był kalibrowany **z** tym mnożnikiem, co samo w sobie faworyzuje
   wariant z ceną.

### Czego ten pomiar NIE mówi

Nie mówi, że mamy zrezygnować z własnego modelu. Mówi, że **dzisiejsza
przewaga nad kursem nie jest dowodem wiedzy** — i że zanim zbudujemy
`p_sport`, trzeba wiedzieć, po co go budujemy: do mierzenia, czy do typowania.
To są dwie różne decyzje.

---

## 4. DECYZJA WŁAŚCICIELA (12.08) i co z niej weszło

**Ściągamy liczbę pokazywaną do ceny — WYŁĄCZNIE ją.** Selekcja, bramy i pula
kuponów zostają na naszej liczbie, więc lista nie ginie.

Waga liczona z rozliczeń raz na cykl (`rozliczanie.waga_sciagania`, warstwa
`sciaganie_karty`). Walidacja czasowa, pięć podziałów: `w* = 0,10` w czterech
z pięciu, zysk Briera +9,9…+11,2% za każdym razem.

### Co to robi z liczbami

```
na 1777 rozliczeniach bieżącej epoki
   dziś deklarujemy   72,9%, wchodzi 60,0%  ->  luka -12,9 pp
   po ściągnięciu     59,7%, wchodzi 60,0%  ->  luka  +0,3 pp
```

I to nie jest średnia kryjąca dwa przeciwne błędy — kalibracja poprawia się
w KAŻDYM paśmie:

| pasmo | n | deklaruje | trafia | luka |
|---|---|---|---|---|
| 0,55–0,65 | 313 | 60,1% | 61,7% | +1,5 |
| 0,65–0,75 | 439 | 70,3% | 71,3% | +1,0 |
| 0,75–0,85 | 358 | 78,2% | 79,9% | +1,6 |

Typy deklarujące ≥75% trafiają po ściągnięciu **79,8%** — czyli więcej, niż
obiecują. Obawa, że jednolite ściąganie zepsuje dobrze skalibrowane górne
pasmo, **nie potwierdziła się**: pasmo ≥85% miało lukę −12,4 pp i po zmianie
ma +2,4 pp.

### ⚑ Czego to NIE robi

Nie poprawia ROI. Na żadnym poziomie wagi zysk nie jest istotny — przy w=0,10
zostają 64 typy z ROI +8,2%, ale bootstrap daje przedział 90% od −27,8% do
+47,1%. To jest naprawa **uczciwości liczby**, nie sposób na zysk. Nie
uzasadniać tym żadnej zmiany w selekcji.

### Skutki uboczne, które trzeba było domknąć razem

1. **Półki na `/druzyny`** szły po `p_model >= 0,70`. Ściągnięta szansa to
   w 90% cena, więc próg odpowiadałby kursowi ~1,35 i pierwsza półka robiła
   się pusta (zmierzone: 5 typów przed, 0 po). Dzielimy teraz po **kursie
   1,90** — to fakt rynku, nie nasza deklaracja, więc nie przesunie się przy
   następnej zmianie modelu.
2. **Opisy półek** obiecywały „Szansa 70% i więcej". Zrzut pokazał typy z 69%,
   66% i 61% pod tym nagłówkiem — czyli opis kłamał już przed zmianą. Mówią
   teraz o kursie, czyli o kryterium, którego naprawdę używamy.
3. **Brama uzasadnień** tnie półkę „więcej płacą", więc musiała przejść na to
   samo kryterium — inaczej tnie inną półkę, niż strona rysuje. Pilnuje tego
   `test_brama_uzasadnien.py` (parytet backend–front). Nowa brama jest
   **łagodniejsza**: obejmuje 325 żywych typów zamiast 417.
