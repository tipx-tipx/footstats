# Drabinka ma dwa szczeble, a rozliczaliśmy jeden (13.08.2026)

Zakładka Drabinki sprzedaje jedno zdanie usera: „drugi szczebel bardzo często
siada i jest jakby głównym celem, żeby go upolować". Cała selekcja kart jest
pod to zbudowana — `_oceń_karte` uśrednia przewagę OBU szczebli, więc drugi
współdecyduje o tym, która karta idzie na górę listy.

**Do 13.08 ten szczebel nie miał ani jednego rozliczenia.** Księga zapisywała
wyłącznie `hero` (szczebel z nagłówka). Przy strumieniu, który traci najwięcej
w całym produkcie, była to najdroższa biała plama, jaką mieliśmy.

## Stan wyjściowy — liczby sprzed zmiany

Strumień drabinek, bieżąca epoka, 94 rozliczenia (kontrola startowa 13.08):

```
poziom                    n   deklaruje   trafia     luka      ROI
pierwszy (nagłówek)      94      52,2%    37,2%    -15,0    -25,5%
drugi (cel polowania)     0    — nigdy nie rozliczany —
```

Rozbicie pierwszego szczebla, na czym traci (118 rekordów w księdze, przed
filtrem rynków osobnych):

```
po klasie karty          n   trafia  deklaruje    luka      ROI
solidny                 70    38,6%     48,9%   -10,3    -30,8%
mocny                   19    36,8%     61,3%   -24,5    -41,4%
top                      3     0,0%     48,5%   -48,5   -100,0%

po linii                 n   trafia  deklaruje    luka      ROI
1,5                     49    38,8%     41,9%    -3,1    -28,1%
0,5                     34    32,4%     58,1%   -25,8    -49,8%
2,5                     32    28,1%     47,0%   -18,9    -36,9%
```

⚑ Klasy kart są **odwrócone**: „top" trafia 0%, „solidny" 38,6%. Progi
`PROG_KLASY` były od początku opisane w kodzie jako założenie do skalibrowania
z rozliczeń — to pierwszy pomiar, który mówi, że kalibracji wymagają pilnie.
Przy n=3 dla „top" to jeszcze nie dowód, ale kierunek jest jednoznaczny.

## Co dziś deklarujemy o drugim szczeblu

Siedem kart żywych na radarze 13.08 wieczorem (mała próba — to punkt
odniesienia, nie wniosek):

```
                                        mediana
pierwszy szczebel: nasza szansa           50,4%   przy kursie 1,61
drugi szczebel:    nasza szansa           31,0%   przy kursie 2,75
                   sama historia (traf/z) 50,0%
                   cena bukmachera (1/k)  36,4%
```

**Własną liczbą stawiamy drugi szczebel poniżej ceny bukmachera.** Karta
zachęca do polowania na coś, czemu sami dajemy mniejszą szansę, niż wycenia ją
rynek. Droga z 50% do 31% prowadzi przez trzy kolejne ścięcia tej samej
niepewności: Wilson (kara za krótką próbę) → korekta kontekstowa → korekta
strumienia zmierzona na szczeblach PIERWSZYCH.

## Sygnał retrospektywny — 58%, ale z zastrzeżeniem

Księga zna już pary „ten sam mecz, ten sam podmiot, ten sam rynek, dwie różne
linie" — z typów modelu, nie z drabinek. 169 takich grup, 104 z nich mają
wygrany niższy szczebel:

```
niższy szczebel wszedł                    104
   wszedł też wyższy                       60   (58%)
   wyższy nie wszedł                       44
   niespójne (wyższy tak, niższy nie)       0
```

⚑ **To NIE jest odpowiedź na pytanie o drabinki** i nie wolno tak tego cytować.
Te pary to typy, które przeszły bramy publikacji **osobno**, czyli podwójna
selekcja; rynki są w większości drużynowe (rożne 35, gole 19), a drabinki są
zawodnicze. Liczba mówi tyle: rząd wielkości „drugi szczebel wchodzi po
pierwszym" jest bliżej połowy niż jednej trzeciej, więc 31% z kart wygląda na
zaniżone — i dlatego warto to zmierzyć naprawdę, zamiast dalej zgadywać.

Zero niespójności to osobna, dobra wiadomość: rozliczanie linii działa
poprawnie (wyższy szczebel nie wchodzi bez niższego).

## Co weszło 13.08

