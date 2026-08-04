# Przegląd całości pod sprzedaż — backend, front, dane, sprzedaż

**Data:** 2026-08-04 · **Zakres:** cały system — 21 000 linii backendu,
~12 000 linii frontu, baza, cron, źródła danych, wszystkie zakładki.

**Cel ustalony z userem:** przekaz zgodny z rzeczywistością, typy maksymalnie
dopracowane, jak najwięcej trafień, **bez chaosu i bez przesytu**. Teksty
zrozumiałe dla kogoś, kto nie zna zakładów. Widok KLIENTA ważniejszy niż admina.

**Jak czytać:** każde znalezisko ma wagę i zdanie „co to zmieni".
**[1]** blokuje sprzedaż · **[2]** psuje wrażenie · **[3]** szlif

---

# CO JUŻ NAPRAWIONE (2026-08-04, po przeglądzie)

| co | stan | efekt |
|---|---|---|
| „Moje zakłady" | **usunięte** | zakładka, strona, przycisk na karcie, `tracker.ts`, `BetTracker.tsx`. Zagrane KUPONY zostają — to osobny mechanizm |
| Sumy meczowe i „kto więcej" nie trafiały do puli kuponów | **naprawione** | 12 typów o szansie 74–91% (kartki meczowe, gole) dostępnych dla kuponów; wcześniej pula miała średnią szansę 59% wobec 71% na liście |
| 79 cichych połknięć błędu | **25 załatanych** | licznik `footstats/diagnostyka.py` + raport w logu cyklu i w `meta.ciche_bledy` |

**Które ciche błędy załatane** — wyłącznie te, które gubią DANE, nie pojedyncze
pola: historia drużyny i zawodnika (statshub), shotmapy, wyniki meczów,
rozliczanie strzałów i statystyk (365scores), dni terminarza, skan rozgrywek,
bank stylu, profil sędziego, linie kursowe (Superbet), dociąganie kursów do
puli, szukanie meczu przy rozliczaniu, pobranie Elo. Reszta (54) to parsowanie
pojedynczych pól i moduły martwe (`sofa_worker`) — tam licznik by się nie zwrócił.

**Elo dostało osobny licznik wieku cache** — skoro dane mają 18 dni, cykl ma
teraz powiedzieć wprost `elo:cache_starszy_niz_18dni` zamiast po cichu wozić
stare ratingi.

---

# CZĘŚĆ I — BACKEND

## 1.1. Czy model jest dobrze zbudowany? TAK.

To trzeba powiedzieć na wstępie, bo reszta tej części to lista usterek i można
odnieść mylne wrażenie. Rdzeń modelu jest zrobiony porządnie:

* **Rozkład liczby zdarzeń, nie punktowa liczba.** Gamma-Poisson z wygaszaniem
  czasowym; im mniejsza próba, tym szersze ogony (ujemny dwumianowy).
  To jest właściwe narzędzie do „ile strzałów odda zawodnik".
* **Minuty jako mieszanka scenariuszy** (pełny mecz / zejście w 70' / wejście
  z ławki / nie zagra), a nie jedna liczba. Po ogłoszeniu składów scenariusze
  się upraszczają.
* **Kartki liczone warstwowo przez faule** (`P = 1 − exp(−λ_fauli × q_zawodnika
  × m_sędziego)`), bo bezpośrednich kartek jest za mało na zawodnika.
* **Tempo meczu wyciągane z kursów 1X2** — czyli z najefektywniejszego
  dostępnego sygnału, nie z własnego zgadywania.
* **Profil rywala per rynek** — ile drużyna dopuszcza danej statystyki.

**Wniosek:** problemem nie jest architektura modelu, tylko *kalibracja*
(deklaruje 70%, trafia 58%) i *podaż* (dziś załatana).

## 1.2. Ciche połykanie błędów — 79 miejsc

**[1] To jest najpoważniejsza rzecz w całym backendzie.**

Policzone: **79 miejsc**, w których wyjątek jest łapany i zamieniany na `pass`,
`continue`, `return None`, `return []` — **bez jednej linii logu**. Rozkład:

