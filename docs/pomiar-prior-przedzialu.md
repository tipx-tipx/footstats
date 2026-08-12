# Prior przedziału kalibracji — pomiar z 12.08.2026

Dlaczego przedział bez własnej próby przestał dostawać wartość rynku, i co
z tego wyszło. Wszystkie liczby policzone na księdze produkcyjnej (4333 wpisy,
1777 rozliczeń bieżącej epoki), skrypty w opisie przy każdej sekcji.

---

## 1. Co odsłoniła kontrola startowa

Naprawa odwróconego znaku kalibracji (`ba5a2f4`, 11.08) **przewróciła stronę
typów**. To nie jest efekt uboczny do zignorowania — to zmiana charakteru
produktu:

| | „poniżej" | „powyżej" |
|---|---|---|
| V1 — rozliczone | 83,2% | 15,6% |
| V2 — rozliczone | 5,0% | **91,0%** |
| V2 — żywe typy 12.08 | 26,9% | **72,1%** |

Strona „powyżej" traciła **zawsze**, nie dopiero po naprawie:

```
POWYŻEJ  V1: 300 typów  luka -14,0 pp  ROI -13,1%   (szum 2,9)
         V2:  91 typów  luka -20,3 pp  ROI -17,2%   (szum 5,2)
PONIŻEJ  V1: 1364 typy  luka -12,4 pp  ROI  -0,7%   (szum 1,3)
         V2:    5 typów — za mało, żeby cokolwiek powiedzieć
```

Różnica V1/V2 na stronie „powyżej" (6,3 pp) mieści się w szumie. **V2 nie
zepsuło tej strony — przeniosło na nią produkcję** ze strony o ROI bliskim
zera. To rozróżnienie prowadzi w zupełnie inne miejsce niż wycofanie zmiany.

Bramy publikacji odsiewają najgorsze: V2 „powyżej" na liście klienta ma ROI
−5,3% (n=32), w tle −23,7% (n=59).

⚑ Warunek audytu do oceny V2 (min. 30 „powyżej" **i** 30 „poniżej") **nadal
nie jest spełniony** — mamy 91/5. Formalnej oceny V2 wciąż nie da się zrobić.

---

## 2. Usterka: prior przedziału pochodził z przeciwnego reżimu

Kalibracja dzieli szansę na cztery przedziały `p_over`. Do 12.08 przedział bez
własnej próby dostawał `global` — bias całego rynku — a przedział z próbą był
do `global` **ściągany**. Przy równomiernym materiale to zwykły shrinkage.
Nasz materiał równomierny nie jest.

`global` liczy się **po obserwacjach**, a te siedzą prawie wyłącznie w jednym
przedziale: do 11.08 produkt typował „poniżej", więc `p_over` tych rekordów
było niskie. Zmierzone (`pokrycie_mapy.py`):

```
team_corners   p_over 0,00-0,55   n=513   model ZANIŻA  o +16,1 pp
               p_over 0,55-0,70   n= 41   model ZANIŻA  o +11,5 pp
               p_over 0,70-0,85   n= 27   model ZAWYŻA  o -22,6 pp
               p_over 0,85-1,01   n= 14   model ZAWYŻA  o -17,2 pp

team_shots     p_over 0,00-0,55   n= 66   +22,2 pp
               p_over 0,85-1,01   n=  4   -39,4 pp
```

Błąd **zmienia znak wzdłuż skali**, a 86% obserwacji leży po jednej jej
stronie. `global` = +0,80 (górny cap) było więc wartością przedziału niskiego,
wpisywaną w przedziały wysokie — te same, w których model zawyża.

Po naprawie znaku produkt przeskoczył dokładnie tam: **89% rozliczeń V2 stoi
w `p_over` ≥ 0,55**, a 76% żywych typów w przedziale z własnym pomiarem, który
i tak był ściągany do skażonej wartości rynku.

To ta sama rodzina błędu co odwrócony znak: **liczba zmierzona w jednym
reżimie, stosowana w przeciwnym.**

---

## 3. Test out-of-sample

Mapa uczona **wyłącznie** na rozliczeniach V1, sprawdzana na 100 rozliczeniach
V2 z 11–12.08 (84 z odtwarzalnym `p_over_raw` ze stempli `kal_rynek` +
`kal_strumien`). Skala `p_over`, bo tylko w niej korekta ma jeden znak.
Skrypt: `replay_fallback.py`.

| wariant | Brier | log-loss | luka |
|---|---|---|---|
| A. prior = wartość rynku *(dawniej)* | 0,2774 | 0,7632 | −24,1 pp |
| B. zero tylko dla przedziałów bez próby | 0,2757 | 0,7573 | −21,5 pp |
| C. wartość z najbliższego zmierzonego | 0,2795 | 0,7683 | −24,3 pp |
| D. ściąganie do zera wg próby, tylko puste | 0,2750 | 0,7558 | −21,9 pp |
| E. prior = średnia PO przedziałach | 0,2793 | 0,7676 | −24,3 pp |
| **F. prior = 0 dla wszystkich przedziałów** | **0,2625** | **0,7192** | **−18,9 pp** |
| G. jak F, ale puste zostawione po staremu | 0,2641 | 0,7251 | −21,4 pp |