Drugi szczebel każdej opublikowanej karty trafia do księgi jako typ
**pomiarowy**: `odrzucony = True`, `odrzucenie_powod = "drugi_szczebel"`.
Ta sama ścieżka co pomiar progu pokrycia, czyli:

* rozlicza się w tle i znamy jego wynik,
* **nie** wchodzi do Skuteczności (user go nie obstawiał jako osobnego typu),
* **nie** uczy kalibracji ani korekty strumienia,
* nie zmienia niczego userowi ani modelowi — dochodzi wyłącznie wiedza.

Rekord niesie stempel `szczebel` (1 = hero, 2 = drugi) oraz w `rachunku`
szansę **przed** korektą strumienia (`p_over_raw`) obok tej pokazanej na
karcie. Dopiero obie liczby przy tej samej prawdzie rozstrzygną pozycję
z kolejki: „zdjąć korektę strumienia z drugiego szczebla".

Odczyt: `rozliczanie.pomiar_szczebli_drabinek` oraz **część 6 kontroli
startowej** (`pipeline/scripts/audyt_uczenia.py`).

## Klasy kart — etykieta zdjęta ze strony (13.08)

Klasa („top" / „mocny" / „solidny") liczy się z przewagi nad kursem
(`radar._klasa_karty`) i mówiła userowi wprost: *„Nasza szansa wyraźnie bije
cenę bukmachera"*. Pierwszy pomiar tej etykiety, 94 rozliczenia:

```
klasa                                n   deklaruje  trafia    luka      ROI
solidny („niewielka przewaga")      70     49,7%    38,6%   -11,1    -21,3%
mocny   („wyraźna przewaga")        19     60,9%    36,8%   -24,1    -33,4%
top     („największa przewaga dziś") 3     49,4%     0,0%   -49,4   -100,0%
```

Deklaracja rośnie z klasą (49,7 → 60,9%), trafienia **nie** — więc rośnie sama
luka. Kwintyle przewagi mówią to samo, tylko ostrzej:

```
przewaga (edge)          n   deklaruje  trafia    luka      ROI
-0,275..-0,030          18     44,7%    44,4%    -0,3    -10,4%   <- skalibrowane
-0,029..+0,025          18     47,5%    33,3%   -14,2    -32,4%
+0,025..+0,039          18     46,6%    22,2%   -24,3    -44,2%
+0,041..+0,063          18     61,1%    55,6%    -5,5     +3,1%
+0,064..+0,108          22     59,4%    31,8%   -27,6    -40,4%
```

Korelacja przewagi z trafieniem: **−0,084**. Karty, którym przypisujemy
najmniejszą przewagę, są skalibrowane co do punktu; te z największą rozjeżdżają
się o −27,6 pp. To ten sam wzorzec, co w reszcie produktu: model jest dobrze
skalibrowany tam, gdzie zgadza się z kursem, i psuje się proporcjonalnie do
tego, jak bardzo się z nim nie zgadza.

**Decyzja właściciela: plakietka schodzi z karty do czasu pomiaru.** Klasa
dalej się liczy i zapisuje w księdze, więc pomiar biegnie bez przerwy — znika
wyłącznie obietnica, której nie potwierdzają rozliczenia. Sprawdzone na żywej
karcie z klasą „mocny" (Sami Ouaissa): przed zmianą nagłówek niósł „wyraźna
przewaga", po zmianie zostają „druga poprzeczka 54%" i „przebił w 7 z 10
meczów" — czyli liczby, nie ocena. Reszta karty bez zmian, audyt 390 px czysty.

Etykieta wraca, gdy któraś klasa realnie trafia lepiej od pozostałych.

## Czego z tego jeszcze NIE wiadomo

* Czy 31% jest zaniżone — retrospektywne 58% pochodzi z innej populacji.
  Odpowiedź po ~25 rozliczeniach drugich szczebli (`KOREKTA_DRABINEK_MIN_N`).
* Czy zdjęcie korekty strumienia z drugiego szczebla pomoże. Uwaga: podniesie
  ona deklarowane szanse, a strumień jako całość **przeszacowuje o 15 pp** —
  więc to zmiana, która może pogłębić lukę zamiast ją domknąć.
* Czy klasy kart („top" / „mocny" / „solidny") niosą jakąkolwiek informację.
  Dzisiejsze liczby sugerują, że są odwrócone.
* Trzeci szczebel i wyżej — na kartach rzadki, nie zapisujemy go.
