# Kolejka po audycie zewnętrznym (11.08.2026)

Lista rzeczy do zrobienia, w kolejności. **Nic z tej listy nie znika bez
zapisanego powodu** — jeśli coś odrzucamy, dopisujemy dlaczego.

Legenda: `[x]` zrobione · `[~]` w toku / obejście · `[ ]` otwarte

---

## P0 — krytyczne

- [x] **Rozjazd karta–księga między wersjami.** `_dopisz_nowe` przy istniejącym
  kluczu nie aktualizuje `p_model`/kursu/wersji (to zamierzone: cena z chwili
  publikacji). Po zmianie wersji kalibracji karta pokazywałaby V2, a księga
  rozliczyłaby i nauczyła model na V1. Zmierzone: **7 z 20 typów** pierwszej
  listy V2 (Kairat Almaty: księga 0,869, strona 0,8325).
  → brama `kolizja_wersji` w `build_wc_fast`; rekord V1 **zostaje nietknięty**
  i rozlicza się jako historia. Kolizja wygasa po meczu tamtego typu.

- [x] **Zamrożona kalibracja działała fail-open.** Brak / uszkodzenie /
  niezgodna wersja pliku po cichu wracały do `compute_bias_full`.
  → teraz `RuntimeError` przerywający cykl + test pilnujący zgodności pliku
  z `WERSJA_KALIBRACJI` przed pushem.

- [x] **Podwójna korekta w kuponach.** Leg drużynowy ma `p_model` policzone
  z `apply_bias(_bias_t_pelny, …)`, gdzie `_bias_t_pelny` zawiera już korektę
  strumienia — a `build_kupony` dostawał te same delty i nakładał je drugi raz
  (przy sześciu legach: szósta potęga tej samej poprawki).
  → `korekty_legow=None`. `kal_szansy` zostaje: działa na szansę całego
  kuponu i mierzy co innego.

- [~] **Izolacja wersji w POZOSTAŁYCH warstwach uczenia.** Zweryfikowane:
  `compute_bias_full`, `korekta_strumienia`, `szansa_pokazywana`,
  `compute_wagi_zaufania` — **żadna nie filtruje wersji**, tylko epokę.
  → **FILTRA NIE MA I TO JEST DECYZJA, NIE ZANIEDBANIE.** Zmierzone 12.08
  przed zmianą:

  ```
  korekta strumienia (drużyny)   wszystko -0,439   tylko V2 -0,428   bez V2 +0,174
  rozliczeń bieżącej wersji      drużyny 128       zawodnicy 0       drabinki 2
  ```

  Okno ostatnich 120 rozliczeń **samo już izoluje wersję** tam, gdzie
  strumień żyje — dla drużyn filtr zmieniłby korektę o 0,011 logita, czyli
  poniżej progu istotności warstwy (0,02). Tam, gdzie strumień nie żyje,
  twardy filtr skasowałby korektę do zera: zawodnicy zostaliby BEZ warstwy
  uczenia w ogóle, a nie z gorszą warstwą.
  → zamiast filtra **licznik**: `rozliczanie.sklad_wersji_okna` +
  linia w logu cyklu „ile z okna liczy BIEŻĄCA wersja". Gdy udział spadnie,
  będzie to widać od razu, a nie dopiero w audycie.
  **Zostaje otwarte:** `compute_wagi_zaufania` (nie sprawdzone pomiarem) oraz
  decyzja, co zrobić, gdy udział bieżącej wersji spadnie poniżej ~50%.

- [x] **Niekompletne stemple.** `kal_rynek` zapisywaliśmy tylko w pętli
  drużynowej; zawodnicy i rynki `match_*`/`wiecej_*` idą własnymi ścieżkami
  i go nie miały. Zmierzone 12.08 na produkcji: `kal_rynek` przy 423 z 684
  typów drużynowych, **0 z 18** zawodniczych, **0 z 25** sum meczowych,
  **0 z 7** „kto więcej", a `p_over_raw` nie istniało w ogóle.
  → `betting.stempel_rachunku` — JEDEN słownik `rachunek` (`p_over_raw`,
  `kal_rynek`, `kal_strumien`, `p_over_final`) wpięty we wszystkie cztery
  ścieżki plus drabinki. Jeden klucz, bo każde pole osobno musiałoby przejść
  przez białe listy w `build_wc_fast` — udokumentowana pułapka tego repo.
  `None` znaczy „ta ścieżka tego nie liczy", zero znaczy „policzono i wyszło
  zero"; mylenie tych dwóch rzeczy kosztowało nas już jeden pomiar.

- [~] ⚑ **ZNALEZISKO 12.08: `match_*` i `wiecej_*` NIE PRZECHODZĄ PRZEZ
  WARSTWY UCZENIA.** → **SUMY NAPRAWIONE tego samego dnia**, „kto więcej"
  zostaje świadomie. Zmierzone na 95 rozliczeniach epoki (skala `p_over`):
  dziś Brier 0,1718 i luka −7,9 pp; z korektą strumienia 0,1617 i **+1,2 pp**;
  z obiema warstwami 0,1625. Sama kalibracja rynku wypadła neutralnie (−0,5%,
  szum przy tej próbie), ale wchodzi razem z drugą — różnica jest w szumie,
  a jednolitość ścieżek to realna wartość, za brak której właśnie zapłaciliśmy.
  Per rynek: `match_corners` +8,2%, `match_cards` +3,5%.
  **`wiecej_*` ZOSTAJE bez warstw i to nie jest zaniedbanie:** to trójmian
  (gospodarz/remis/gość, sumuje się do 1), a delta logitowa jest zdefiniowana
  na `p_over` rynku dwustronnego — nałożona na jedną nogę rozerwałaby tę sumę.
  Test `test_sumy_maja_warstwy.py` pilnuje, żeby nikt nie dopisał rynków
  trójmianowych do mapy kalibracji bez policzenia korekty dla trzech wyników.
  Dotyczy 17 rozliczeń. Otwarte: policzyć taką korektę.

  *(oryginalny opis znaleziska niżej)* Wyszło przy wpinaniu stempli. Suma meczowa liczy
  `counts.p_over_sumy` z SUROWYCH rozkładów obu drużyn, „kto więcej"
  `counts.porownanie_druzyn` tak samo — i obie idą prosto do `p_model`.
  `korekta_strumieni` jest wołana wyłącznie w ścieżce zawodniczej,
  drużynowej i drabinek (`build_wc_fast`: 3675, 5650, 6957), a `bias_map`
  nie dotyka tych rynków wcale. Dotyczy 25 + 7 żywych typów i 78 + 17
  rozliczeń bieżącej epoki (luka −4,9 i −5,2 pp).
  **`match_corners` ma własną kalibrację ze WSZYSTKICH czterech przedziałów
  policzoną z rozliczeń — i nigdy nie jest stosowana.** To ta sama klasa co
  „nowe rynki bez bram" z 31.07: rynek dopisany osobną ścieżką ominął
  mechanizm, który wszyscy uważali za globalny. Stempel zapisuje tam teraz
  jawne zera, więc od 12.08 widać to w księdze, a nie tylko w kodzie.
  → **decyzja właściciela**: naprawa zmienia liczby na produkcji, więc
  wymaga pomiaru przed/po, nie „przy okazji".

