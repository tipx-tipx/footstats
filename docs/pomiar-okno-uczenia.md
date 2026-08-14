# Okno korekty strumienia: typy czy mecze? (pomiar 2026-08-14)

## Pytanie

Okno uczenia korekty strumienia to 120 ostatnich rozliczeń drużynowych.
14.08 były to **cztery mecze z jednej nocy**, z czego jeden dawał 33% okna
(Rosario Central – Corinthians, 40 typów). Wynik w obrębie meczu jest silnie
zgodny — rożne albo padają, albo nie, dla wszystkich typów naraz — więc
warstwa ściągająca szansę KAŻDEGO publikowanego typu stała na jednym
wieczorze.

Rekomendacja przed pomiarem brzmiała: liczyć okno meczami, nie typami.

## Metoda

Walidacja czasowa: korekta liczona wyłącznie z przeszłości, oceniana na
następnych 40 rozliczeniach. 111 punktów walidacji, 2446 rozliczeń
drużynowych z 319 meczów. Korekta liczona dokładnie jak w produkcji (surowe
`p`, orientacja „powyżej", tłumienie, cap) — porównujemy OKNO, nie maszynerię.

Narzędzie: `pipeline/scripts/pomiar_okna_uczenia.py`.

## Wynik

```
wariant                         Brier   vs bez  log-loss  skok delty   typów  meczów
BEZ KOREKTY                    0.2361        —    0.6831           —       —       —
A dziś: 120 typów, typ=1       0.2351    -0.4%    0.6829       0.079     120      16
B 120 typów, mecz=1            0.2343    -0.8%    0.6809       0.099     120      16
C 40 meczów, typ=1             0.2356    -0.2%    0.6840       0.033     376      40
D 40 meczów, mecz=1            0.2361    -0.0%    0.6854       0.037     376      40
```

Test parowany wobec dzisiejszego wariantu (różnica per punkt walidacji, bo
obserwacje z jednego punktu siedzą w tych samych meczach):

```
wariant                        Δ Brier     szum   wygrywa w   werdykt
B 120 typów, mecz=1           -0.00077  0.00064     55/111    w szumie
C 40 meczów, typ=1            +0.00046  0.00066     45/111    w szumie
D 40 meczów, mecz=1           +0.00094  0.00087     48/111    w szumie
```

## ⚑ ODPOWIEDŹ: OKNA NIE ZMIENIAMY

**Żaden wariant nie bije dzisiejszego poza szumem.** Najlepszy z nich (B,
ważenie meczem w tym samym oknie) wygrywa w 55 punktach ze 111 — to rzut
monetą. Rekomendacja sprzed pomiaru się **nie obroniła**, i to z powodu, który
był w niej zapisany jako ryzyko: publikujemy TYPY, nie mecze, więc kalibracja
po typach jest właściwym celem.

Poszerzenie okna do 40 meczów (C, D) wypada **gorzej**, mimo że obejmuje dwa
dni i 40 meczów zamiast czterech. Świeżość wygrywa ze stabilnością: starsze
rozliczenia opisują produkt sprzed napraw priora i kalibracji.

## Co z tego zostaje

1. **Alarm i diagnostyka — naprawione osobno** (commit „Alarm mówi teraz,
   z ilu MECZÓW jest zrobiony"). To był realny problem: alarm krzyczał
   „luka pogłębiła się o 11,5 pp przy szumie 6,0" o trzech meczach.
   Ta część nie zależała od wyniku powyższego pomiaru.

2. **Skok delty jest 2,4× większy w dzisiejszym oknie** (0,079 wobec 0,033
   przy oknie 40 meczów). Na Brier to nie wpływa, ale wpływa na to, jak bardzo
   liczba na karcie skacze między cyklami — dziś korekta pokazuje −0,395,
   a przy oknie 40 meczów pokazałaby −0,251, czyli około **3 pp różnicy
   w szansie widzianej przez klienta**. To pytanie PRODUKTOWE (spójność
   liczby), nie modelowe, i wymaga własnego pomiaru: jak bardzo skacze
   deklaracja tego samego typu między kolejnymi publikacjami.

3. ⚑ **Cała warstwa poprawia Brier o 0,4%** — mało. Ale NIE wyciągać z tego,
   że jest zbędna: ten pomiar ocenia jakość prognozy na typach, które JUŻ
   zostały opublikowane, a korekta wpływa też na to, KTÓRE typy w ogóle
   powstają (jej `p` wchodzi do bram publikacji). Tego walidacja czasowa na
   rozliczonych nie mierzy i nie ma jak zmierzyć wstecz.

## Czego nie robić

* **Nie obcinać typów w tle**, żeby okno objęło więcej meczów — tło wypada
  lepiej niż to, co publikujemy (`poza_lista_dnia` ROI −1,9% wobec −6,3%),
  a mecze z 20+ kandydatami mają lukę −2,1 pp wobec −21,7 pp przy 1–4.
* **Nie wracać do tego bez nowych danych.** Pomiar ma 111 punktów walidacji
  i 2446 rozliczeń; kolejne kilkaset rozliczeń nie zmieni werdyktu „w szumie"
  na „lepszy", bo różnica jest o rząd wielkości mniejsza niż szum.
