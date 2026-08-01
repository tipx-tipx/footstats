# Test w przód: drużynowe „poniżej", kurs 1,9+

**Zarejestrowany 2026-08-01. Do zamknięcia po 40 rozliczeniach.**

Ten plik jest *pre-rejestracją*, nie notatką. Leży w repo, a nie w bazie,
dokładnie po to, żeby zmiana zasad testu zostawiała ślad w historii gita.
Jeśli ktoś (ja też) będzie chciał poprawić kryteria w trakcie, bo wynik
zaczyna wychodzić nie po jego myśli — będzie to widać w `git log`.

---

## Skąd to się wzięło

Pomiar 2026-07-31 na 536 rozliczonych typach z kursem, wszystkie ROI po
podatku, wyłącznie typy w oknie zgody z rynkiem:

```
segment                      n   weszło  obiecywał   luka     ROI     bilans
powyżej zawodnicze  <1,9   118   68,6%    74,3%     −5,6 pp  −19,1%  −22,57u
powyżej zawodnicze  ≥1,9    22   40,9%    46,1%     −5,2 pp  −17,6%   −3,86u
powyżej drużynowe   <1,9    30   63,3%    74,3%    −11,0 pp  −24,0%   −7,19u
powyżej drużynowe   ≥1,9     2   50,0%    52,0%     −2,0 pp  +15,3%   +0,31u
poniżej drużynowe   <1,9    43   81,4%    80,4%     +1,0 pp   −6,2%   −2,67u
poniżej drużynowe   ≥1,9    24   62,5%    45,8%    +16,7 pp  +48,8%  +11,72u   <--
```

Ostatni wiersz to jedyny zyskowny segment w całym zestawieniu. Model
**nie**doszacowuje go o 16,7 pp — czyli myli się tam w drugą stronę niż wszędzie
indziej.

## Czemu to NIE jest jeszcze strategia

Dwa powody, oba wystarczające same z siebie:

1. **n = 24.** Przy tej próbie ROI +48,8% mieści się w przedziale, który
   obejmuje również zero. To jest hipoteza, nie wynik.

2. **Jedna warstwa modelu już się na tej próbce uczyła.** Przedziały w korekcie
   strumienia (`rozliczanie.KOREKTA_PRZEDZIAL_MIN_N`) zostały policzone
   2026-07-31 na tych samych rozliczeniach, a bin `drużyny p_over 0,00–0,55`
   dostaje −0,519 zamiast globalnych −0,324 — czyli **dokładnie ten segment**.
   Ściąganie do wartości globalnej (waga `n/(n+20)`) to łagodzi, ale nie
   kasuje. Mierząc dalej na tych samych rekordach, mierzylibyśmy częściowo
   własne dopasowanie.

Punkt 2 jest powodem, dla którego test musi liczyć **wyłącznie rekordy ze
stemplem `wersje`** (patrz `betting.wersje_publikacji`). Stempel wszedł
2026-08-01, więc wszystko wcześniejsze jest z epoki, na której się uczyliśmy.

---

## Definicja segmentu (zamrożona)

Typ wchodzi do testu, gdy spełnia WSZYSTKIE warunki:

| warunek | wartość |
|---|---|
| strumień | `druzyny` (`team_*`, `match_*`, `wiecej_*`) |
| strona | `ponizej` |
| kurs | `>= 1,90` |
| okno zgody z rynkiem | `betting.w_oknie_zgody(p_model, kurs)` |
| stempel epoki | `wersje` obecne (czyli publikacja od 2026-08-01) |
| stan | rozliczony jako `wygrany` albo `przegrany` |
| wykluczenia | `sugestia`, `odrzucony`, `poza_publikacja` |

Liczone: liczba typów, trafienia, średnia deklarowana szansa, luka
(trafienia − deklaracja) i ROI po podatku. Implementacja:
`rozliczanie.forward_test()`; wynik jedzie do `typy_wyniki` pod kluczem
`forward_test`.

## Reguła stopu

* **Cel: 40 rozliczeń.** Przed osiągnięciem tej liczby wynik jest raportowany,
  ale **nie wolno na jego podstawie niczego zmieniać**.
* Do zamknięcia testu **nie ruszamy niczego, co dotyka tego segmentu**:
  progów widełek drużynowych, granic okna zgody, przedziałów korekty
  strumienia ani `MIN_ODDS`.
* Zmiany gdzie indziej (typy zawodnicze, kupony, interfejs) są dozwolone —
  ale każda musi podbić `betting.WERSJA_POLITYKI`, jeśli rusza selekcją.
  Gdyby podbiła, ten test startuje od nowa: mieszanie polityk jest dokładnie
  tym błędem, przed którym się tu zabezpieczamy.

## Jak czytać wynik

* **luka bliska zeru** — model mówi o tym segmencie prawdę; ROI zależy wtedy
  od kursu, nie od kalibracji,
* **luka nadal mocno dodatnia (+10 pp i więcej)** — niedoszacowanie jest realne
  i wtedy jest o czym rozmawiać: albo osobna korekta dla tego segmentu, albo
  większy udział w publikacji,
* **luka ujemna** — pierwsze 24 typy były szczęśliwą próbką. To też jest wynik
  i trzeba go zapisać, a nie przemilczeć.

W każdym z trzech przypadków wnioski wpisujemy TUTAJ, pod tą linią, razem
z datą i liczbą rozliczeń.

---

## Wyniki

*(pusto — test wystartował 2026-08-01)*
