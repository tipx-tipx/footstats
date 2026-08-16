# Analiza konkurencji: SmartBet.gg, PredictStats, BetLab

**16.08.2026.** Zbadane bezpośrednio na żywych stronach (HTML, routing, nagłówki
serwera, cenniki), nie z opisów marketingowych.

---

# 0. NAJWAŻNIEJSZE ZDANIE TEJ ANALIZY

**Żaden z nich nie sprzedaje swojego zysku. Wszyscy sprzedają NARZĘDZIE albo
DOSTĘP.**

My budujemy produkt, którego celem jest udowodnić, że nasz model zarabia — i
dlatego nie ma końca, bo ROI wciąż jest ujemne. Oni sprzedają coś, co ma
wartość natychmiast, niezależnie od tego, czy ich model jest dobry: policzone
statystyki, filtry, generator kuponów, śledzenie własnych typów.

To jest różnica między produktem, który można SKOŃCZYĆ, a projektem badawczym,
który zawsze można poprawiać.

---

# 1. KTO JEST KIM — trzy różne biznesy, nie trzej konkurenci

| | SmartBet.gg | PredictStats | BetLab |
|---|---|---|---|
| czym jest | platforma statystyczno-predykcyjna | j.w. + moduły LIVE | grupa typerska + edukacja |
| stack | Next.js / **Vercel** | Next.js (`_next/static`) | React / **Vercel** |
| ochrona | Vercel Firewall (bot challenge) | brak | brak |
| języki | PL / EN | PL / EN | PL / EN |
| zakres | **111+ lig** | **1400+ lig** | — (typy ludzkie) |
| model | freemium | freemium | tylko płatne grupy |
| cena | **0 / 79 zł mies. / 59 zł rocznie** | free + Pro | **199–399 zł/mies.** |
| kanał | własna strona | własna strona | **Telegram + Kick + YouTube** |

⚑ **PredictStats i BetLab są POWIĄZANE.** BetLab pisze wprost: „We've partnered
with PredictStats – an advanced football analytics platform". BetLab dostarcza
ludzi i content, PredictStats — liczby. To jeden ekosystem, nie dwa serwisy.

⚑ **BetLab nie jest naszym konkurentem produktowym.** Sprzedaje wejście do grup
na Telegramie (ValuePL 249→199,20 zł, Strategy 399→319,20 zł, AKO 200→160 zł),
szkolenia, stream na Kicku, kanał YouTube „Underground Tips", a nawet **wyjazdy
na mecze** (BetTravel: Malta, Nowy Jork, Premier League). To biznes contentowy.
Konkurentem jest **SmartBet.gg** i, w mniejszym stopniu, PredictStats.

---

# 2. SMARTBET.GG — najbliższy nam produkt, robi DOKŁADNIE nasze rynki

## 2.1 Pełna mapa funkcji (z routingu)

```
/pl/football/predictions/     1x2 · double-chance · btts · corners · cards
                              corners-team · cards-team · shots-on-target
/pl/football/value-bets       osobna zakładka
/pl/football/acca             generator kuponów
/pl/football/bet-tracker      ŚLEDZENIE WŁASNYCH TYPÓW
/pl/football/standings        tabele
/pl/football/stats/           btts · cards · corners · fouls · offsides
                              goals-halves · match-result · over-1-5-goals
                              over-2-5-goals · shots-on-target
                              team-goals-scored · team-goals-conceded
/pl/premium                   cennik
/pl/blog  /pl/about-us        treści
```

**Rynki drużynowe, na których stoi cały nasz produkt — rożne drużyny, kartki
drużyny, celne strzały drużyny — mają u nich osobne strony prognoz.** To nie
jest nisza, którą tylko my odkryliśmy.

## 2.2 Czego my NIE mamy, a oni mają

1. **Rynki główne**: 1X2, podwójna szansa, BTTS, over/under całego meczu.
   To jest 80% wolumenu zakładów na rynku. My gramy wyłącznie w statystykach.
2. **Bet Tracker** — użytkownik wprowadza WŁASNE typy i widzi swoją
   skuteczność, ROI, co mu działa. Zero kosztu po stronie modelu, duże
   zaangażowanie i powód, żeby wracać codziennie.
3. **Typy społeczności** — „statystyki najlepszych typerów", ranking. Treść
   generowana przez użytkowników.
4. **Dwanaście stron statystyk jako osobny produkt** (`/stats/*`) — to jest
   maszyna SEO. Ktoś szuka „statystyki fauli", trafia na stronę, zostaje.
   My nie mamy ani jednej takiej strony.
5. **Widoki Grid / Table** i filtry po prawdopodobieństwie, EV%, rynku, kursie.
6. **Nawigacja po dniach** (poprzedni / dziś / następny).
7. **Discord i X** — społeczność poza stroną.

## 2.3 Ich deklaracje (i co z nimi zrobić)

```
+24% ROI vs zwykłe zakłady        <- bez rejestru, nie do sprawdzenia
12+ prognoz AI na mecz
90% mniej ręcznego wyszukiwania
111+ lig
```