```
build_wc_fast.py   13   główny cykl
scores365.py       13   źródło wyników
statshub.py         8   GŁÓWNE źródło statystyk i historii
sofa_worker.py      7   (worker odpuszczony świadomie)
betclic.py          4   drugi bukmacher
superbet.py         2   źródło kursów
rozliczanie.py      4
pozostałe          28
```

**Co to znaczy po ludzku:** jeśli statshub odpowie błędem, funkcja zwraca pustą
listę i cykl leci dalej, jakby zawodnik po prostu nie miał historii. Nikt się
nie dowie, że dane przepadły. **Dokładnie tak wyglądały wszystkie cztery błędy,
które znaleźliśmy dziś** (kartki gubione u obu bukmacherów, historia ucięta do
10 meczów, mecze znikające z terminarza, sumy meczowe omijające kwarantanny) —
każdy z nich to było ciche odrzucenie danych.

**Rekomendacja:** licznik przy każdym `except`. Nie trzeba logować każdego
wyjątku osobno — wystarczy zliczać per moduł i wypisywać na koniec cyklu jedną
linią: „statshub: 47 cichych błędów (timeout 31, parse 16)". Jeśli liczba
skoczy, od razu widać.

**Co to zmieni:** przestaniemy znajdować takie błędy przypadkiem raz na
tydzień. To jest różnica między „naprawiamy, gdy user zauważy" a „widzimy,
zanim zauważy".

## 1.3. Martwe i zamarłe źródła danych

Sprawdzone stemplami **w środku** danych (nie `updated_at`, które kłamie):

| źródło | ostatnie dane | stan |
|---|---|---|
| `statshub` (statystyki, historia) | 1 h temu | **żyje** |
| `superbet` (kursy) | 1 h temu | **żyje** |
| `betclic` (druga cena drabinek) | bieżący cykl | **żyje** |
| `sts_value` (kursy STS) | **187 h temu** (7,8 dnia) | **zamarłe** |
| `sofa_results` (Sofascore) | 242 h temu | martwe, świadomie |
| `elo_ratings` | **430 h temu** (18 dni) | **zamarłe** |

* **[2] STS nie działa od 27 lipca.** Kod `sts_value.py` (442 linie) jest
  wołany w cyklu, ale nie produkuje świeżych danych. Front ma dla niego osobną
  ścieżkę (`StsBetCard.tsx`, 450 linii) i etykietę „kurs w STS". Czyli jest
  zakładka funkcji, która od tygodnia pokazuje wyłącznie stare rzeczy albo nic.
* **[2] Elo sprzed 18 dni.** Elo zasila profil rywala (`koncesje.py`). Zmienia
  się wolno, więc to nie katastrofa — ale po 18 dniach transferów i formy to
  już nie jest „siła drużyny dziś".

**Rekomendacja:** zdecydować dla każdego: naprawiamy, czy usuwamy razem z UI.
Zamarłe źródło, które zostaje w kodzie, to najgorszy wariant — udaje, że działa.

## 1.4. Testy — 702 zielone, ale siedem modułów bez ani jednego

Bez pokrycia: `cycle` (orkiestrator całego crona!), `sts_value`, `build_wc`,
`kalibracja_tau`, `napraw_rozliczenia`, `backfill`, `wc_auto`.

* **[2] `cycle.py` bez testu** — to jest plik, który w chmurze uruchamia
  wszystko. Ma dobre zabezpieczenia (wykrywa nieudany push i wywala job), ale
  nikt tego nie sprawdza automatycznie.
* **[3] Docstring `cycle.py` kłamie:** „Uruchamiany co ~30 min przez Windows
  Task Scheduler". W rzeczywistości chodzi w GitHub Actions co 15 min. Ktoś,
  kto to przeczyta, zacznie naprawiać nieistniejący lokalny cron.

## 1.5. Cron i świeżość

