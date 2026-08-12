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

- [ ] **Diagnoza składów — zrobiona, wynik zmienia priorytet.** statshub
  oddaje przewidywane XI dla **1 z 12** sprawdzonych meczów (endpoint działa —
  Lyon 22 zawodników — po prostu nie ma danych dla naszych lig). Sofascore
  jest jedynym realnym źródłem, ale kod ostrzega, że **blokuje IP serwerowni**,
  więc w chmurze wypada; 13 składów z dry-runu to wynik LOKALNY.
  → wniosek: dla Ameryki Płd. i Skandynawii nikt nie poda nam składów.
  Jedyna droga to własny skład przewidywany z rotacji minut.
- [ ] **Sofascore jako główne źródło składów** (dziś 13 z 307 meczów) —
  najpierw diagnoza, czy to limit budżetu, czy coś innego.
- [ ] **365Scores jako drugie źródło składów** (ma `lineups`, jest wpięte do
  rozliczeń).
- [ ] **Skład zastępczy z rotacji minut**, gdy nikt nie podaje XI.
- [ ] **Nieużywane pola statshuba** — 49 pól, używamy 5. Dla rożnych liczymy
  szóstym najlepszym predyktorem (strzały z pola karnego +0,145 kontra rożne
  +0,082 na 536 parach). **Największa rezerwa jakości, zero dodatkowych
  zapytań.** UWAGA: `opponentStatistics` jest już czytane
  (`profil_druzyn.py`) — wcześniejszy zapis w `docs/zrodla-danych.md` był
  nieaktualny.
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
- [ ] **Naddyspersja per rynek** — rożne (1,55) i strzały (1,88) są
  nad-dyspersyjne, gole (0,94) i kartki (0,86) **pod**-dyspersyjne. Jedna
  zmiana rozkładu na wszystkie rynki byłaby błędem.

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

- [ ] **Stopka obiecuje przewagę cenową, której nie pokazujemy.** „Pokazujemy,
  gdzie kurs bukmachera jest naszym zdaniem za wysoki" — po zmianie z 13.08
  karta o tym nie mówi i mówić nie może. Do przejrzenia razem z resztą tekstów
  sprzedażowych.

- [ ] **Podział na zakładki NIE JEST wdrożony zgodnie z dokumentem.** Audyt
  sprawdził stan faktyczny: nadal obowiązuje limit **dwóch** typów na mecz,
  lista jest wybierana od nowa w każdym cyklu (brak trwałego manifestu dnia
  i zamknięcia o 06:00), a kwarantanny i ukrywanie rynków **są aktywne** mimo
  deklaracji „bez blacklist". To są cztery osobne rzeczy do zrobienia, nie
  jedna.

- [ ] **Routing rynku z wagą modelu < 0,2 do „Value" — WYCOFANY.** Jeśli cena
  przewiduje lepiej niż model, to nie jest dowód, że model znalazł wartość.
  Taki segment → shadow, bez kuponów i bez stawki. (Moja pierwotna
  rekomendacja B2 była błędna.)
- [ ] **„Bez blacklist" znaczy: nic nie znika z pomiaru i z shadow.** Nie
  znaczy: obowiązek publicznego rekomendowania segmentu bez potwierdzonej
  jakości.
- [ ] **Zamrożona lista dnia** — niezmienny snapshot z `valid_until` =
  początek meczu, obok osobno aktualny kurs i status. Wyjątki bezpieczeństwa:
  odwołanie/przełożenie, potwierdzona absencja, zawieszenie rynku, uszkodzone
  dane, unieważniona wersja modelu.
- [ ] **Limit 1 typ/mecz** (dziś 2) + nowe kryterium rankingu: świeżość
  i długość historii → jednoznaczność serii → zgodność źródeł → dopiero
  szansa i cena. Dzisiejsze sortowanie po pewności i przewadze jest
  **odwrócone** (górna tercja −4,2% / −41,2%, dolna +26,6% / +32,5%).
- [ ] **Kupony: limit ekspozycji** na mecz, drużynę i pojedynczy leg (dziś
  jeden zakład w 4 z 5 kuponów), metryki klastrowane, append-only historia
  wszystkich rezultatów (dziś log rotuje po 21 dniach zachowując wygrane —
  selekcja przeżywalności).

---

## Drabinki

- [ ] **Każdy wyświetlany szczebel zapisywany i rozliczany osobno** (dziś
  tylko hero), potem ciągły posterior Beta–Binomial albo jeden model rozkładu
  liczby zdarzeń. Przejście „Wilson przy 7 obserwacjach → surowy procent przy
  8" tworzyłoby arbitralny skok — nie robić tego w tej postaci.
- [ ] **Zdjąć korektę strumienia z drugiego szczebla** — jest zmierzona na
  pierwszych szczeblach, a stosowana do drugich.
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