„AI" i „algorytm SmartBeta" to marketing — opis funkcji mówi wprost: forma
drużyn, H2H, statystyki ofensywne i defensywne, kontekst meczu. **To jest to
samo, co robi nasz silnik**, tylko nazwane inaczej i sprzedane pewniej.

## 2.4 Cennik — najważniejsza liczba z całej analizy

```
Darmowe      0 zł     ograniczone predykcje AI, typy społeczności,
                      wyniki na żywo, podstawowe statystyki, tabele
Miesięczny   79 zł    pełne prognozy, value bety, zaawansowane statystyki,
                      filtry, generator ACCA, rożne, kartki
Roczny       59 zł/mies (rabat 25%)
```

**79 zł miesięcznie za dokładnie to, co mamy zbudowane.** BetLab za typy ludzkie
bierze 199–399 zł. Referencja z pamięci (PredictStats 129,99 zł/30 dni) była
zawyżona — realny sufit dla NARZĘDZIA to ~79 zł.

---

# 3. PREDICTSTATS — moduły i freemium z limitem danych

## 3.1 Moduły (routing)

```
/pl/value-bets          /pl/matches        /pl/live
/pl/goals               /pl/corners        /pl/cards
/pl/htft-opportunities  <- „HT/FT Łamaki": mecze, gdzie wynik zmienia się
                           między połowami
/pl/match-finder        <- wyszukiwarka meczów po kryteriach
/pl/games               /pl/upgrade        /pl/contest-rules  <- KONKURSY
/pl/affiliate-terms     <- PROGRAM PARTNERSKI
/pl/academy-terms       <- akademia/szkolenia
```

## 3.2 Model dostępu — to jest wzorzec do skopiowania

> „Wszystkie funkcje dostępne **za darmo z ograniczonymi danymi**. Ulepsz do
> Pro po pełny dostęp." · „100% darmowy test • Bez karty kredytowej"

**Nie blokują funkcji — blokują ILOŚĆ.** Każdy moduł widać, ale gość dostaje
kilka pozycji zamiast wszystkich. To jest dokładnie mechanizm, który u nas
byłby naturalny: mamy limit 12 typów na dobę, więc gość widzi 3, klient 12.

## 3.3 Co pokazują na karcie (z podglądu na stronie głównej)

```
Sygnały HT/FT:   „H2H Łamaki 4 / 10 · 40% skuteczność · H/A Trend
                  Manchester City często odrabia straty"
Prognozy bramek: „Oczekiwane 3.45 · 20 meczy · O 2.5 → 78% · MOCNY
                  BTTS 68% · Trafień 78%"
```