* Deklaracja: co 15 minut. Cykl trwa **17–20 minut** i rośnie z zakresem lig.
* Jest `concurrency`, więc przebiegi się nie nakładają — **to jest zrobione
  dobrze**. Ale kolejny cykl czeka, aż poprzedni skończy, więc realna
  częstotliwość to ~20 min w najlepszym razie, a w praktyce bywa 1–1,5 h.
* **[1] Strona obiecuje „żywe dane", a bywa godzinę nieświeża i nie ma jak
  tego zauważyć.** W stopce jest „AKTUALIZACJA 13:19" — ale to jedyny ślad,
  napisany najmniejszą czcionką na stronie.

**Rekomendacja:** wskaźnik świeżości przy typach: świeże (<30 min) / opóźnione
(30–90 min) / stare (>90 min), plus czas ODCZYTU OFERTY, a nie zapisu do bazy.
**Co to zmieni:** klient, który stawia pieniądze, musi wiedzieć, czy kurs sprzed
godziny jeszcze istnieje. Dziś dowiaduje się o tym u bukmachera.

## 1.6. Dwa monolity

`build_wc_fast.py` — **6000 linii**. `rozliczanie.py` — **4016 linii**.
Razem połowa całego backendu w dwóch plikach.

* **[2]** Nazwa `build_wc_fast` znaczy „build World Cup fast" — mundial
  skończył się 19 lipca, a plik obsługuje ligę. Nazwa myli przy każdym wejściu.
* **[3]** Praktyczny skutek: każda zmiana w publikacji wymaga czytania 6000
  linii, żeby znaleźć właściwe z czterech miejsc. Dziś kosztowało to nas błąd
  (sumy meczowe omijały bramy, bo dopisywały się osobną ścieżką).

**Rekomendacja:** nie przepisywać wszystkiego. Wyciągnąć jedną rzecz —
**publikację** (kto wchodzi na listę i dlaczego) — do osobnego modułu z
testami. To jest miejsce, które zmienialiśmy dziś cztery razy.

## 1.7. Baza danych

* **[2] Migracja 0001 to 300 linii martwego schematu.** Tabele `predictions`,
  `odds_snapshots`, `value_bets`, `bet_log`, `model_runs`, `shot_events`,
  `market_defs`, `calibration_reports` — **żadna nie jest używana**. Cały system
  jedzie na jednej tabeli `app_data` (klucz → JSON).
  **Co to zmieni:** ktoś nowy (albo my za miesiąc) zacznie od tego schematu
  i zbuduje coś, co nie ma połączenia z rzeczywistością.
* **[1] `app_data` ma politykę odczytu `using (true)`** — czyli kto ma klucz
  anonimowy, czyta **wszystko**: całą księgę typów (1,7 MB), bank stylu
  (5,4 MB), rejestr odrzuceń, diagnostykę. Klucz jest dziś tylko po stronie
  serwera, więc nie wycieka — ale to jedna zmienna środowiskowa od katastrofy.
  **Rekomendacja:** rozdzielić klucze publiczne (to, co i tak widać na stronie)
  od wewnętrznych (księga, bank, diagnostyka).

## 1.8. Wydajność

* **[2] Strona ciągnie z bazy ~4 MB jednym zapytaniem**, a Next cache'uje do
  2 MB — więc ten odczyt **nie jest cache'owany w ogóle**. Największe pozycje:
  `players` 2,1 MB, `typy_log` 1,7 MB.
  **Co to zmieni:** każde wejście na stronę to pełne 4 MB z bazy. Przy jednym
  użytkowniku nieważne; przy stu — to jest rachunek i wolna strona.

---

# CZĘŚĆ II — FRONT, ZAKŁADKA PO ZAKŁADCE

## 2.1. STRONA GŁÓWNA („Zawodnicy", `/`)

* **[1] Nazwa zakładki kłamie o zawartości.** Nazywa się „Zawodnicy", a przy
  dzisiejszej podaży pokazuje 10 kart drabinek i 1 typ zawodniczy. Domyślnie
  otwiera się wewnętrzna zakładka „Drabinki" (bo żaden typ nie ma flagi
  `pewniak`) — pierwsze, co widzi kupujący, to nie jest to, po co przyszedł.