- [x] **Endpoint `kupon-pomin` bez kontroli roli.** → NAPRAWIONE 12.08
  dwuwarstwowo: (1) akcje ruszające wspólny stan (`profil`, `pomin`,
  `przywroc`, `wymien`, `przebuduj`) wymagają roli `admin` — 403 dla klienta;
  (2) `wlasny_nauka` bierze z żądania **tylko identyfikatory**, a `p_model`,
  kurs, EV, flagi i `rachunek` odtwarza z `legi_pool`, czyli z tego, co sami
  policzyliśmy w ostatnim cyklu — leg bez pokrycia w puli jest odrzucany,
  a kurs łączny i szansa kuponu liczą się z legów. UI poszedł za tym: strona
  kuponów czyta rolę i nie rysuje przycisków, które zwróciłyby 403 (razem
  z leadem, który obiecywał pomijanie). `rachunek` dopisany do `_POLA_LEGA` —
  czwarta biała lista na drodze stempla.
  **Zostaje otwarte:** kupony per użytkownik (osobna, większa zmiana) oraz RLS.

  *(oryginalny opis niżej)* Zalogowany klient przez
  endpoint z kluczem serwisowym zmienia globalny profil i kupony oraz woła
  cykl; przyjmuje z przeglądarki `p_model`, kursy i EV, które trafiają do
  księgi i warstw uczenia. → ograniczyć do administratora, kupony klienta
  per użytkownik, parametry modelowe odtwarzać po stronie serwera
  z kanonicznych identyfikatorów.