⚑ **Pokazują LICZBĘ MECZÓW, na której stoi prognoza („20 meczy"), i etykietę
siły („MOCNY", „WYSOKA").** My mamy `ess` i `udzial_priora` policzone przy
każdym typie i **nie pokazujemy ich nigdzie** — a to jest dokładnie ta
informacja, która buduje zaufanie.

## 3.4 Deklaracje

`1,3M+ analiz · 85% dokładność prognoz · 10K+ użytkowników · 1400+ lig`

„85% dokładność" bez rejestru — to samo, czego świadomie nie kopiujemy.

---

# 4. BETLAB — biznes, nie produkt

Sekcje: BET POLAND · BET GLOBAL · BET TRAVEL · TOOLS · PODZIEMNETYPY ·
TRAINING · STREAM PRO.

Sprzedaje **dostęp do grup Telegram**, a nie oprogramowanie:

```
ValuePL    249 zł → 199,20 zł/mies   value bety opłacalne PO PODATKU,
                                     tylko polscy bukmacherzy
Strategy   399 zł → 319,20 zł/mies   „Mathematically guaranteed long-term
                                     profit", „LIMITED spots"
AKO        200 zł → 160 zł/mies      kupony AKO z value betów, maks. 3 zdarzenia
```

⚑ **Trzy rzeczy warte uwagi mimo wszystko:**

1. **„Value bety opłacalne PO PODATKU, tylko polscy bukmacherzy"** — sprzedają
   dokładnie to, co my policzyliśmy i schowaliśmy. Mamy `ev_netto` z podatkiem
   12% w rachunku każdego typu i **nie robimy z tego argumentu**.
2. **Publiczna statystyka miesięczna** („Compare our statistics with what we
   post on Telegram. Click the link and see how we're doing in any given
   month") — to jedyna sprawdzalna rzecz, jaką ma konkurencja.
3. **Mechanika ceny**: „cena sugerowana" przekreślona obok promocyjnej, z notą
   prawną „najniższa cena z 30 dni" (zgodność z dyrektywą Omnibus).

**Czego nie kopiujemy:** „matematycznie gwarantowany zysk", „ograniczone
miejsca", brak własnej powierzchni (cały produkt żyje na Telegramie i Kicku).

---

# 5. GDZIE MY JESTEŚMY LEPSI (i nie wolno tego zmarnować)

To nie jest pocieszenie — to są rzeczy, których żaden z trzech nie ma:

1. **Rejestr rozliczeń pozycja po pozycji, liczony automatycznie.** Nasza
   Skuteczność liczy zamrożoną listę dnia, z typami „na próbę" oznaczonymi
   osobno. BetLab ma arkusz, który stał od 29.07. SmartBet i PredictStats mają
   wyłącznie deklaracje („85%", „+24% ROI") bez ani jednej sprawdzalnej pozycji.
2. **Podatek w rachunku każdego typu** (`ev_netto`, tryb zamrożony przy typie).
3. **Uczciwe „nie wiemy"** — tri-state składu, licznik typów bez rozstrzygnięcia,
   etykiety źródeł kalibracji (`wlasna` / `bez_proby` / `obca_epoka`).
4. **Drabinki** — nikt z trzech nie ma produktu wielopoziomowego.
5. **Kalibracja mierzona wstecz** i cała warstwa uczenia z rozliczeń.

⚑ Punkty 1–3 to jest **jedyna przewaga, której nie da się skopiować w tydzień**,
bo wymaga historii. Reszta (funkcje, UI) jest do zrobienia przez każdego.

---

# 6. CO UKRAŚĆ — w kolejności stosunku wartości do kosztu

## ⚑ A. Rzeczy, które kończą produkt (dni, nie tygodnie)

1. **Freemium z limitem DANYCH, nie funkcji** (wzorzec PredictStats).
   Gość widzi 3 typy z 12 i licznik „pokazujemy 3 z 12 dzisiejszych". Nie
   trzeba nowych ekranów — trzeba jednego filtra i jednego zdania.
2. **Cennik 79 zł/mies., 59 zł przy rocznym.** Punkt odniesienia rynkowy
   ustawiony przez SmartBeta. Bez tego nie ma produktu, tylko demo.
3. **Publiczny rejestr miesięczny** — „miesiąc → liczba typów → trafienia →
   wynik", ze stemplem świeżości. Dane MAMY, brakuje widoku. To jedyna rzecz,
   w której bijemy całą trójkę, i akurat jej nie pokazujemy.
4. **Liczba meczów i siła próby na karcie** („20 meczów", „MOCNY").
   `ess` i `udzial_priora` są policzone przy każdym typie — wystarczy je
   wyświetlić.

## B. Rzeczy, które budują ruch i zaangażowanie (tygodnie)

5. **Strony statystyk jako osobny produkt** (`/statystyki/rozne`,
   `/statystyki/kartki`, `/statystyki/faule`…). SmartBet ma ich dwanaście —
   to jest ich maszyna SEO. Mamy wszystkie te dane w banku.
6. **Bet Tracker** — użytkownik wpisuje własne typy, widzi swoją skuteczność.
   Zero kosztu modelu, powód do codziennych powrotów.
7. **Filtry i widok tabelaryczny** na liście typów (kurs, szansa, EV, rynek).
8. **Nawigacja po dniach** — wczoraj/dziś/jutro z zachowanym składem listy.

## C. Rynki, których nie mamy (do decyzji, nie do zrobienia od ręki)

9. **1X2, podwójna szansa, BTTS, over/under meczu.** To jest 80% wolumenu
   rynku i jedyny powód, dla którego przeciętny gracz w ogóle wchodzi na taki
   serwis. ⚑ Uwaga: nasz model jest dziś kalibrowany na rynkach statystycznych
   i nie wiadomo, czy poradzi sobie na 1X2 — ale **statystyki H2H i formy
   możemy pokazywać bez własnej prognozy**, tak jak robi to SmartBet
   w sekcji `/stats/`.

---

# 7. CZEGO NIE KOPIOWAĆ (decyzja stoi)

* „85% skuteczności" i „+24% ROI" bez rejestru — obaj to robią;
* „matematycznie gwarantowany zysk", „ograniczone miejsca" (BetLab);
* nazywanie zwykłego modelu statystycznego „AI" — ich własny opis funkcji
  wymienia formę, H2H i kontekst meczu, czyli to samo co u nas;
* przeniesienie produktu na Telegram — traci się jedyne, czego nie mają:
  sprawdzalną powierzchnię;
* masowe typy z deklarowaną przewagą 20%+.

---

# 8. WNIOSEK DLA NAS

Produkt nie ma końca, bo cel jest ustawiony na „udowodnić, że model zarabia".
Konkurencja ustawiła cel na „dać narzędzie, które oszczędza czas" — i dlatego
oni mają skończony produkt w sprzedaży, mimo że ich model jest **prostszy niż
nasz** (odtworzony wzór ScoutingStats to zwykły Poisson z shrinkage z minut).

Kolejność, która kończy produkt:

```
1. freemium z limitem danych + cennik 79/59 zł        <- produkt do sprzedania
2. publiczny rejestr miesięczny                       <- jedyna przewaga
3. liczba meczów / siła próby na karcie               <- zaufanie
4. strony statystyk (SEO)                             <- ruch
5. bet tracker                                        <- powroty
```

Punkty 1–3 są do zrobienia z tego, co JUŻ mamy policzone. Żaden nie wymaga
poprawy modelu.