* **[1] Kafelek „pierwszy typ z listy" pokazuje typ, którego na tej liście
  nie ma** — bo lista jest przefiltrowana na drabinki.
* **[2] Nagłówek „Model, który typuje za Ciebie" nie mówi, co dostaniesz.**
  Brak zdania: „X typów dziennie na Y lig, aktualizowane co godzinę".
* **[2] Przycisk „ZOBACZ 1 OKAZJĘ"** przy 19 typach drużynowych obok.
* **[2] Słowo „drabinki" nigdzie nie wyjaśnione.** Dla laika nie znaczy nic.
* **[2] Karta drabinki jest ogromna** — dziesięć takich to ~4000 px przewijania.

## 2.2. DRUŻYNY (`/druzyny`)

* **[1] Legenda tłumaczy żargon żargonem:** „KROPKA = PRZEWAGA W KURSIE ·
  duża przewaga / przewaga / cienka przewaga". To jedyne miejsce, które ma
  wyjaśnić symbol, i samo wymaga wyjaśnienia.
* **[2] Brak nagłówków kolumn.** Wiersz to: nazwa → rynek → pasek → `91%` →
  `1,34`. Nigdzie nie napisano, że pierwsza liczba to szansa, a druga kurs.
* **[2] Podwójny licznik typów** w nagłówku dnia („4 typy" dwa razy pod sobą).
* **[2] Przesyt jednego rynku:** na 19 typów sześć to „kartki w meczu poniżej",
  trzy „kartki drużyny". Prawie połowa listy to jeden pomysł w wariantach.
  **To jest dokładnie „przesyt", o którym mówiłeś.**
* **[2] Dziś 3 typy, jutro 4, a czwartek 10.** Użytkownik wchodzi po typy na
  dziś i dostaje najmniej.
* **[2] „12 częściej wchodzą · 7 więcej płacą"** — nazwy półek użyte jak liczby,
  bez wyjaśnienia różnicy.
* **[3] „materiał na kupon", „kurs to wynagradza", „komplet historii"** —
  żargon w zdaniach, które mają tłumaczyć.

## 2.3. KUPONY (`/kupony`)

* **[1] „NA DZIŚ — 0".** Zakładka, po którą przychodzi najwięcej ludzi, jest
  pusta. Z trzech kategorii działa jedna, z jednym kuponem.
* **[1] „Z PRZEWAGĄ — 0"** — druga pusta.
* **[1] „Ostatnio trafione" pokazuje sześć kuponów i wszystkie trafione.**
  Wygląda jak witryna oszusta. Link do pełnego bilansu jest, ale pierwsze
  wrażenie jest nieprawdziwe — a chcemy przekazu zgodnego z rzeczywistością.
  **Rekomendacja:** pokazywać ostatnie N kuponów **z wynikiem, jaki był** —
  trafione i nietrafione. Uczciwe „4 z 6" buduje więcej zaufania niż „6 z 6".
* **[1] Ostrzeżenie o składach na kuponie z typami DRUŻYNOWYMI.** „Jeśli
  zawodnik siedzi na ławce, jego typ wypadnie" — a kupon zawiera „gole
  drużyny", gdzie skład tak nie działa.
* **[1] Kupon ma ujemną wartość oczekiwaną.** Kurs 2,54 przy szansie 31%
  (0,31 × 2,54 = 0,79 — czyli z każdej złotówki statystycznie zostaje 79 gr).
  Generator własny: 19% przy ×4,71 = 0,89. Brama „nie publikujemy kuponu
  o ujemnej wartości" jest w projekcie opisana jako rekomendowana i niezrobiona.
* **[2] Suwak kursu z dwoma nieaktywnymi przedziałami** („bliżej meczów").

## 2.4. MECZE (`/mecze`)

* **[1] 112 meczów, ~8300 px przewijania**, zdecydowana większość z etykietą
  „bez przewagi". Szukanie igły w stogu siana.
  **Rekomendacja:** domyślnie pokazywać tylko mecze z typami, a resztę schować
  za „pokaż wszystkie 112".

## 2.5. MOJE ZAKŁADY (`/zaklady`)

* **[1] Dane w przeglądarce (localStorage).** Klient zapłaci, zaloguje się
  z telefonu i nie zobaczy nic z tego, co dodał na laptopie. Wyczyści historię
  przeglądarki — traci wszystko. **Dla produktu płatnego to wada blokująca.**
* **[1] Wstęp tłumaczy CLV, nie mówiąc, co user ma zrobić:** „wpisz kurs, jaki
  był tuż przed pierwszym gwizdkiem – pokażemy, czy łapiesz lepsze kursy niż
  reszta rynku". Trzy niezrozumiałe pojęcia w jednym zdaniu, plus praca, której
  sensu laik nie rozumie.

## 2.6. SKUTECZNOŚĆ (`/model`)

**Widok klienta jest tu WZOREM dla całej strony** i to trzeba powiedzieć
wprost: tytuł „Co z tego wyszło", liczby w **złotówkach** (−1411 zł zamiast
−141,09u), zdanie „grając po 10 zł na każdy z 681 typów miałbyś dziś −1411 zł",
pole **„przelicz na moją stawkę"**, kalendarz z kwotami dnia. Tak ma wyglądać
reszta produktu.

* **[1] Kod rynku w polskim zdaniu:** „Wstrzymane właśnie są: rzuty rożne
  drużyny, **match_corners**, najwyższa szansa w meczu".
* **[2] Widok admina to ściana liczb** — pięć kafelków, wykres, kalendarz,
  tabela dnia, cztery tabele uczenia. Dla nas bezcenne, dla kupującego nie.

### Sprawdzone i POPRAWNE (nie ruszać)
* Kalendarz: 1 i 2 sierpnia w kolumnach SO/ND — układ tygodnia się zgadza.
* Krzywa wyniku pokazuje **−118,82u** na czerwono, zgodnie z bilansem.
* Wyjaśnienie „22 poprzeczki, ale 15 zakładów" — wzór zdania, którego brakuje
  w innych zakładkach.

> **METODA — dwa błędne odczyty tego samego dnia.** Zrzut o wysokości 4000+ px
> jest pokazywany pomniejszony ~2,2×; przy tej skali minus zlewa się z tłem,
> a etykiety sekcji stają się nieczytelne. Wziąłem drabinki za typy i „zobaczyłem"
> zgubiony minus, którego nie ma. **Każde znalezisko oparte na drobnym tekście
> potwierdzać wycinkiem w pełnej skali**, zanim trafi na listę.

## 2.7. JAK TO DZIAŁA (`/jak-to-dziala`)

* **[1] Deklaruje „bez żargonu" i natychmiast go używa:** „predykcja",
  „rozkład", „marża", „odwrotność szansy", „wartość dodatnia w długiej serii".
* **[2] Dziesięć kroków ściany tekstu.** Nikt rozważający zakup tego nie
  przeczyta. Potrzebna wersja w trzech zdaniach + rozwinięcie dla chętnych.
* **[2] Zero ilustracji** — a kroki 5–6 (szansa → uczciwy kurs → porównanie
  z bukmacherem) aż proszą się o jeden rysunek.

## 2.8. STRONA MECZU (`/mecze/[id]`)

Najbogatsza strona w całym produkcie — i najbardziej ryzykowna.

* **[1] „TOP POKRYCIA — 37 propozycji" z kolumną WARTOŚĆ pokazującą +48%,
  +47%, +52%.** To NIE jest wycena modelu. Nagłówek tłumaczy drobnym drukiem:
  „+% = ile płaci kurs względem pokrycia (zgrubnie, próba 5)" — czyli to surowe
  porównanie kursu z tym, ile razy zawodnik przebił linię w **pięciu** ostatnich
  meczach. Model tych typów **nie wystawił** (gdyby wystawił, byłyby na liście).
  **Ryzyko:** ktoś zobaczy „+52%" i uzna to za okazję życia, choć to jest
  liczba z pięciu meczów bez kontekstu rywala, minut i kalibracji.
  **Rekomendacja:** albo nazwać kolumnę uczciwie („kurs vs 5 ostatnich meczów —
  to nie jest nasza wycena"), albo pokazywać obok wycenę modelu, gdy istnieje.
* **[2] Generator kuponu na mecz wita komunikatem „Ten zestaw się nie składa".**
  Domyślne ustawienia (kurs ×4,00, min. 3 typy) nie mają pokrycia w puli tego
  meczu. Użytkownik widzi błąd, zanim czegokolwiek dotknie. Jest przycisk
  „dopasuj kurs do puli" — powinien być zastosowany domyślnie.
* **[3] „2 OKAZJI MODELU"** — zła odmiana, ma być „2 okazje".
* **Dobre, zostawić:** „Czego nie typujemy w tym meczu i dlaczego — 58
  sprawdzonych bez typu". To jest uczciwość, która buduje zaufanie.

## 2.9. EKRAN LOGOWANIA (`/login`)

* **[1] Napis „NARZĘDZIE PRYWATNE".** To pierwsza rzecz, jaką zobaczy ktoś,
  kto ma zapłacić — i mówi mu, że trafił nie tam, gdzie trzeba.
* **[1] Brak jakiejkolwiek informacji, czym to jest i jak kupić dostęp.**
  Jest logo, „podaj hasło" i pole. Nikt, kto nie zna hasła, nie ma żadnej
  ścieżki dalej.
* **[2] Karta wisi w pustce** — na laptopie zajmuje 1/4 ekranu, reszta pusta.

## 2.10. Telefon — audyt automatyczny CZYSTY

`npm run audyt` na 390 px: **żadna strona nie ucieka w bok.** Wykryte przesuwy
poziome (paski filtrów lig, zakładki dni, tabele uczenia) są celowe i skrypt
je odróżnia. To znaczy, że układ mobilny jest zdrowy — problemem na telefonie
jest treść i długość, nie łamanie się layoutu.

## 2.11. Przekrojowe (wszystkie zakładki)

* **[1] Nigdzie nie napisano, CO KUPUJĄCY DOSTAJE** — ile typów dziennie,
  z jakich lig, o jakich porach, jak często odświeżane.
* **[1] Brak ceny, planu, przycisku zakupu.** Strona jest narzędziem, nie ofertą.
* **[2] Słowo „przewaga" w czterech znaczeniach** (przewaga w kursie, kropka
  przewagi, „bez przewagi", „typy z przewagą"). Dla laika to jedno słowo,
  które za każdym razem znaczy co innego.
* **[2] Godziny meczów bez strefy czasowej.**
* **[3] Stopka „Narzędzie analityczne, nie gwarantuje wygranych"** — dobre,
  zostawić.

---

# CZĘŚĆ III — CZEGO BRAKUJE, ŻEBY W OGÓLE SPRZEDAĆ

## 3.1. [1] Jedno hasło dla wszystkich klientów

Dziś dostęp to `APP_PASSWORD` (admin) i `KLIENT_PASSWORD` (klient). **Wszyscy
klienci dzielą jedno hasło.** Konsekwencje:

* nie da się odciąć jednego klienta, który przestał płacić, bez zmiany hasła
  wszystkim pozostałym,
* nie wiadomo, ilu ludzi korzysta ani kto,
* jeden klient może rozdać hasło dowolnej liczbie osób,
* nie da się zrobić okresu próbnego ani różnych planów.

**To jest twarda blokada sprzedaży** — nie kwestia wygody. Bez kont nie da się
prowadzić płatnego produktu.

**Rekomendacja:** konta (Supabase Auth ma to gotowe: e-mail + magic link).
Przy okazji rozwiązuje się „Moje zakłady" — historia idzie do bazy per konto,
a nie do przeglądarki.

## 3.2. [1] Brak rejestracji wejść

Nie wiemy, ile osób wchodzi, na które zakładki, gdzie odpadają. Sprzedaż bez
tego to sprzedaż po ciemku.

## 3.3. [1] Brak jakiejkolwiek obietnicy produktowej

Ktoś wchodzi i nie znajduje odpowiedzi na: *co dostanę, ile to kosztuje, czy
to działa, co mam zrobić jako pierwsze*. Cztery zdania na górze strony głównej
rozwiązują trzy z tych czterech.

---

# CZĘŚĆ IV — OD CZEGO ZACZĄĆ (kolejność wg zwrotu z pracy)

### Etap 1 — żeby było CO sprzedawać (1–2 dni)
1. **Kupony „na dziś" przestają być puste.** Dziś zakładka z największym
   ruchem świeci zerem. To pierwsza rzecz, którą widzi kupujący.
2. **Strona główna mówi, co dostajesz** — cztery zdania i licznik typów.
3. **Uczciwa historia kuponów** — pokazujemy trafione i nietrafione.
   Paradoksalnie **zwiększa** sprzedaż: „6 z 6" nikt nie kupuje, „4 z 6" tak.

### Etap 2 — żeby dało się kupić (2–3 dni)
4. **Konta zamiast wspólnego hasła** (Supabase Auth).
5. **„Moje zakłady" do bazy** — przy okazji kont.
6. **Cena i przycisk zakupu.**

### Etap 3 — żeby nie odpadli po tygodniu (2–3 dni)
7. **Wskaźnik świeżości danych** przy typach.
8. **Filtr „tylko mecze z typami"** na zakładce Mecze.
9. **Teksty na język ośmiolatka** — słownik pojęć, jedno znaczenie słowa
   „przewaga", nagłówki kolumn, „drabinki" wyjaśnione przy pierwszym użyciu.

### Etap 4 — żeby produkt się bronił liczbami (ciągłe)
10. **Liczniki przy 79 cichych połknięciach błędu** — koniec znajdowania luk
    przypadkiem.
11. **Brama na kupony o ujemnej wartości.**
12. **Kalibracja publikacyjna** — model uczy się na tym, co faktycznie
    publikujemy, a nie na wszystkim, co policzy. To jest największa rzecz
    modelowa i jedyna, która realnie ruszy trafność.
13. **Decyzja o zamarłych źródłach** (STS, Elo): naprawiamy albo usuwamy z UI.

---

---

# PODSUMOWANIE LICZBOWE

| obszar | sprawdzone | znaleziska [1] | [2] | [3] |
|---|---|---|---|---|
| Backend — model | rdzeń, 8 modułów | 0 | 2 | 1 |
| Backend — dane i błędy | 79 miejsc, 6 źródeł | 2 | 4 | 1 |
| Backend — infrastruktura | cron, baza, testy | 2 | 4 | 2 |
| Front — 9 zakładek | wszystkie + telefon | 11 | 15 | 6 |
| Sprzedaż | dostęp, oferta | 3 | 0 | 0 |
| **RAZEM** | | **18** | **25** | **10** |

**Stan zdrowia w skrócie:**
* Model — **dobry**, kalibracja słaba.
* Układ mobilny — **zdrowy** (audyt czysty).
* Bezpieczeństwo logowania — **solidne** (rate-limit, stałoczasowe porównanie),
  ale model dostępu (jedno hasło) blokuje sprzedaż.
* Teksty — **dobre tam, gdzie są przemyślane** (Skuteczność, „Jak to działa"
  co do treści), **żargonowe wszędzie indziej**.
* Największa dziura techniczna — **79 cichych połknięć błędu**.
* Największa dziura produktowa — **nie da się kupić dostępu**.

## Czego świadomie NIE robiłem
* Nie czytałem linia po linii `GeneratorKuponu.tsx` (1249) i `RadarCard.tsx`
  (1406) — przejrzane z zewnątrz, oba korzystają ze wspólnego słownika i mają
  parytet z backendem opisany w komentarzach. Bez zgłoszenia konkretnej wady
  czytanie 2600 linii nie zwróciłoby się.
* Nie oceniałem doboru progów modelu (MIN_EV, MAX_CI_WIDTH itd.) — to wymaga
  pomiaru na rozliczeniach, nie czytania kodu.