- [~] **EV netto — DECYZJA WŁAŚCICIELA PODJĘTA 11.08.** Stan zmierzony na
  produkcji: wszystkie 19 typów na stronie ma ujemną wartość po podatku
  (mediana −6,3%), a **żaden segment z n≥25 nie ma dodatniego zwrotu netto**
  w historii (najlepszy: `match_corners|powyzej` −4,6%). Realny zwrot epoki
  ligowej: brutto −6,4%, **netto −17,7%** (−1475 zł przy 10 zł na typ, 835
  zakładów). Do wyjścia na zero po podatku trzeba zwrotu brutto powyżej
  +13,6% — brakuje 20 punktów procentowych.

  **PRZYJĘTE:**
  * strona przestaje obiecywać zysk — „Duża szansa" mówi o trafialności
    (to dowozi: 83,6% w paśmie ≥85%), nie o zarobku,
  * druga zakładka („Wyszukane okazje") wymaga dodatniego EV netto i póki
    co będzie **pusta** — z jawnym komunikatem „dziś nic nie znaleźliśmy".

  **ODRZUCONE, z uzasadnieniem właściciela:**
  * ~~podłoga −5% na EV netto w bramach~~ — wycinanie typów idzie pod prąd
    celowi „jak najwięcej rodzajów typów"; model ma się nauczyć, a nie
    dostawać coraz ciaśniejsze sito,
  * ~~wstrzymanie sprzedaży do czasu dodatniego segmentu~~ — decyzja, którą
    trzeba by potem odwracać.

  **Nie proponować ponownie bez nowych danych.**

---

## Fundament — przeciek kursu do prognozy

- [~] **`p_sport` — prognoza liczona BEZ jakichkolwiek danych kursowych.**
  → **ZMIERZONE 12.08, wynik zmienia uzasadnienie tej pozycji:**
  `docs/pomiar-cena-w-prognozie.md`. Test niezmienniczości **nie przechodzi**
  (sam kurs rusza mnożnik prognozy o 41% na `team_corners`/`team_shots`, 21%
  przez samą linię goli), więc audyt ma rację co do faktu. Ale usunięcie ceny
  **pogarsza** prognozę o 3,1% Briera na 409 rozliczeniach — i najbardziej
  tam, gdzie cena rusza najmocniej (−10,1% przy |mnożnik−1| > 0,15).
  → wniosek: rozdzielenie ma sens **jako narzędzie pomiaru**, nie jako sposób
  na poprawę typów. Przed przebudową trzeba zdecydować, po co ją robimy:
  do mierzenia przewagi czy do typowania. To dwie różne decyzje.
  Dziś kursy 1X2 i linii goli przeliczamy na tempo i spread, które wchodzą
  w kontekst meczu, λ i końcowe `p_model`. Cena wpływa też na pokrycie, bo do
  silnika trafiają głównie mecze sparowane z ofertą. Korelacja model–rynek
  (0,965) jest więc częściowo konstrukcyjna, a porównanie „model kontra
  kurs" jest częściowo porównaniem ceny z samą sobą.
  → cena dołączana dopiero przy wyborze linii i liczeniu EV; wariant
  z rynkiem może zostać, ale jako osobno nazwany i wersjonowany model
  hybrydowy. Do tego test niezmienniczości: zmiana kursu przy tych samych
  cechach nie może zmienić rozkładu.

- [ ] **Benchmark kursu nie jest prawdziwym no-vig.** Zapisywać obie strony
  rynku z tej samej chwili i liczyć fair probability po zdjęciu faktycznej
  marży.

---

## Dane i źródła

- [~] **Zdrowie źródeł** — stan per źródło, odróżniający legalny brak danych
  od awarii. Rotowire (`league=WOC`) milczał trzy tygodnie bez alarmu.
  → zrobione DLA ROTOWIRE (rozróżnia „żadna strona nie odpowiedziała" od
  „strony działają, ale brak meczów"). Pozostałe źródła nadal bez strażnika.
- [x] **Rotowire: poprawne kody lig.** `league=WOC` → osiem lig
  (EPL/LALIGA/SERIEA/BUNDESLIGA/LIGUE1/MLS/UCL/UEL). Sprawdzone na żywym
  źródle: **0 → 25 drużyn ze składem**, 90 bloków meczowych zamiast zera.

- [x] **Zakres drużynowy: +2 rozgrywki.** Zmierzone 11.08: **67 ze 160**
  nadchodzących meczów było poza rejestrem, więc nie liczyliśmy dla nich ani
  jednego rynku drużynowego. Doszły Leagues Cup (utid 13783 / comp365 7242,
  18 meczów) i CONMEBOL Libertadores (384 / 102, 7 meczów) — obie z parą
  identyfikatorów sprawdzoną na realnych meczach.
- [ ] **South African Premier Division** (utid 358, 9 meczów) — czeka na
  `comp365`. Wyszukiwarka 365 nie dała jednoznacznego dopasowania, a bez pary
  identyfikatorów typy z tej rozgrywki nigdy by się nie rozliczyły.
- [ ] **Reszta rozgrywek spoza rejestru** — J1 League, Championship,
  Eredivisie, Süper Lig, Liga Portugal, Pro League, MLS, Liga MX. Ta sama
  procedura: `utid` z `event/by-date`, `comp365` z `/search/?query=`,
  weryfikacja liczby gier w `fixtures`/`results` PRZED dopisaniem.

- [x] **Diagnoza składów — POTWIERDZONA I ROZSZERZONA 13.08.** Pomiar na
  oknie 48 h: statshub oficjalny **0 ze 119**, przewidywany **2 ze 119**,
  Rotowire pokrywa +5, 365Scores nie ma pola `lineups` przed gwizdkiem,
  Sofascore blokuje IP serwerowni. **112 ze 119 meczów (94%) jedzie na samej
  historii.** Pełny przegląd dziewięciu źródeł:
  `docs/pomiar-wlasna-jedenastka.md`.
- [x] **Sofascore jako główne źródło składów — ODRZUCONE.** Potwierdzone
  empirycznie: działa z domowego PC, w chmurze blokuje IP serwerowni. To nie
  jest limit budżetu.
- [x] **365Scores jako drugie źródło składów — ODRZUCONE JAKO ŹRÓDŁO SKŁADU.**
  Sprawdzone 13.08: `game/?gameId=` przed meczem NIE ma pola `lineups` (jest
  dopiero po gwizdku). ⚑ Ma za to **listę nieobecnych**: `Missing` 57,
  `Doubtful` 9 na 40 meczów (55% meczów), każdy rekord z `injury.reason`.
  To jedyne działające w chmurze źródło do `injured_or_suspended` — patrz
  osobna pozycja niżej.
- [x] **Skład zastępczy z rotacji minut — ZMIERZONY I ODRZUCONY 13.08.**
  Walidacja wsteczna: trafia 68,6% (7,5 z 11) wobec 85–90% prognoz medialnych,
  a wpięty jako `predicted_started` **pogarsza Briera o 20%**. Model już
  wyciska z historii wszystko; ograniczenie „startuje dokładnie 11" nie wnosi
  nic (0,0%). Nie wracać bez NOWEGO ŹRÓDŁA, nie z nowym sposobem liczenia.
- [ ] ⚑ **SportsGambler jako źródło składów — ZNALEZIONE, CZEKA NA POMIAR.**
  Przewidywane XI **3–10 dni przed meczem**, HTTP 200 bez klucza, endpoint
  `/lineups/lineups-load2.php?id=<ID>`. **1206 meczów ze składem w 18
  rozgrywkach** — Brazylia A i B, Liga Profesional, MLS, Liga MX,
  Libertadores, Sudamericana, Kolumbia, Urugwaj, Chile, Ekstraklasa,
  Allsvenskan, Eliteserien, Superliga, Veikkausliiga, LM/LE/LK. Czyli
  dokładnie ta luka, której nie zamyka żadne nasze źródło.
  **Snapshot 730 prognoz zapisany** (`docs/pomiar/`), pomiar zamyka się po
  rozegraniu tych meczów. Próg: wyraźnie powyżej 68,6%.
- [ ] **Kontuzje i zawieszenia z 365Scores** — `injured_or_suspended`
  (`engine.py`) zeruje minuty w modelu i **w produkcji nikt go nigdy nie
  ustawia**; jedyne `True` jest w teście. Źródło działa w chmurze, parowanie
  po nazwisku istnieje (`scores365.resolve_player_key`). ⚑ Robić **po**
  rozstrzygnięciu SportsGamblera — jeśli tamten wejdzie, kontuzjowany i tak
  wypadnie z przewidywanej jedenastki i zostanie wąski margines
  (rozróżnienie „na ławce" od „nie ma go wcale").
- [x] **Nieużywane pola statshuba — ZMIERZONE 13.08, REZERWY NIE MA.**
  Teza audytu („największa rezerwa jakości") sprawdzona na obu poziomach.

  **Zawodnicy** (1023 obserwacje na rynek, walidacja czasowa, 35 kandydatów):
  w KAŻDYM rynku najlepszym predyktorem jest historia tego samego rynku.
  Najlepszy obcy kandydat to `duelLost` dla fauli, +0,003 — szum.

  ```
  rynek             baza (historia rynku)   najlepszy obcy
  shots                    0,344            onTargetScoringAttempt  -0,009
  sot                      0,293            shots                   -0,002
  fouls_committed          0,198            duelLost                +0,003
  fouls_won                0,333            foulInvolvements        -0,011
  tackles                  0,274            interceptionWon         -0,038
  ```

  **Drużyny — rożne** (961 obserwacji, bank ligowy 1677 meczów): tu obcy
  predyktor faktycznie bije bazę **w korelacji** — `possession` 0,141 wobec
  0,095 dla historii rożnych. Ale w realnym błędzie prognozy to nic:

  ```
  model                    błąd (out-of-sample)   poprawa
  sama średnia ligi              2,406
  historia rożnych (DZIŚ)        2,398             +0,3%
  samo posiadanie                2,393             +0,2%
  rożne + posiadanie             2,389             +0,4%   (kontrola: +0,9%)
  ```

  ⚑ **Najważniejsze z tego pomiaru:** historia rożnych bije zwykłą średnią
  ligi o **0,3%**. Cały model rożnych na poziomie drużyny wnosi prawie nic
  ponad „w meczu jest ~5 rożnych" — a deklaruje 77% przy 58% trafień.
  To nie jest problem doboru cech, tylko tego, że rynek jest nieprzewidywalny,
  a model o tym nie wie. Patrz `docs/pomiar-skad-luka-deklaracji.md`.

  „Strzałów z pola karnego" z tezy audytu **nie mamy** — bank ma
  `shots_outside` (spoza pola, 65% pokrycia).
  UWAGA: `opponentStatistics` jest już czytane (`profil_druzyn.py`).
- [ ] **Budżet: pamięć historii między cyklami** (zwolni 60–70%), priorytet
  po terminarzu, backoff na 429, cache negatywny.
- [ ] **Minimalny budżet eksploracyjny** dla lig i rynków spoza bieżącej
  listy — priorytetyzacja wyłącznie po zeszłotygodniowej liście tworzyłaby
  pętlę samowzmacniającą.
- [ ] **Sparować 12 drużyn bez identyfikatora 365** (Lyon, Rapid Wiedeń, AGF,
  Helsingborg, Hearts, Borac…). Godzina roboty, odblokowuje historię na stałe.

---

## Model

- [ ] **ESS jako brama** — zacząć od ESS ≥ 10 dla etykiety wysokiej pewności
  (przy priorze 4 meczów ESS 5 zostawia priorowi 44,4% informacji), próg
  potwierdzić walidacją czasową. `MIN_EFFECTIVE_MATCHES = 4.0` istnieje
  w kodzie i nie jest używany.
- [ ] **Sufit 18 miesięcy musi objąć też `lg_mean`, priory, koncesje
  i mostki** — dziś maskujemy likelihood i opisy, ale norma ligi liczy się ze
  wszystkiego. Do tego: jawne sortowanie po czasie przed wyborem najnowszych,
  a brak timestampu nie może znaczyć „dzisiaj".
- [~] **Kalibracja per (rynek, strona, przedział)** z hierarchią i ściąganiem
  proporcjonalnym do próby. Rdzeń musi zostać w jednej orientacji „powyżej",
  żeby `p_over + p_under = 1`; strona może być wymiarem diagnostycznym, ale
  nie osobną korektą rozrywającą komplementarność.
  → **ZROBIONE 12.08 w części „przedział":** hierarchia rynek→przedział była
  wręcz szkodliwa, bo `global` liczy się po obserwacjach, a 86% z nich siedzi
  w jednym przedziale (`p_over` 0,00–0,55, bo V1 typowało „poniżej"). Prior
  przedziału to teraz ZERO. Zmierzone out-of-sample na 100 rozliczeniach V2:
  Brier 0,2774 → 0,2625, luka −24,1 → −18,9 pp. Pełny pomiar i odrzucone
  warianty: `docs/pomiar-prior-przedzialu.md`. **Zostaje wymiar „strona"** —
  dziś strona nie jest osobnym wymiarem kalibracji i po naprawie znaku produkt
  stoi w 91% po stronie „powyżej", która traci −14…−20 pp od zawsze.
- [ ] **`szansa_pokazywana` nie jest dziś tylko prezentacją** — zmienia
  eligibility i wybór listy (brama „ujemna po korekcie"). Na starcie V2
  wyzerować lub zamrozić, uczyć wyłącznie na V2.
- [ ] **Regulator `compute_bias_full` nie odejmuje własnej poprzedniej
  delty.** Objaw: przed naprawą znaku wszystkie duże rynki drużynowe
  siedziały dokładnie na dolnym capie. Obejście: mapa zamrożona. Teraz jest
  stempel `kal_rynek`, więc przebudowa ma na czym stanąć.
- [x] **Naddyspersja per rynek — ZMIERZONA I ODRZUCONA 13.08.** Rozrzut jest
  realny i większy, niż zakładał audyt (Pearson wobec przewidywania:
  `team_corners` 1,81, `team_shots` 1,75, `shots` 2,38, `team_cards` 0,69,
  `fouls_committed` 0,77 — przy modelu zakładającym 1,00). **Ale wpływ na
  deklarację to 0–2 pp**, bo linie stoją blisko średniej, a dyspersja rusza
  ogony, nie środek: symulacja NB o tej samej średniej dała `team_corners`
  +0,0 pp, `team_shots` −1,7 pp, `match_cards` +0,6 pp. Przy luce −12 pp to
  nie jest przyczyna. ⚑ Liczyć Pearsonem WOBEC PRZEWIDYWANIA — surowa
  wariancja miesza różnice między zawodnikami z szumem meczowym i zawyża
  (2,57 wobec 1,75 dla `team_shots`).

- [x] ⚑ **PRZYCZYNA LUKI ZNALEZIONA I NAPRAWIONA 13.08** (`ed4c306`) — to jest
  odpowiedź na pytanie, którego dotyczyła większość tego bloku. Model liczy
  poprawnie (bias 1,00 na wszystkich meczach), **zawyża selekcja**: na górnych
  25% rozkładu λ bias to 1,13, na górnych 5% już 1,46, a dolne 25% jest
  NIEdoszacowane (0,87). Powód siedział wprost w kodzie — `group_prior_from_context`
  ściągała zawodnika do JEGO WŁASNEJ średniej zamiast do grupy porównawczej,
  więc prior nie ściągał do niczego. Po naprawie bias na górze schodzi do
  0,95–1,07, Brier lepszy o 2,5–7,8% w każdym z czterech rynków.
  Pełny rozbiór siedmiu sprawdzonych mechanizmów:
  `docs/pomiar-skad-luka-deklaracji.md`.
  → **Do rozważenia (wymaga własnego pomiaru):** grupa per (rynek × pozycja)
  zamiast samego rynku — wspólna średnia 1,61/90 zawyża obrońcę i zaniża
  napastnika.

- [x] **Faule zawodnicze wyceniane dwukrotnie za wysoko — NAPRAWIONE 13.08.**
  Model deklarował ~51% na „powyżej 1,5 faula", a realnie to **25,8%**
  (1220 meczów naszych zawodników: średnio 0,98 faula na mecz, 41% meczów
  bez ani jednego).

  Sprawdzone i ODRZUCONE po drodze: usterka rozliczania (ten sam rozkład zer
  w innych strumieniach), mnożnik sędziego (wynosi 1,000 — patrz osobne
  znalezisko niżej), kształt rozkładu (wariancja/średnia 1,24, Poisson pasuje
  do 4 pp).

  Przyczyna: **model wierzył historii fauli tak samo mocno jak historii
  strzałów**, a to najmniej powtarzalny rynek, jaki mamy:

  ```
  korelacja historii z następnym meczem (1023 obserwacje, walidacja czasowa)
     shots           0,567  (R² 0,32)
     sot             0,492  (R² 0,24)
     fouls_won       0,481  (R² 0,23)
     tackles         0,436  (R² 0,19)
     fouls_committed 0,282  (R² 0,08)   <- historia mówi prawie nic
  ```

  → `SILA_PRIORU_RYNKU = {"fouls_committed": 25.0}` (reszta zostaje na 5,0).
  Zmierzone: Brier na górze rozkładu 0,2361 → 0,2304, bias 1,09 → 0,98.
  ⚑ **Zmieniony JEDEN rynek.** `shots` i `sot` mają dziś optimum; przy
  `fouls_won` i `tackles` Brier poprawiał się o ułamek, ale bias się psuł.

- [x] **Sędzia praktycznie nie ruszał liczby — NAPRAWIONE 13.08.**
  Objaw: `czynniki.sedzia` = 1,000 w każdym rynku dyscyplinarnym.
  ⚑ Pierwsza diagnoza („profil nie powstaje") była BŁĘDNA — patrzyłem na cache
  mundialowy. Ligowy ma 1064 mecze, 659 z policzonymi faulami i 333 arbitrów,
  a mnożniki są sensowne (Marciniak 0,89, Juan Martínez 1,20, Rey Hilfer 0,77).

  Prawdziwa przyczyna: **`MIN_MECZE_SEDZIA = 4`, a mediana arbitra to 2 mecze.**
  Mnożnik był liczony i od razu zerowany — w logu cyklu widać to wprost
  („faule ×1,021, 2 m.", „×1,288, 3 m.").

  Zmierzone na 658 meczach (leave-one-out, profil wyłącznie z pozostałych
  meczów arbitra, `shrink_factor` jak w produkcji):

  ```
  próg   pokrycie meczów   poprawa prognozy fauli
   1          100%              +1,9%
   2           75%              +1,9%
   3           51%              +3,4%
   4           29%              +3,5%   <- było
  ```

  Profil pomaga przy KAŻDYM progu, więc `shrink_factor` (przy dwóch meczach
  zostawia ~20% surowego odchylenia) wystarcza jako ochrona przed szumem.
  → `MIN_MECZE_SEDZIA = 2`, pokrycie 29% → 75%.

  ⚑ **Liczba i zdanie rozdzielone.** Komentarz przy starym progu sam na to
  wskazywał („Liczba była nieszkodliwa, zdanie już nie"): mnożnik wolno
  stosować od 2 meczów, ale `MIN_MECZE_SEDZIA_OPIS = 4` pilnuje, żeby karta
  nie nazwała arbitra „pobłażliwym" na dwóch meczach. Drabinki zostają na
  progu opisowym — ich front pisze „nic tu nie zmieniamy", więc włączenie
  mnożnika bez zmiany tego zdania zamieniłoby je w nieprawdę.

---

## Produkt

- [x] **Cena, do której ściągamy kartę, brała się z założenia, nie z pomiaru**
  (13.08, `04ff875`). Ściągaliśmy do kursu po zdjęciu ZAŁOŻONYCH 7% marży,
  a wartość liczyliśmy wobec kursu Z marżą — pierwszy cykl z aktywnym
  ściąganiem dał **0 z 31 typów z dodatnią wartością**. Zmierzone na 2451
  rozliczeniach: cena zawyża relatywnie o 3,2%, nie 7% (walidacja czasowa:
  luka +0,4 pp). → warstwa `rozliczanie.marza_sciagania`, waga dobierana pod
  tę samą cenę, obie liczby w stemplu `rachunek`.
  ⚑ Sama marża **nie naprawia komunikatu**: waga schodzi na podłogę 0,05,
  a wartość zostaje ujemna u wszystkich — bo po ściągnięciu do uczciwej ceny
  „wartość" wobec kursu z marżą JEST marżą. Stąd druga część niżej.

- [x] **Cena jest informacją, nie werdyktem** (13.08, decyzja właściciela).
  Z karty schodzi werdykt o przewadze i odznaka z procentem; kropka w wierszu
  liczy się z szansy, nie z `ev_pct` (wcześniej wszystkie typy miały najsłabszą);
  znika sortowanie „największa przewaga nad kursem" (górna 1/3 tego sortowania
  dawała −41,2%, dolna +32,5%); nagłówek nie zależy od znaku wartości.

- [x] **Ten sam zakład miał dwie szanse w dwóch miejscach produktu**
  (13.08, `4b132e5`). Lista typów przechodzi urealnienie i ściągnięcie do ceny,
  a pula legów (generator kuponów na żądanie) była dumpowana surowa: 32 z 32
  typów listy jest też w puli, mediana różnicy **+10,5 pp**, max +13,8.
  → leg niesie `p_model` (surowe, do składania — parytet z `build_kupony`)
  i `p_pokaz` (do pokazania); front czyta przez `szansaLega` z fallbackiem.
  `rozlicz_only` dostał tę samą warstwę, bo pisze `kupony` co 20 minut.

- [ ] **Stopka obiecuje przewagę cenową, której nie pokazujemy.** „Pokazujemy,
  gdzie kurs bukmachera jest naszym zdaniem za wysoki" — po zmianie z 13.08
  karta o tym nie mówi i mówić nie może. Do przejrzenia razem z resztą tekstów
  sprzedażowych.

- [~] **Podział na zakładki NIE JEST wdrożony zgodnie z dokumentem.** Audyt
  sprawdził stan faktyczny: nadal obowiązuje limit **dwóch** typów na mecz,
  lista jest wybierana od nowa w każdym cyklu (brak trwałego manifestu dnia
  i zamknięcia o 06:00), a kwarantanny i ukrywanie rynków **są aktywne** mimo
  deklaracji „bez blacklist". To są cztery osobne rzeczy do zrobienia, nie
  jedna.
  → **14.08 zamknięte trzy z czterech:** limit na mecz (szczegóły niżej),
  **kwarantanny przestały zdejmować typy** — deklaracja „bez blacklist" ma
  wreszcie pokrycie w kodzie — oraz **trwały manifest dnia z zamknięciem
  o 6:00**. Zostaje sam podział na zakładki.
  ⚑ Przy okazji wyszło, że limity **tylko udawały, że działają**: deklarowany
  cap 20 dawał realnie medianę 67 typów na dzień (13.08 — 185), a „2 typy
  z meczu" pozwalało na 16. Powód: typ wznowiony wchodził poza limitem, ale
  licznik rósł dopiero po nim, więc mocny nowy typ przechodził przed nim.
  Naprawione jednym posortowaniem (wznowione pierwsze) — nic nie znika ze
  strony, nowe wchodzą na to, co realnie zostało wolne.

- [ ] **Routing rynku z wagą modelu < 0,2 do „Value" — WYCOFANY.** Jeśli cena
  przewiduje lepiej niż model, to nie jest dowód, że model znalazł wartość.
  Taki segment → shadow, bez kuponów i bez stawki. (Moja pierwotna
  rekomendacja B2 była błędna.)
- [x] **„Bez blacklist" znaczy: nic nie znika z pomiaru i z shadow.** Nie
  znaczy: obowiązek publicznego rekomendowania segmentu bez potwierdzonej
  jakości.
  → **14.08: kwarantanny przestały zdejmować typy z listy** (decyzja
  właściciela, `KWARANTANNA_ZDEJMUJE_Z_LISTY = False`). Powodem nie jest sama
  zasada, tylko pomiar — bramy wyrzucały materiał LEPSZY niż to, co zostawało:

  ```
  pokazane klientowi          n=419  luka -10,8 pp  ROI  -3,5%
  zdjęte: kwarantanna rynku   n= 34  luka  -7,3 pp  ROI +10,3%
  zdjęte: kwarantanna strony  n=190  luka -16,3 pp  ROI  -1,3%
  zdjęte: poza listą dnia     n=149  luka  -9,2 pp  ROI  +1,2%
  ```

  Mechanizm: brama patrzy na okno 40 rozliczeń, więc wstrzymuje segment po
  serii pecha — czyli dokładnie wtedy, gdy ten i tak wraca do średniej.
  Rozstrzygnięcie tego punktu jest więc takie: segment bez potwierdzonej
  jakości **jest publikowany, ale oznaczony** („ostrożnie z tym zakładem"),
  schodzi na koniec kolejności „polecane" i **nie wchodzi do kuponów**.
  Przy okazji naprawione samopodtrzymywanie się kwarantanny kategorii:
  „ambitniejsza linia" w kwarantannie przestawała w ogóle powstawać, więc
  znikała też z pomiaru i brama nie miała jak się nigdy odwrócić.
  **Zostaje otwarte:** okno zgody (`rozjazd_z_rynkiem`) — 274 rozliczone typy
  o ROI −3,0%, czyli lepszym niż publikowane, i 174 typy zdejmowane dziś przed
  gwizdkiem. Ten sam wniosek co przy kwarantannach, ale własna skala, więc
  własny pomiar przed i po.
- [x] **Zamrożona lista dnia — WDROŻONA 14.08.** Pełny plan, liczby i decyzje:
  `docs/plan-lista-dnia.md`. Lista domyka się o 6:00 (pierwszy cykl po tej
  godzinie), manifest w Supabase pod kluczem `lista_dnia`; po domknięciu skład
  się nie zmienia, a nowy typ na ten dzień dostaje `dzien_zamkniety` i żyje
  dalej w puli kuponów oraz w rozliczeniach w tle.
  ⚑ **Doba PRODUKTOWA 6:00 → 6:00, nie kalendarzowa** — 41% typów to mecze
  grane między północą a 4:00 (Ameryka Płd.), więc przy dacie kalendarzowej
  „lista na piątek" domykana o 6:00 w piątek zawierałaby mecze rozpoczęte
  o 2:00. `rozliczanie.dzien_pl` (rozliczenia, Skuteczność, archiwum) zostaje
  kalendarzowe i **nie wolno go ruszać**. Konsekwencja: mecz o 2:00 z piątku
  na sobotę jest na liście PIĄTKOWEJ, a w Skuteczności pod datą SOBOTNIĄ.
  Koszt domknięcia: 18,7% typów nie zdąży (i są to typy nieco gorsze niż te,
  które zdążyły: −6,5% wobec −2,6%, przy n=99 w granicach szumu).
  **Zostaje otwarte:** wyjątki bezpieczeństwa poza odwołanym meczem
  (potwierdzona absencja, zawieszenie rynku) — dziś typ zostaje na liście
  z zamrożoną ceną, bez osobnego oznaczenia.
- [x] **Limit 1 typ/mecz — ODRZUCONY POMIAREM (14.08).** Pełne liczby:
  `docs/pomiar-bramy-i-kolejnosc.md`. Trzy powody, każdy osobno wystarczający:

  ```
  typów w meczu    n     luka          ROI      <- 366 rozliczeń, bez drabinek
  1               33   -10,9 pp      +6,4%      (próba za mała)
  2-4            176   -13,3 pp      -6,7%
  5 i więcej     157    -5,3 pp      +8,3%      <- NASZ NAJLEPSZY MATERIAŁ
  ```

  (1) mecz, o którym model ma dużo do powiedzenia, jest dwa razy lepiej
  skalibrowany — limit obcinałby dokładnie ten segment; efekt monotoniczny
  w 9 z 9 komórek pasma kursu, przeżył kontrolę na horyzont, ligę i drabinki;
  (2) zostawienie jednego typu z meczu daje 143 zakłady o ROI −11,7% zamiast
  419 o ROI −3,5%; (3) brama i tak była martwa — w całej księdze (4594 wpisy)
  powód `limit_meczu` wystąpił **raz**, bo stała na końcu łańcucha.
  → limit zdjęty z listy, **zostaje w puli kuponów** (tam korelacja legów
  realnie boli). Stała `MAX_PEWNIAKOW_MECZ` żyje dalej dla kuponów.

- [x] **Nowe kryterium rankingu — WESZŁO W WERSJI ZMIERZONEJ (14.08).**
  Teza „dzisiejsze sortowanie jest odwrócone" **nie potwierdziła się**: stała
  na 114 rozliczeniach sprzed naprawy znaku kalibracji i dotyczyła sortowania
  po PRZEWADZE NAD KURSEM — a to zdjęliśmy już 13.08 (`04ff875`). Na 419
  rozliczeniach dzisiejsza kolejność ma kierunek poprawny (góra +0,6%,
  dół −11,6%); odwrócone jest wyłącznie sortowanie po przewadze (−7,4% na
  górze), którego nie ma.
  → zamiast przepisywania rankingu na niezmierzone kryteria audytu (świeżość
  historii, jednoznaczność serii, zgodność źródeł — **żadnego z nich nie da
  się dziś ocenić wstecz, bo księga ich nie stempluje**) doszedł jeden
  czynnik, który JEST zmierzony: bogactwo materiału meczu (premia 1,10 od
  5 typów w meczu). `build_wc_fast.moc_listy`, liczone przy dumpie — więc
  obejmuje typy wznowione, które omijają pętlę scoringu.
  ⚑ Front przestał liczyć własną kopię formuły (`moc` w `DruzynyTablica`)
  i bierze gotową liczbę z backendu.
  **Otwarte:** stempel `rank_score` / miar historii w księdze — bez niego
  następnego kryterium rankingu też nie da się ocenić wstecz.
- [ ] **Kupony: limit ekspozycji** na mecz, drużynę i pojedynczy leg (dziś
  jeden zakład w 4 z 5 kuponów), metryki klastrowane, append-only historia
  wszystkich rezultatów (dziś log rotuje po 21 dniach zachowując wygrane —
  selekcja przeżywalności).

---

## Drabinki

- [~] **Każdy wyświetlany szczebel zapisywany i rozliczany osobno.**
  ZROBIONE 13.08 DLA DRUGIEGO SZCZEBLA — czyli dla tego, na którym stoi cała
  zakładka. Do tej pory księga znała wyłącznie `hero`, więc zdanie usera
  („drugi szczebel bardzo często siada i jest głównym celem") nie miało **ani
  jednego rozliczenia**, choć jego przewaga współdecyduje o kolejności kart
  (`_oceń_karte` uśrednia oba szczeble). Przy strumieniu o ROI −25,5% to była
  najdroższa biała plama produktu.

  Drugi szczebel idzie teraz do księgi jako typ **pomiarowy** (`odrzucony`
  + `odrzucenie_powod = drugi_szczebel`): rozlicza się w tle, poza
  Skutecznością, poza kalibracją i poza korektą strumienia — userowi ani
  modelowi nie zmienia się nic, dochodzi wyłącznie wiedza. Rekord niesie
  stempel `szczebel` (1 = hero, 2 = drugi) oraz w `rachunku` szansę **przed**
  korektą strumienia. Odczyt: `rozliczanie.pomiar_szczebli_drabinek`
  i część 6 kontroli startowej.

  Zostaje otwarte: szczeble od trzeciego w górę (na kartach są rzadkie),
  a potem ciągły posterior Beta–Binomial albo jeden model rozkładu liczby
  zdarzeń. Przejście „Wilson przy 7 obserwacjach → surowy procent przy 8"
  tworzyłoby arbitralny skok — nie robić tego w tej postaci.
- [~] **Zdjąć korektę strumienia z drugiego szczebla** — jest zmierzona na
  pierwszych szczeblach, a stosowana do drugich. **NIE ROBIMY TEGO NA ŚLEPO:**
  od 13.08 księga zapisuje przy każdym drugim szczeblu obie liczby (przed
  ścięciem i po nim) przy tej samej prawdzie, więc pytanie jest wreszcie
  rozstrzygalne pomiarem. Część 6 kontroli startowej pokazuje trójkę
  „deklaracja przed / po / faktycznie". Decyzja po ~25 rozliczeniach
  (`KOREKTA_DRABINEK_MIN_N`), nie wcześniej — zdjęcie korekty PODNOSI szanse
  drugiego szczebla, a ten strumień już dziś przeszacowuje o 15 pp.
- [~] **Klasy kart nie niosą informacji — etykieta ZDJĘTA ZE STRONY 13.08.**
  `PROG_KLASY` było w kodzie opisane jako założenie do skalibrowania
  z rozliczeń. Pierwszy pomiar (94 rozliczenia): „solidny" trafia 38,6%,
  „mocny" 36,8%, „top" 0,0% (n=3), a deklaracja rośnie z klasą — czyli rośnie
  sama luka. Korelacja przewagi z trafieniem **−0,084**; karty z najniższą
  przewagą są skalibrowane (luka −0,3 pp), z najwyższą rozjeżdżają się
  o −27,6 pp. Decyzja właściciela: plakietka schodzi z karty, klasa **dalej
  się liczy i zapisuje**, więc pomiar biegnie. Wraca, gdy któraś klasa realnie
  trafia lepiej. Liczby: `docs/pomiar-szczeble-drabinek.md`.
  **Zostaje otwarte:** znaleźć cechę, która faktycznie porządkuje karty —
  dzisiejsze kryterium (przewaga) tego nie robi.
- [x] **Premia za okno ceny obejmowała najgorsze pasmo — POPRAWIONE 13.08.**
  `OKNO_CENY_PREF_DO` 1,90 → 1,70. Okno powoływało się na tabelę rozliczeń
  w `radar.py`, a ta mówiła „1,70–2,00: trafia 23,5%, zwrot −56,1%".
  Sprawdzone ponownie na 94 rozliczeniach, próg z LUKI, obie połowy próby
  zgodne: 1,55–1,70 luka **+0,2 pp** (skalibrowane co do punktu), 1,70–1,90
  luka **−28,9 pp** — gorzej niż to, co zostaje POZA oknem (−10,7 pp).
  Zmiana kolejności, nie bramy.
- [ ] **Routing kart**: pierwszy < 1,45 i drugi < 2,20 → „wysoka szansa";
  pierwszy ≥ 1,45 → drabinka; pierwszy 1,20–1,45 z drugim ≥ 2,20 przy
  pokryciu ≥ 50% → drabinka (najciekawszy typ karty).
- [ ] **Kilka rynków jednego gracza** — osobna karta zbiorcza, **nie**
  drabinka (brak monotoniczności szczebli).

---

## Uczciwość i interfejs

- [ ] **„Nie eksponować ROI, dopóki nie jest dodatni" — ODRZUCONE.** To
  selektywne ukrywanie niekorzystnego wyniku. Albo ROI i EV netto jawnie,
  z liczebnością i okresem, albo strumień oznaczony jako eksperymentalny bez
  rekomendacji i bez CTA. Nie wolno jednocześnie ukrywać ROI i mówić, że
  bukmacher „płaci więcej, niż powinien".
- [ ] **Hit rate może być główną metryką „Dużej szansy"**, ale nie zastępuje
  kalibracji ani ekonomiki po podatku.
- [ ] **Dowód historyczny na karcie** zamiast żargonu (przyjęte wcześniej).

---

## Bezpieczeństwo i proces

- [ ] **RLS osobnym wdrożeniem**: allowlistowe `meta_public` /
  `typy_wyniki_public` → przełączenie klienta → ścieżka server-only dla
  administratora → dopiero potem odebranie anonowi surowych kluczy →
  sprawdzić, czy frontend po błędzie nie podstawia po cichu danych demo.
  **Migracji 0004 nie wykonywać ponownie w ciemno** — produkcja zachowuje się
  tak, jakby była aktywna (anon widzi dokładnie 14 kluczy z allowlisty).
- [ ] **Deploy nie jest blokowany testami** — Vercel wdrożył ~28 s przed
  końcem CI. Chroniony master, wymagane testy przed wdrożeniem, ręczna
  promocja albo feature flag.
- [ ] **`TERMIN_BRAK_DANYCH_S` = 7 dni**, a dokumentacja w tym samym pliku
  mówi o 48 godzinach.
- [ ] **Rozliczenie nie jest w pełni nieodwracalne** — „superzmiana" potrafi
  zmienić rozliczony rekord z przegranej na wygraną. Docelowo: status
  provisional → immutable final, poprawki jako append-only correction event.

---

## Kryteria bezpiecznego uruchomienia V2 (z audytu)

Do odhaczenia przed uznaniem V2 za w pełni wdrożone:

- [x] brak rekordów V1 na publicznej liście V2
- [x] brak cichego fallbacku zamrożonej kalibracji
- [x] dokładnie jedno zastosowanie korekty strumienia w kuponach
- [ ] zero rozjazdów karta–księga w `p`, kursie i wersji *(brama stoi;
      do potwierdzenia na produkcji)*
- [x] 100% wymaganych stempli dla wszystkich klas typów *(wdrożone 12.08,
      `betting.stempel_rachunku`; do potwierdzenia na pierwszych rekordach
      z produkcji — pola przechodzą przez białe listy, a te już raz gubiły
      stempel w drodze z puli na stronę)*
- [ ] ustalona i przetestowana reguła EV netto
- [ ] V2 oceniane na danych spoza próby użytej do dopasowania mapy
- [ ] aktywne kontrole zdrowia źródeł
- [ ] chroniony master i ręczna promocja

**Ocena V2 dopiero po ~100 sparowanych rozliczeniach** (min. 30 „powyżej"
i 30 „poniżej"), paired Brier / log-loss. Nie po ROI z kilku dni.

⚑ **STAN 12.08: 100 rozliczeń V2, ale rozkład 91 „powyżej" / 5 „poniżej"** —
warunek sparowania NIE jest spełniony i formalnej oceny nadal nie da się
zrobić. Powód jest sam w sobie znaleziskiem: naprawa znaku przewróciła stronę
typów (V1: 83% „poniżej" → V2: 91% „powyżej"), czyli przeniosła produkcję ze
strony o ROI ≈ 0 na stronę, która traci −13…−17% od początku epoki ligowej.
Liczby: `docs/pomiar-prior-przedzialu.md`.

---

## Kolejność prac zalecana przez audyt

Zapisana w całości, bo porządkuje zależności — nie każda pozycja z listy wyżej
ma sens przed poprzednią.

```
1. Wstrzymać publikację nowych rekomendacji i kuponów V2 przed następnym
   cyklem; nie zatrzymywać rozliczania istniejących rekordów.
   → ODRZUCONE decyzją właściciela: trzy najgroźniejsze rzeczy były do
     naprawy w godziny, a alternatywą dla publikacji była pusta strona.
     Naprawione tego samego dnia (P0-1, P0-2, P0-5).
2. Naprawić tożsamość karta–księga, immutable snapshot i pełną izolację
   wersji.                                        → CZĘŚCIOWO (brama kolizji)
3. Frozen calibration jako fail-closed + stemple dla wszystkich ścieżek.
                                                  → CZĘŚCIOWO (fail-closed)
4. Usunąć podwójną korektę w kuponach.            → ZROBIONE
5. Jawna decyzja produktowa o EV netto i komunikacja dla klienta.
                                                  → PODJĘTA (patrz wyżej)
6. Ograniczyć `kupon-pomin` do administratora i osobno domknąć RLS.
7. Zbudować niezależne `p_sport` i dopiero po nim dołączać cenę.
8. Rozszerzać pokrycie, źródła składów, cache i monitoring źródeł.
                                                  → ZACZĘTE (Rotowire, +2 ligi)
9. Na końcu: nowy ranking, zamrożona lista dnia, drabinki i kupony.
```

## Co audyt potwierdził jako JUŻ DZIAŁAJĄCE

Ważne, żeby tego nie „naprawiać" drugi raz — mój dokument twierdził inaczej
i było to nieaktualne:

- `opponentStatistics` jest przetwarzane i używane (`profil_druzyn.py`),
- endpoint `performance` działa, ma budżet i cache,
- Betclic potrafi dostarczać ofertę,
- model minut ma scenariusze start / zmiana / ławka / DNP,
- korelacje kontekstu są stosowane dla kilku rynków,
- rozliczenia grupują po strefie Europe/Warsaw, najwcześniejsze rozliczenie
  wymaga 130 minut i zakończonego statusu, dogrywka ma zabezpieczenia,
- korelacje drużynowe są mierzone i wykorzystywane (`counts.py`).

## Czego audyt nie potwierdził (i co z tym zrobić)

- **943 testy** — potwierdzone lokalnie po audycie (dziś 953).
- **Wzrost pokrycia do 300–400 typów** — prognoza, nie pomiar. Zweryfikować
  dry-runem po zmianie zakresu, zanim trafi do jakiegokolwiek dokumentu.
- **Liczby o korelacjach i AUC** — pochodzą z `docs/zrodla-danych.md`
  i wcześniejszych sesji; brakuje odtwarzalnego skryptu i surowego artefaktu.
  Przy następnym użyciu: policzyć od nowa i zapisać skrypt obok wyniku.
- **Rotowire jako przyczyna konkretnej liczby odrzuceń** — wymaga atrybucji
  na danych, dziś to rozumowanie, nie pomiar.
- **Że nowe korekty poprawiają wynik poza próbą** — obecny replay jest
  częściowo in-sample. Stąd wymóg oceny na danych spoza próby.