Wdrożony **wariant F**: −5,4% Briera, −5,8% log-lossu, luka −24,1 → −18,9 pp.

Warianty B i D pokazują, dlaczego samo załatanie pustych przedziałów nie
wystarcza: większość szkody siedzi w przedziałach, które **mają** własny
pomiar, ale są do skażonej wartości rynku ściągane.

**Uczciwie: to zmniejsza szkodę, nie leczy.** Luka −18,9 pp zostaje, więc
główna przyczyna przeszacowania leży poza kalibracją.

---

## 4. Co się zmieniło w mapie

```
przedziałów na capie ±0,80:   6  ->  1
średnia zmiana delty:              0,227
największa zmiana:                 1,206  (team_corners 0,85-1,01)

team_corners  0,70-0,85   +0,443 -> -0,588   ZMIANA ZNAKU
team_corners  0,85-1,01   +0,800 -> -0,406   ZMIANA ZNAKU
team_goals    0,70-0,85   -0,263 -> -0,479
team_shots    0,55-1,01   +0,800 -> 0 (brak próby, nie zgadujemy)
```

Pokrycie: 17 z 68 przedziałów na własnych danych, 23 bez próby (nie
korygujemy), 28 na połowie korekty z poprzedniej epoki.

---

## 5. Pułapka przy wdrożeniu — dolewka z obcej epoki

Pierwsza wersja zmiany **po cichu skasowała korektę rynkom zawodniczym**
(faule, przechwyty, strzały głową, „zza pola"). Mechanizm: rynek dostaje
dolewkę z poprzedniej epoki właśnie dlatego, że własnych rozliczeń nie ma —
więc jego przedziały nie mają próby, więc po zmianie dostawały zero, a
`_dolej_z_innej_epoki` kopiowało te zera. Siedem rynków straciłoby korektę
−0,16…−0,39 bez jednej linijki w logu.

Naprawione: dolewka bierze wprost `global` (przyznanie się do niewiedzy nie ma
przedziałów). Pilnuje tego test
`test_dolewka_przezywa_zerowy_prior_przedzialu`.

---

## 6. Czemu „powyżej" traci — zmierzone (skrypt `czemu_powyzej.py`)

Sprawdzone trzy hipotezy. **Wygrywa selekcja, nie rozkład i nie lambda.**

Luka wobec przewagi modelu nad kursem (`p_model` − 1/kurs):

```
POWYŻEJ   przewaga <=0 pp    n= 68   luka  -1,6 pp   ROI  -9,1%
          przewaga 0..6      n= 83   luka -16,4 pp   ROI -20,7%
          przewaga 6..12     n=152   luka -16,7 pp   ROI -11,9%
          przewaga 12..20    n= 87   luka -22,5 pp   ROI -14,6%

PONIŻEJ   przewaga 0..6      n=122   luka  +0,2 pp   ROI  +9,5%
          przewaga 6..12     n=536   luka  -9,5 pp   ROI  -0,6%
          przewaga 12..20    n=702   luka -16,7 pp   ROI  -1,8%
```

⚑ **Model jest dobrze skalibrowany dokładnie tam, gdzie zgadza się z rynkiem,
i psuje się proporcjonalnie do tego, jak bardzo się z nim nie zgadza.** Przy
przewadze ≤ 0 pp luka wynosi −1,6 pp na 68 obserwacjach; przy +12…20 pp rośnie
do −22,5 pp. Po stronie „poniżej" ten sam wzór: przedział 0–6 pp ma lukę +0,2
i ROI **+9,5%**.

To potwierdza wcześniejszy pomiar „rozjazd z rynkiem" na świeżych danych i w
rozbiciu na strony. Cała przewaga, którą model rzekomo znajduje, jest w
większości jego własnym błędem.

Pozostałe hipotezy — **obalone jako całościowe wyjaśnienie**:

* **Sama lambda** (za dużo przewidywanych zdarzeń) — nie ma jednolitego znaku.
  `team_goals` ma lukę ujemną po obu stronach (−20,8 / −10,1), a `team_shots`
  odwrotnie niż reszta (−9,8 „powyżej" wobec −22,2 „poniżej"). Gdyby lambda
  była systematycznie przesunięta, strony miałyby przeciwne znaki.
* **Ogon rozkładu** (naddyspersja przy wysokich liniach) — luka „powyżej" nie
  rośnie z linią, wręcz maleje (linia 0–1,5: −21,0 pp; linia 6,5+: −10,8 pp).
* **Sam kurs** — „poniżej" ma lukę −11…−15 pp w KAŻDYM przedziale kursu, więc
  różnica ROI między stronami nie bierze się z tego, że „powyżej" jest droższe.

---

## 7. Co dalej

Do sprawdzenia po ~100 rozliczeniach nowej wersji
(`2026-08-12-prior-przedzialu`), paired Brier / log-loss, **nie** ROI z kilku
dni:

1. czy luka w przedziałach `p_over` ≥ 0,55 faktycznie zeszła z −24 do ~−19 pp,
2. czy strona „powyżej" utrzymuje udział ~70%, czy wraca do równowagi,
3. **czemu strona „powyżej" traci** — to jest pytanie otwarte i ważniejsze
   niż kalibracja. Luka −14…−20 pp na 391 typach nie jest szumem, a kalibracja
   przedziałowa domyka z tego najwyżej 5 pp.
