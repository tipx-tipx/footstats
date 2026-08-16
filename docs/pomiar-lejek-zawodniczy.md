# Co naprawdę blokuje strumień zawodniczy

**Pomiar z 16.08.2026**, na rejestrze odrzuceń z dry-runu (10 613 wpisów,
246 meczów) i na księdze. Pytanie postawione przed wpięciem SportsGamblera:
czy składy są tym, co blokuje typy zawodnicze.

**Stan wyjściowy: w dry-runie powstało ZERO typów zawodniczych** (99 typów,
wszystkie drużynowe). Strumień stoi, mimo że do silnika trafiło 3221 rynków
zawodniczych.

## 1. Składy NIE są wąskim gardłem

```
par (mecz, zawodnik) rozważanych      2992
   blokuje je skład                    527  (17%)
   nie mają problemu ze składem       2465  (82%)
```

Co więcej, `poza_skladem` znaczy **„skład jest znany i zawodnika w nim nie
ma"** — czyli blokada poprawna. Dołożenie SportsGamblera zwiększy liczbę
meczów ze znanym składem (dziś 29 ze 110), a więc **doda blokad, nie zdejmie
ich**. Prognoza składów poprawi JAKOŚĆ typów zawodniczych, ale ich nie odblokuje.

## 2. Co blokuje naprawdę

Powody dla par bez problemu ze składem:

```
brak_kursu                2562   <- „Superbet nie kwotuje tego rynku"
za_malo_zdarzen           1404   <- nasz próg λ >= 0,35
szansa_za_niska           1251   <- nasz próg profilu
za_stara_historia          582
za_malo_minut              364
```

Rozbicie `brak_kursu` po rynkach: `shots` 1292, `fouls_committed` 557,
`sot` 275, `fouls_won` 171, `tackles` 110.

## 3. Luzowanie progu λ POGORSZY, nie poprawi

Sprawdzone na rozliczeniach bieżącej epoki ze stemplem `lambda` (wszedł 03.08):

```
pasmo λ        n     deklaruje   trafia     luka      ROI
0–1          103       73,4%     58,3%    -15,1    -9,0%
1–2          433       69,2%     54,3%    -14,9    -6,5%
2–4          614       71,6%     58,5%    -13,2    -0,0%
4–8          730       70,0%     56,8%    -13,2    -4,2%
8+           679       67,3%     55,2%    -12,1    -4,8%
```

Luka rośnie monotonicznie w miarę spadku λ. **Próg ma pokrycie w kierunku** —
obniżanie go dołoży typów gorzej wycenionych.

⚑ Zastrzeżenie: poniżej progu 0,35 księga ma **zero** rozliczeń, bo brama
wycina je przed publikacją. Powyższe to ekstrapolacja z pasm nad progiem, nie
pomiar spod progu. Mechanizm typów pomiarowych (`odrzucone_pomiar`) obejmuje
dziś cztery progi z `betting` (EV, pewność, rozjazd, rozjazd względny), ale
NIE λ ani progu profilu — te odrzucenia dzieją się wcześniej, przed wyceną.

## 4. Materiał LEŻY NIEUŻYWANY — u drugiego bukmachera

Betclic ma własny job i od 08.08 własną pamięć oferty. Jego moduł już parsuje
propsy zawodnicze, ale oferta trafia **wyłącznie do drabinek**:

```
w pamięci Betclica:  44 mecze
   par (mecz, zawodnik)              2128
   par (mecz, zawodnik, rynek)      10087
   wpisów kursowych z liniami       19611
   rynki: sot 2040, shots 2040, tackles 1946, fouls_committed 1630,
          headed_sot 753, sot_outside_box 753, shots_outside_box 753
```

Dla porównania: cały cykl dołożył **3221** rynków zawodniczych ze Superbeta
(4464 wpisy kursowe). **Betclic ma ponad trzy razy więcej materiału
zawodniczego niż Superbet** — i dokładnie w tych rynkach, których Superbet
nie kwotuje (`shots`, `fouls_committed`, `sot`, `tackles`).

## ⚑ WNIOSEK I REKOMENDACJA

Kolejność jest odwrotna do intuicyjnej:

1. **Nie wpinać SportsGamblera po to, żeby odblokować strumień** — nie o to
   się rozbija. Wpiąć go później, dla jakości (i z zastrzeżeniem na rozgrywki:
   Argentyna 62,7%, `docs/pomiar-sklady-sportsgambler.md`).
2. **Nie luzować progów** — λ ma pokrycie w kierunku.
3. **Jedyne realne źródło podaży to oferta zawodnicza Betclica.**

⚑ **ALE nie wpinać jej od razu na stronę.** Strumień zawodniczy ma dziś
ROI −16,0% i lukę −16,3 pp na 77 rozliczeniach — jest drugim najgorszym po
drabinkach. Potrojenie podaży w strumieniu, który przeszacowuje o 16 pp,
mnoży stratę zamiast ją odrabiać.

**Proponowana droga:** wpiąć ofertę Betclica jako źródło kursów zawodniczych,
ale powstałe typy kierować do księgi jako POMIAROWE (poza publikacją) —
rozliczają się i uczą model, klient ich nie widzi. Po ~100 rozliczeniach
będzie wiadomo, czy strumień zawodniczy nadaje się do pokazania. To ta sama
metoda, którą 13.08 zastosowano do drugiego szczebla drabinek.
