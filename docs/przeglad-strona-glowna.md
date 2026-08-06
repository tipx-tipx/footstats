# Strona główna — przegląd element po elemencie

Data: 2026-08-06. Stan strony: cykl 12:13, **zero typów zawodniczych**,
20 drużynowych, 8 drabinek. Zrzuty: `web/zrzuty/start-rozwiniete--*.png`.

Cztery pytania do każdego elementu: **działa** (czy nie kłamie, czy znosi
pustkę) · **zrozumiałe** (czy ktoś bez wiedzy o zakładach wie, co czyta) ·
**wygląda** (czy to nasz język wizualny) · **sprzedaje** (czy kupujący
rozumie, za co płaci).

Numeracja jest stała — będę się do niej odwoływał przy wdrażaniu.

---

## A. Pasek na górze (Nav + SwiezoscDanych)

### A1. ⚑ Wskaźnik świeżości alarmuje przy NORMALNEJ pracy — najważniejsze

Progi: świeże < 45 min, opóźnione 45–120, stare > 120. **Zmierzone dziś na
104 publikacjach z ostatniego tygodnia** (`opublikowano_ts` z księgi):

```
mediana odstępu cykli   67 min
średnia                 92 min
odstępów > 45 min       71 ze 102  (70%)
odstępów > 120 min      24 ze 102  (24%)
```

Czyli kupujący widzi żółte **„dane opóźnione"** w 70% wejść i czerwone
**„dane stare"** w co czwartym. Alarm, który świeci prawie zawsze, przestaje
być alarmem — a przy pierwszym kontakcie wygląda jak produkt, który się psuje.

*Propozycja:* progi z pomiaru, nie z założenia: świeże < 90 min, opóźnione
90–180, stare > 180. Do tego zdanie w dymku: „przeliczamy mniej więcej co
godzinę". Alternatywa mocniejsza: pokazywać kolor dopiero, gdy dane są starsze
niż typowy odstęp × 2.

### A2. Dwa sprzeczne komunikaty o tej samej rzeczy

W pasku: „dane opóźnione · 56 minut temu" (żółty). Dwa centymetry niżej,
w nagłówku: „żywe dane · 12:13" (zielona kropka). Ta sama informacja, dwa
różne wnioski.

