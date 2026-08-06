# Strona główna — przegląd drugi, po wdrożeniach

Data: 2026-08-06, wieczór. Stan po pięciu partiach zmian z tego dnia.
Zrzuty: `web/zrzuty/start--*.png`. Pomiary: Playwright, telefon 390 px,
zimne wejście.

Poprzedni przegląd (`przeglad-strona-glowna.md`) jest zamknięty — wszystkie
punkty poza B3 wdrożone. Ten patrzy na stronę od nowa: przekaz, teksty,
technika, wygląd.

---

## Zmierzone

```
dokument (HTML+RSC)   173 kB
JavaScript            912 kB      <-- największa pozycja
CSS                    90 kB
obrazy                  4 kB
inne                  623 kB
RAZEM                1802 kB   w 57 żądaniach

wczytanie do końca   1144 ms    (DOM gotowy 627 ms)
wysokość strony      5413 px    (bez rozwiniętych kart)
nagłówki             h1: 1, h2: 1, h3: 0
```

---

## A. PRZEKAZ — co zostało z naszego języka

### A1. Pierwsza linia strony to żargon

`SKAN RYNKÓW · PIŁKA KLUBOWA 2026/27` — „skan rynków" to nazwa naszego
procesu. To pierwszy napis nad nagłówkiem, czyli najlepsze miejsce na
powiedzenie, czym to jest.

*Propozycja:* `TYPY NA DZIŚ · PIŁKA KLUBOWA 2026/27`.

### A2. „SKAN NA ŻYWO" w pasku pod nagłówkiem

To samo słowo, druga sztuka. Pasek pokazuje przesuwające się typy.

*Propozycja:* `DZIŚ TYPUJEMY` albo `NA ŻYWO` bez „skanu".

### A3. „SZANSA MODELU" na kuponie, „model daje 40%" w torze

Konsekwentnie mówimy „nasza szansa" wszędzie indziej. Te dwa miejsca zostały.

### A4. `<title>` strony: „FootStats – okazje na statystyki piłkarskie"

„Okazje na statystyki" nie znaczy nic dla nikogo spoza branży. To pierwsza
rzecz w zakładce przeglądarki i w linku wysłanym znajomemu.

*Propozycja:* „FootStats — typy na mecze piłkarskie, liczone ze statystyk".

### A5. „NASZ TYP NA DZIŚ" nad kartą, która rotuje 1 z 4

Etykieta obiecuje jeden typ, licznik obok pokazuje cztery. Drobiazg, ale
czytelnik zauważa go w pierwszych sekundach.

*Propozycja:* `NASZE TYPY NA DZIŚ` i licznik zostaje.

### A6. Karta drabinki: „drugi szczebel 52%" i „7/10 ostatnich"

„Szczebel" to nasze słowo na poprzeczkę drabinki. „7/10 ostatnich" bez
jednostki — siedem z dziesięciu czego?

*Propozycja:* „przebił w 7 z 10 ostatnich meczów" (pełne zdanie zamiast
plakietki) i „druga poprzeczka" zamiast „drugi szczebel".

### A7. „gra śr. 76 min"

Skrót w miejscu, gdzie zmieściłoby się „średnio 76 minut na mecz".

---

## B. WYGLĄD — gdzie strona wygląda jak szablon

### B1. ⚑ Pięć kart o identycznej wadze