*Propozycja:* jedno źródło prawdy. W hero zostaje sama godzina bez oceny
(„ostatnie przeliczenie 12:13"), ocena tylko w pasku.

### A3. Nazwa zakładki „Zawodnicy" przy zerze typów zawodniczych

Decyzją z 05.08 nazwa zostaje (mają tam być wysokie szanse i drabinki) —
ale dziś ta zakładka nie ma ani jednego zawodnika w części „Wysokie szanse",
a jedyna widoczna zakładka wewnętrzna to „Drabinki".

*Do decyzji:* nie ruszam nazwy bez Twojego słowa. Warto rozważyć podpis pod
nazwą w nawigacji albo dopuszczenie, by przy zerze typów zawodniczych strona
sama się przedstawiała jako „Drabinki i wysokie szanse".

---

## B. Nagłówek strony (Hero)

### B1. Karta „namierzone przez skan" mówi żargonem

Etykieta rotującej karty: **„NAMIERZONE PRZEZ SKAN · 2 z 4"**. „Namierzone"
i „skan" to nasze wewnętrzne słowa. Kupujący nie wie, czy to coś dobrego.

*Propozycja:* „typ 2 z 4 — nasze najlepsze na teraz".

### B2. „+81,0% bukmacher przepłaca" bez kontekstu

Liczba jest prawdziwa w naszej arytmetyce (kurs wycenia 27%, model daje 55%),
ale dla kupującego brzmi jak obietnica 81% zysku. Nie ma nigdzie zdania, że
to **nasza ocena**, a nie fakt o bukmacherze.

*Propozycja:* podpis pod liczbą: „tyle wychodzi z naszej szansy — im wyżej,
tym większa różnica zdań z bukmacherem". Rozważyć sufit wyświetlania:
powyżej ~40% liczba przestaje być wiarygodna i lepiej ją opisać słowem.

### B3. ⚑ Karta promuje typ z pasma, o którym wiemy, że traci

Dziś w hero: Hapoel Tel Aviv, model daje **55%** — czyli dolna granica pasma
55–70%, które w pomiarze z tego samego dnia ma **ROI −19,9%** na 152
rozliczeniach (patrz `docs`/pamięć: „gdzie tracimy"). Kafelek wybiera po
wartości netto, więc systematycznie wynosi na górę typy z najgorszego pasma:
im większa rozbieżność z kursem, tym wyżej trafia typ.

*To jest decyzja produktowa, nie kosmetyka.* Propozycja: karta hero wybiera
z pasm, które w pomiarze wychodzą na plus (deklaracja < 55% albo > 70%),
zamiast po samej wartości netto. Do zrobienia razem z decyzją o korekcie
po 12.08.

### B4. Pasek konkretów — po dzisiejszej zmianie zostaje „20 na drużyny"

Działa. Zostało jedno: „przeliczane co godzinę" stoi obok wskaźnika, który
mówi „opóźnione" po 45 minutach — patrz A1, to ta sama sprzeczność.

### B5. Pasek skanu pokazuje pięć razy ten sam zakład

„Ljungskile gole poniżej 0,5 @3,60 · Motor Lublin gole poniżej 0,5 @3,55 ·
Santos gole poniżej 0,5 @3,55 · Górnik Zabrze gole poniżej 0,5…" — pierwsze,
co widzi kupujący, to wrażenie, że model umie jedną rzecz.

*Propozycja:* pasek pokazuje najwyżej dwa typy z tej samej pary
(rynek, strona), resztę dobiera z innych rynków. To NIE jest zmiana reguł
publikacji — sama kolejność w pasku.

---

## C. Lista (ValueBoard)

### C1. Jedna zakładka w pasku zakładek

Przy zerze typów zawodniczych zostaje sama „DRABINKI 8". Pasek z jedną
pozycją wygląda jak niedokończony interfejs.

*Propozycja:* gdy zostaje jedna zakładka, zamiast paska pokazać nagłówek
sekcji („Drabinki — 8 kart na dziś").

### C2. Rozwinięta karta drabinki ma ~1000 px na telefonie

Cztery rozwinięte karty = **7653 px** strony. Sekcje w rozwinięciu:
„skąd ta liczba", „co zmienia ten mecz", „jak było ostatnio", „gdzie jest
przewaga", „szczegóły techniczne". Treść jest dobra — jest jej po prostu
tyle, że nikt nie dojdzie do końca.

*Propozycja:* „jak było ostatnio" (lista 10 meczów) i „szczegóły techniczne"
domyślnie zwinięte wewnątrz rozwinięcia. Zostają dwa akapity, które
tłumaczą typ, reszta na klik.

### C3. Sekcja „gdzie jest przewaga" mówi o Betclicu

„…albo Betclic nie prowadzi tego meczu, albo nie wystawił tego rynku".
Kupujący nie wie, czym jest Betclic ani dlaczego ma go obchodzić.

*Propozycja:* mówić rolą, nie nazwą: „drugi bukmacher nie wystawił tego
rynku, więc nie mamy z czym porównać naszej wyceny".

### C4. Filtry — po dzisiejszej zmianie chowają się przy krótkiej liście

Działa. Warto sprawdzić to samo na zakładce Drabinki (ma osobne sortowanie,
zawsze widoczne, nawet przy 8 kartach — tam jest OK).

---

## D. Most do drużyn

### D1. Działa i jest potrzebny

„Model ma dziś także 20 typów drużynowych (gole, rożne i kartki całych
drużyn) → Zobacz drużyny". Po dzisiejszej zmianie liczba jest też klikalna
w hero. Bez zastrzeżeń.

---

## E. Dwa kafelki na dole

### E1. ⚑ „Jak trafia model" pokazuje 58% i ani słowa o pieniądzach

Kafelek: „ostatni dzień 12/16 · łącznie 420/721 · trafialność 58%".
Kupujący czyta 58% jako sukces. Tymczasem ROI całego zbioru jest **ujemny** —
58% trafień przy tych kursach to strata. Nigdzie na stronie głównej nie ma
tej informacji; jest dopiero w Skuteczności.

*To jest najpoważniejszy zarzut wobec uczciwości strony głównej.* Propozycja:
dołożyć trzecią liczbę „z 10 zł zostaje X zł" — dokładnie tę samą, którą
kafelek kuponu już pokazuje obok. Dwa kafelki stoją ramię w ramię i jeden
mówi o złotówkach, a drugi o procentach.

### E2. Kupon dnia — spójny

„×2,01 · szansa modelu 63% · z 10 zł robi się 18 zł" + trzy legi. Ton w
porządku (patrz przegląd tonu z 06.08). Bez zastrzeżeń.

---

## F. Stopka

### F1. Nazwy techniczne źródeł

„DANE: statshub (statystyki i historia) + Superbet (kursy)". „statshub" to
nazwa API, nie marka, którą ktokolwiek zna.

*Propozycja:* „skąd bierzemy dane: statystyki meczów z bazy statystycznej,
kursy z Superbetu".

### F2. „MECZÓW W BAZIE 163" bez kontekstu

163 czego? Dziś? W sezonie? Do wyboru?

*Propozycja:* „mecze, które dziś przeliczyliśmy: 163".

---

## Kolejność, którą proponuję

1. **A1 + A2** — wskaźnik świeżości. Dotyczy KAŻDEJ strony, ma twardy pomiar
   i psuje pierwsze wrażenie najbardziej.
2. **E1** — trafialność bez pieniędzy. Uczciwość wobec kupującego.
3. **B1, B2, C3, F1, F2** — teksty i żargon, tanie i pewne.
4. **B5, C1, C2** — wygląd i długość.
5. **B3** — wybór typu do hero; czeka na decyzję o korekcie po 12.08.