Największy problem wizualny. Lista drabinek to pięć białych prostokątów
w tym samym rytmie, tej samej wielkości, z tą samą ramką. Ranking istnieje
(sortowanie „najlepsze typy"), ale **nie widać go**: karta pierwsza wygląda
dokładnie tak samo jak piąta.

Tak wyglądają listy generowane automatycznie — i to jest dokładnie ten
„AI slop", o którym mówisz. Produkt, który ma opinię, pokazuje ją układem.

*Propozycja:* pierwsza karta większa i wyróżniona (jak „polecany" plan
w cenniku): grubsza ramka, tło marki, plakietka „nasz typ numer 1", większa
czcionka nazwiska. Pozostałe zostają jak są. Jedna zmiana, a lista przestaje
być szeregiem.

### B2. Brak oddechu między sekcjami

Hero → pasek → lista → most do drużyn → dwa kafelki → stopka. Wszystko na
tym samym jasnym tle, w tej samej szerokości, z tym samym odstępem. Strona
czyta się jak jeden ciąg.

*Propozycja:* sekcja z dwoma kafelkami na tle o ton ciemniejszym (mamy już
`bg-card-soft`), oddzielona pełną szerokością. Zero nowych kolorów.

### B3. Ramki w ramkach

Karta drabinki: ramka karty → w środku ramka tabelki kursów → w środku
ramka wybranej poprzeczki. Trzy poziomy obramowań na 300 px wysokości.

*Propozycja:* tabelka kursów bez własnej ramki, oddzielona samą przerwą.

### B4. Hero jest jedynym miejscem z charakterem

Celownik z narożników wokół karty to najlepszy element wizualny na stronie.
Nic poniżej nie ma nic równie własnego — dalej jest już tylko typografia.

*Propozycja:* powtórzyć motyw narożników przy pierwszej karcie listy (patrz
B1) — ten sam znak, drugi raz, i strona ma swój język zamiast jednego
ładnego akcentu.

---

## C. TECHNIKA

### C1. ⚑ JavaScript waży 912 kB

Największa pozycja w 1,8 MB strony. Sam React to 221 kB, reszta to nasze
komponenty klienckie i `framer-motion` (animacje: Hero, Reveal, ValueBoard,
Nav, KuponAnim).

To nie jest awaria — strona wstaje w 1,1 s lokalnie. Ale na telefonie
w terenie te 912 kB to realna sekunda różnicy.

*Propozycja do rozważenia (większa robota):* `framer-motion` jedzie dziś
w każdą stronę. Animacje wejścia (`Reveal`) da się zrobić czystym CSS-em,
a rotacja karty w hero to jedyne miejsce, gdzie biblioteka naprawdę pracuje.
Zysk rzędu 100–150 kB.

### C2. Płaska hierarchia nagłówków (h1: 1, h2: 1, h3: 0)

Pięć kart drabinek nie ma żadnego nagłówka — nazwisko zawodnika to `<p>`.
Dla kogoś, kto czyta stronę czytnikiem ekranu, lista typów nie istnieje jako
struktura. To też sygnał jakości kodu, nie tylko dostępności.

*Propozycja:* nazwisko na karcie jako `<h3>`, nagłówki sekcji jako `<h2>`.
Zero zmian wizualnych.

### C3. 57 żądań na jedno wejście

Dużo jak na stronę, która pokazuje jedną listę. Głównie chunki JS.

---

## D. STANY, KTÓRYCH NIE WIDZIELIŚMY

### D1. Zero typów i zero drabinek naraz

Dziś: 0 zawodniczych, 10 drabinek. Jeśli oba wyjdą puste (zdarzy się przy
kwarantannie albo w przerwie między kolejkami), strona główna zostaje
z samym hero i mostem do drużyn. Nie wiem, jak to wygląda — nie było okazji
zobaczyć.

*Do zrobienia:* zrzut z pustą listą (da się wymusić lokalnie na danych demo).

### D2. Brak kuponu dnia

Kafelek kuponu znika, a kafelek wyników zostaje sam w siatce dwukolumnowej
— czyli pół ekranu pustki. Tego też nie widzieliśmy.

---

## Kolejność, którą proponuję

1. **B1 + B4** — pierwsza karta wyróżniona. Największa zmiana wrażenia
   przy najmniejszym ryzyku; to ona odróżnia produkt od listy z generatora.
2. **A1–A7** — reszta żargonu. Tanie, pewne, robione jednym przejściem.
3. **C2** — nagłówki. Zero zmian wizualnych, porządek w kodzie.
4. **B2 + B3** — oddech między sekcjami i mniej ramek.
5. **D1 + D2** — obejrzeć puste stany i dopiero wtedy je poprawiać.
6. **C1** — framer-motion. Osobna sesja, bo dotyka każdej strony.
