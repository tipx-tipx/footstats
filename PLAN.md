# FootStats Value Engine — analiza i plan projektu

> Dokument projektowy. Wersja 0.2 (2026-07-02). Narzędzie do wyszukiwania value betów
> na statystyki zawodników i drużyn: probabilistyczny core + warstwa kontekstowa + betting engine.

## STAN WDROŻENIA (2026-07-02)

ZROBIONE:
- pipeline Python (`pipeline/`): scraper Sofascore (curl_cffi, rate-limit, cache),
  model Gamma-Poisson→NB z shrinkage i wygaszaniem, model minut (mieszanka scenariuszy),
  czynniki kontekstowe (rywal/sędzia/dom/game script), kartki przez faule, devig power,
  bezpieczniki anty-longshot; 26 testów jednostkowych rdzenia — przechodzą.
- backfill EPL 2025/26 (docelowo ~320 meczów) + mini-kalibracja holdout: Brier ~0.144
  na ~2500 predykcjach (rzut monetą = 0.25).
- schemat Supabase (`supabase/migrations/0001_init.sql`) — gotowy do wdrożenia.
- aplikacja webowa (`web/`, Next.js 16 + Tailwind 4 + framer-motion), w całości po polsku:
  Okazje (filtry, karty z uzasadnieniem, pasek rozkładu, forma), Mecze, Moje zakłady
  (localStorage + CLV), Skuteczność modelu (wykresy kalibracji), Jak to działa.
  Design wg frontend-design skill, kolory z logo, paleta wykresów zwalidowana (CVD).
- wszystkie 14 rynków zawodniczych + 4 drużynowe scorowane od dnia 1 (decyzja użytkownika).

TRYB DEMO: przerwa ligowa (MŚ 2026) → mecze "nadchodzące" = ostatnia kolejka 25/26,
kursy przykładowe (szum log-odds + marża, line shopping po 3 bukmacherach), wyraźnie
oznaczone w UI.

DO ZROBIENIA (start sezonu 26/27, sierpień):
- job scoringu nadchodzących meczów + ręczny input realnych kursów (CSV/formularz),
- push wyników do Supabase + przełączenie warstwy danych web na Supabase,
- deploy na Vercel (root: `web/`), pipeline lokalnie przez Harmonogram zadań Windows,
- ingest kursów Superbet (automatyczny) — po walidacji ręcznego obiegu.

---

## SILNIK MATCHUPÓW — „kto na kogo gra" (dodane 2026-07-02)

Kluczowa przewaga nad zwykłym modelem: styl KONKRETNEGO rywala tworzy przewidywalne
efekty na statystyki. To osobna warstwa mnożników (`model/matchup.py`), obok czynnika
„ile rywal dopuszcza". Wszystkie mnożniki shrinkowane do 1.0 przy małej próbie
i capowane do [0.80, 1.30]. Dane stylu (drybling, pojedynki, faule, wysokość linii)
pobieramy z Sofascore (`totalContest`, `duelWon`, `Fouls`, `Offsides`).

### Architektura (model/matchup.py)

Dwa profile stylu wchodzą do predykcji:
- **PlayerStyle** — is_dribbler, is_target_man, is_weak_1v1, is_holdup, is_playmaker,
  takes_setpieces, height, strona L/P (z detailed_position).
- **OpponentStyle** — drybling, pojedynki, faule, dośrodkowania, długie piłki,
  posiadanie, rożne, wysokość linii (spalone wymuszane), bloki, udział strzałów
  z dystansu (deep block), słabość w powietrzu, agresja (kartki), zagrożenie
  lewą/prawą flanką.

Dane stylu z Sofascore (w cache, re-ingest bez nowych zapytań): totalContest,
duelWon, aerialWon/Lost, totalCross, totalLongBalls, challengeLost (ogrywany 1v1),
keyPass, touches, height, situation strzału (egzekutor stałych).

### Zaimplementowane analogie (wybór użytkownika 2026-07-02 — WSZYSTKIE)

Strzały: 1 (faworyt vs głęboki blok → shots+/sot−), 2 (egzekutor stałych),
3 (zza pola vs głęboki blok), 4 (zablokowane vs blokująca drużyna).
Głowa: 9 (target man vs słaby w powietrzu), 10/11 (dośrodkowania/rożne).
Faule: 14/15/16 (drybler/fizyczność/ogrywany 1v1), 17 (kontry), 18 (gra środkiem).
Wywalczone: 19 (drybler), 20 (holdup), 21 (playmaker).
Odbiory: 23/24 (drybler/pojedynki), 25 (świadomość strony L/P).
Przechwyty: 27 (drybling), 28 (długie piłki), 29 (posiadanie).
Spalone: 30 (wysoka linia), 31 (poacher).
Kartki: 33 (drybler), 35 (skrzydło po stronie), 36 (wysoka linia vs szybki).
Drużynowe: 37 (faule vs dryblerzy), 39 (dwie agresywne → kartki).
Mechanizmy przekrojowe: A (strona L/P), C (ogrywany 1v1), D (stałe fragmenty),
E (model głębokiego bloku — spina rynki strzałów).

Weryfikacja: 101/209 okazji ma aktywny matchup, 46 testów przechodzi.
Na szybkiej ścieżce MŚ (statshub) matchup jest nieaktywny (brak danych stylu) —
degraduje się grzecznie; pełnia działa na danych ligowych z Sofascore.

Zasada: każdy efekt wynika z DANYCH STYLU (nie z domysłu), jest kierunkowy,
shrinkowany do 1.0 przy małej próbie i capowany do [0.78, 1.32].

---

## ETAP 1 — Analiza problemu

### Jak podejść do budowy

System to w istocie trzy niezależne strumienie danych, które spotykają się w jednym miejscu:

1. **Strumień statystyczny** — historia per-mecz zawodników i drużyn (co się wydarzyło).
2. **Strumień kontekstowy** — składy, minuty, sędzia, siła przeciwnika, game script (co się wydarzy).
3. **Strumień rynkowy** — linie i kursy bukmacherów (co rynek myśli, że się wydarzy).

Value bet = rozbieżność między (1)+(2) a (3). Kluczowa asymetria projektu: **dane statystyczne są
relatywnie łatwe do zdobycia, dane kursowe na player props są trudne** — i to one są wąskim gardłem.
Model bez porównania z linią to tylko dashboard; dlatego architektura musi od dnia 1 traktować
ingest kursów jako obywatela pierwszej kategorii (snapshoty z timestampem, historia ruchu linii).

### Największe trudności (w kolejności dotkliwości)

1. **Kursy player props** — nie ma taniego, legalnego API z liniami na strzały/faule zawodników
   dla europejskich bukmacherów. Opcje: płatne agregatory (OpticOdds, OddsJam — drogie),
   The Odds API (ograniczone player props w piłce), scraping bukmacherów (kruche, ToS),
   ręczne wprowadzanie linii w MVP. To pytanie nr 1 do rozstrzygnięcia.
2. **Settlement source mismatch** — bukmacherzy rozliczają player props wg danych Opta/StatsPerform.
   Jeśli model uczy się na danych z innego źródła, to „tackle" czy „interception" może znaczyć
   co innego niż to, co rozliczy bukmacher. Dotyczy zwłaszcza: tackles, interceptions, fouls won.
   Shots / SOT / fouls committed / cards / offsides są między providerami niemal zgodne.
3. **Projekcja minut** — połowa wartości modelu. P(over 1.5 shots) dla zawodnika grającego 90 min
   vs 60 min to zupełnie inna liczba. Potrzebny osobny pod-model minut i aktualizacja po ogłoszeniu składów.
4. **Małe próbki i niestacjonarność** — transfery, zmiana roli, nowy trener, powrót po kontuzji.
   Stąd bayesian shrinkage jako fundament, nie dodatek.
5. **Weryfikowalność edge** — bez historii kursów nie da się zrobić uczciwego backtestu.
   Snapshoty kursów zbieramy od pierwszego dnia działania, nawet zanim model będzie gotowy.
6. **Rzadkie zdarzenia** — headed shots, offsides, SOT outside the box: niskie λ, ogromna wariancja
   względna, model łatwo pokazuje „fałszywy edge". Wchodzą później, z ostrożnym traktowaniem.

### Co jest realne w MVP, co do v1, co później

- **MVP (realne w ~kilka tygodni)**: top 5 lig, 5 rynków zawodniczych wysokiej częstotliwości
  (shots, SOT, fouls committed, fouls won, tackles), team fouls + team cards, kursy wprowadzane
  półautomatycznie/ręcznie dla wybranych meczów, dzienny value board z edge/confidence/uzasadnieniem.
- **v1 (pełna wersja pierwsza)**: top 5 lig + LM/LE, automatyczny ingest kursów (rozstrzygnięte źródło),
  rynki pochodne (shots outside the box, 1H shots, interceptions, yellow cards), bet tracker z CLV,
  kalibracja/backtest w UI.
- **Później (v2+)**: top 15 lig, reprezentacje i turnieje, headed shots / SOT outside box / offsides,
  alerty (Telegram), automatyczna reakcja na ogłoszenie składów, ewentualnie live.

Rozgrywki międzynarodowe (MŚ, ME, kwalifikacje) celowo na końcu: małe próbki per zawodnik
w danym kontekście, rotacja, mecze towarzyskie, inne tempo — najtrudniejsze do modelowania,
a linie bukmacherskie bywają tam paradoksalnie ostrzejsze (duża uwaga traderów przy wielkich turniejach).

---

## ETAP 2 — Rekomendacja modelu matematycznego

Architektura modelu: **trzy warstwy, zgodnie z Twoją preferencją** — probabilistyczny core,
multiplikatywna warstwa kontekstowa, betting engine.

### Warstwa 1 — probabilistyczny core (count stats zawodników)

**Bazowa intensywność per-90 z bayesowskim shrinkage (Gamma-Poisson / empirical Bayes):**

- Dla zawodnika `i` i statystyki `s` trzymamy posterior intensywności per-90:
  `λ_i,s ~ Gamma(α0 + Σ w_t·x_t, β0 + Σ w_t·(min_t/90))`
  gdzie `x_t` = liczba zdarzeń w meczu `t`, `w_t = exp(-Δdni/τ)` to wygaszanie czasowe
  (τ ≈ 180 dni na start, kalibrowane per rynek), a prior `(α0, β0)` pochodzi z grupy
  pozycja × rola × liga (np. „skrzydłowy dryblujący, top 5 lig").
- To automatycznie daje **rozkład predykcyjny Negative Binomial** — czyli overdispersion
  „za darmo", bez ręcznego dopasowywania. Zawodnik z 3 meczami jest mocno ściągany do
  średniej grupowej; zawodnik z 60 meczami gra własnymi liczbami.
- **Dyspersja per rynek**: shots i fouls won są wyraźnie naddyspersyjne, fouls committed
  i tackles bliższe Poissona — parametr dyspersji estymujemy globalnie per rynek z historii
  i walidujemy na kalibracji, nie zgadujemy.
- **Zero-inflated NB tylko dla rzadkich rynków** (headed shots, shots outside box dla
  zawodników nie-specjalistów): komponent „strukturalnego zera" = mecze, w których zawodnik
  w ogóle nie wchodzi w daną rolę (np. nie wychodzi do dośrodkowań). Dla rynków MVP zwykły
  NB wystarcza — ZI dodaje parametry, których małe próbki nie udźwigną.

**Model minut (kluczowy pod-model):**

P(over) liczymy jako mieszankę scenariuszy minutowych, nie punktową estymatę:

```
P(X ≥ k) = P(start pełny)·P(X ≥ k | λ·90/90)
         + P(start + zejście ~70')·P(X ≥ k | λ·70/90)
         + P(wejście z ławki ~25')·P(X ≥ k | λ_sub·25/90)
         + P(nie zagra)·0
```

Prawdopodobieństwa scenariuszy z historii rotacji (ostatnie N meczów, wzorce trenera,
zagęszczenie terminarza, status kontuzji). Po **ogłoszeniu oficjalnych składów (~60 min przed
meczem) system przelicza wszystko** — to moment największego edge, bo linie nie zawsze nadążają.

**Kartki (rynek binarny, nie count):**

Yellow card modelujemy warstwowo, nie bezpośrednio z częstości kartek (za mało zdarzeń):
`P(kartka) ≈ 1 − exp(−λ_fauli · q_i · m_ref)` gdzie `λ_fauli` = przewidywane faule zawodnika
(z modelu wyżej), `q_i` = indywidualna konwersja faul→kartka (shrinkowana), `m_ref` = mnożnik
surowości sędziego (kartki/faul sędziego vs średnia ligi). Plus korekta na derby/stawkę meczu.

### Warstwa 2 — kontekstowa (multiplikatywna, w log-space)

Finalna intensywność meczu to dekompozycja:

```
λ_match = λ_base(per-90, posterior) × (E[min]/90 przez mieszankę)
        × f_opp × f_home × f_ref × f_pace × f_gamescript
```

Każdy czynnik estymowany osobno, **shrinkowany do 1.0 i capowany** (np. [0.75, 1.35]),
żeby kontekst korygował model, a nie nim rządził:

- **f_opp (matchup)**: ile przeciwnik „dopuszcza" danej statystyki per-90 względem średniej ligi,
  z korektą pozycyjną (skrzydłowy vs faule popełniane przez bocznych obrońców przeciwnika;
  tackles pomocnika vs liczba dryblingu/podań przeciwnika w środku pola). Też z shrinkage —
  po 5 meczach sezonu czynnik przeciwnika prawie nie działa, po 25 działa mocno.
- **f_home**: efekt dom/wyjazd per rynek (dla fauli istotny — gospodarze faulują mniej i dostają
  mniej kartek; dla strzałów umiarkowany).
- **f_ref**: tylko rynki dyscyplinarne — faule/mecz i kartki/faul sędziego względem ligi.
  Obsada sędziowska znana zwykle 1–2 dni przed meczem → predykcja dwustopniowa
  (bez sędziego / z sędzią).
- **f_pace / f_gamescript**: elegancki trik — **używamy rynku 1X2/handicap/totale jako feature**.
  Rynek meczowy jest efektywny; implikowana różnica siły i spodziewana liczba goli to najlepszy
  dostępny predyktor game scriptu. Drużyna grająca z bloku niskiego = więcej tackles/interceptions
  jej pomocników, mniej strzałów; faworyt goniący wynik = więcej strzałów z dystansu. W MVP
  wystarczy prosty log-linear na (implied spread, implied total); potem można to rozbudować.
- **Forma**: celowo NIE jako osobny czynnik — recent form jest już w wygaszaniu czasowym posteriora.
  Podwójne liczenie formy to klasyczny błąd, który psuje kalibrację.

### Warstwa 3 — betting engine

1. **Model probability**: `p_model = P(X ≥ line + 0.5)` z rozkładu predykcyjnego NB (linie .5)
   albo P(X ≥ k) / push handling dla linii całkowitych.
2. **Implied probability + devig**: jeśli bukmacher kwotuje obie strony (over/under) —
   usuwamy marżę metodą **power/Shin** (lepsza niż proporcjonalna, bo uwzględnia favourite-longshot
   bias, silny właśnie na propsach). Jeśli kwotowana jest tylko jedna strona — odejmujemy
   szacowaną marżę rynku (kalibrowaną per bukmacher/rynek, typowo 5–9% na propsach).
3. **Fair odds**: `1 / p_model`.
4. **Edge**: raportujemy dwie miary — `edge_pp = p_model − p_implied_fair` (punkty procentowe)
   oraz `EV% = p_model × odds − 1` (to EV decyduje o rankingu).
5. **Confidence** (0–100 → low/medium/high), złożony z:
   - efektywnej wielkości próby zawodnika (po wygaszaniu) — ile „prawdziwych" danych stoi za λ,
   - szerokości przedziału wiarygodności na p_model (wariancja posteriora),
   - pewności minut (skład ogłoszony > przewidywany; rotacyjny zawodnik = kara),
   - historycznej kalibracji modelu na danym rynku (z backtestu),
   - wielkości czynników kontekstowych (edge zbudowany w 80% na f_ref przy nieogłoszonym sędzi = kara).
6. **Risk level**: osobno od confidence — wariancja wyniku (rzadkie zdarzenia = high risk nawet
   przy dobrym modelu), ryzyko składu, ryzyko rozliczenia (rynki wrażliwe na definicję providera).
7. **Ranking okazji**: sortowanie po `EV% × waga(confidence)`, z filtrem minimalnym
   (np. EV ≥ 3%, confidence ≥ medium). Opcjonalnie sugerowana stawka: **frakcyjny Kelly (1/4)**
   z capem — pełny Kelly przy niepewnym p_model to przepis na bankructwo.
8. **Kalibracja**: cotygodniowy raport reliability (predicted vs actual w kubełkach p),
   Brier score per rynek; przy dryfcie — rekalibracja izotoniczna na wyjściu modelu.

### Statystyki drużynowe

Ten sam szkielet, prostszy: NB na poziomie drużyny.
- **Team fouls**: `λ = λ_team_base × f_ref × f_opp(faule wymuszane przez przeciwnika: drybling,
  szybkie przejścia) × f_stawka(derby, spadek/awans) × f_gamescript`. Sędzia to czynnik dominujący —
  rozrzut między sędziami w top 5 lig to ±25% fauli/mecz.
- **Team cards / booking points**: z fauli drużynowych × konwersja sędziego.
- **Team shots / SOT**: najprostszy rynek drużynowy — dobre wejście, bo waliduje cały pipeline
  na dużych próbach.

### Variance i rzadkie zdarzenia — zasady

- Rynki z λ < ~0.5/mecz (headed shots, SOT outside box, offsides napastnika) — **nie ufamy edge
  poniżej bardzo wysokiego progu** i oznaczamy risk=high; posterior szeroki → confidence niski
  automatycznie, ale dokładamy twardy filtr.
- Nigdy nie raportujemy edge bez przedziału: UI pokazuje p_model z CI (np. 58% [51–65%]).
- Zawodnicy < 400 minut efektywnej próby → tylko „watchlist", nie „bet".

---

## ETAP 3 — Dane i features

### Domeny danych (rozdzielenie)

| Domena | Zawartość | Granularność |
|---|---|---|
| Zawodnik | tożsamość, pozycja, rola, klub (stint), profil (dryblujący/target man/strzelec z dystansu) | slowly changing |
| Zawodnik-mecz | minuty, start/ławka, wszystkie count staty, pozycja w meczu | per mecz |
| Drużyna-mecz | faule, strzały, posiadanie, PPDA/pressing proxy, kartki | per mecz |
| Mecz | liga, kolejka, data, dom/wyjazd, **sędzia**, stawka meczu, wynik | per mecz |
| Przeciwnik (pochodne) | „allowed per-90" per statystyka i strefa/pozycja | rolling, licz. z drużyna-mecz |
| Rynek | bukmacher, rynek, linia, kurs over/under, **timestamp snapshotu** | wiele snapshotów per linia |
| Predykcje | wersja modelu, λ, parametry rozkładu, p, fair odds, edge, confidence, uzasadnienie | per mecz × podmiot × rynek × linia |

### Źródła danych — realne opcje

- **API-Football (api-sports.io)** — fixtures, składy, per-mecz staty zawodników (shots, SOT, fouls
  committed/drawn, tackles, interceptions, cards, offsides, minuty), sędziowie. Szerokie pokrycie lig,
  rozsądna cena (~$40–60/mc). **Rekomendowany kręgosłup MVP.** Braki: brak lokalizacji strzału,
  części ciała, podziału na połowy.
- **Understat** — dane strzał-po-strzale (koordynaty, część ciała, minuta) dla top 5 lig + RPL.
  To odblokowuje: shots outside the box, headed shots, first half shots. Dane publiczne w JSON
  na stronie; scraping techniczne łatwy, prawnie szara strefa — do decyzji.
- **FBref** — bogate agregaty i logi strzałów, świetne do budowy priorów i backfillu historii; scraping z rate-limit.
- **Sofascore / WhoScored (Opta)** — najbogatsze per-mecz staty, nieoficjalne API / trudny scraping, ryzyko blokad. Opcja, nie fundament.
- **Sportmonks** — alternatywa dla API-Football, głębsze dane w wyższych tierach.
- **Opta/StatsPerform bezpośrednio** — poza budżetem indywidualnym; wspominam, bo to źródło rozliczeń bukmacherów.
- **Kursy**: The Odds API (piłkarskie player props ograniczone — sprawdzić aktualne pokrycie),
  OpticOdds/OddsJam (pełne pokrycie propsów, drogie), scraping wybranych buków, ręczny input w MVP.

### Kluczowe features (poza surowymi liczbami)

per-90 z wygaszaniem, starts ratio i wzorce rotacji, profil roli (touches w polu karnym vs poza,
udział w dryblingu), opponent allowed per-90 pozycyjnie, sędzia (faule/mecz, kartki/faul),
implied spread + implied total z rynku 1X2, zagęszczenie terminarza, stawka meczu, derby flag.

### Ranking rynków zawodniczych z Twojej listy

| # | Rynek | Stabilność | Dane | Modelowalność | Werdykt |
|---|---|---|---|---|---|
| 1 | Shots | wysoka (λ 1.5–4 dla ofensywnych) | łatwe | najlepsza | **MVP** |
| 2 | Fouls Committed | bardzo wysoka per zawodnik | łatwe | świetna (+sędzia) | **MVP** — często miękkie linie |
| 3 | Tackles | wysoka dla DM/CB | łatwe, uwaga na definicję | dobra (game script!) | **MVP** |
| 4 | Shots On Target | średnia (~40% shots, więcej szumu) | łatwe | dobra | **MVP** |
| 5 | Fouls Won | wysoka dla dryblujących | łatwe | dobra | **MVP** |
| 6 | Interceptions Won | średnia, definicje różnią się między providerami | ryzyko settlementu | średnia | v1.5 |
| 7 | Shots Outside the Box | dobra dla specjalistów | wymaga Understat | dobra dla podzbioru graczy | v1.5 |
| 8 | First Half Shots | dobra (pochodna shots × udział 1H) | wymaga danych z minutą | dobra | v1.5 |
| 9 | Yellow Cards | binarna, wysoka wariancja | łatwe | średnia (przez faule+sędzia) | v1.5 |
| 10 | First Half Shots OT | niska (małe λ) | jw. | słaba | v2 |
| 11 | Offsides | niska (λ ~0.3–0.6 dla napastn.) | łatwe | słaba | v2 |
| 12 | Headed Shot | niska, zero-inflated | wymaga Understat | słaba poza target manami | v2 |
| 13 | Headed Shot OT | bardzo niska | jw. | bardzo słaba | v2+ |
| 14 | Shots OT Outside Box | bardzo niska (λ ~0.1–0.3) | jw. | bardzo słaba | v2+ |

**Gdzie realnie jest edge**: linie na faule, tackles i fouls won są układane bardziej algorytmicznie
i z mniejszą uwagą traderów niż strzały — tam rynek jest najmiększy. Na strzałach edge bierze się
głównie z szybszej reakcji na składy, matchup i sędziego, nie z lepszej średniej.

---

## ETAP 4 — Architektura systemu

### Podział odpowiedzialności — rekomendacja wprost

- **Frontend + lekkie API: Next.js na Vercel** ✔ (zgodnie z Twoim kierunkiem)
- **Baza: Supabase Postgres** ✔ (+ Row Level Security jeśli kiedyś multi-user, + pg_cron do prostych zadań)
- **Analityka / pipeline / model: Python, POZA Vercelem.** Piszę to wprost: ekosystem statystyczny
  (numpy/scipy/pandas, ew. PyMC) i długie joby backfillu nie pasują do funkcji request-response.
  - **MVP: GitHub Actions cron** (darmowe, proste, logi, retry) — joby: ingest, features, scoring.
  - **Docelowo: mały worker na Railway/Fly.io**, gdy pojawi się potrzeba reakcji na składy w <1 min.
  - Vercel Cron zostaje do lekkich zadań (odświeżenie widoków, rewalidacja cache, snapshot kursów
    jeśli źródło to proste API).

### Schemat bazy (rdzeń)

```
leagues, seasons, teams, referees
players (id, name, position, profile_tags)
player_team_stints (player, team, from, to)
matches (id, league, season, utc_kickoff, home, away, referee_id, status,
         implied_spread, implied_total, importance_flags)
lineups (match, player, started, minutes, position_played, confirmed_at)
player_match_stats (match, player, minutes, shots, sot, shots_outside_box,
         headed_shots, fh_shots, fouls_committed, fouls_won, tackles,
         interceptions, yellow, offsides, source, ingested_at)
team_match_stats (match, team, fouls, shots, sot, cards, possession, ...)
-- rynek
bookmakers, market_defs (kod rynku, podmiot: player/team, typ: count/binary)
odds_snapshots (id, match, entity_id, market, line, over_odds, under_odds,
         bookmaker, captured_at)          -- NIGDY nie nadpisujemy, tylko dopisujemy
-- model
model_runs (id, version, ran_at, inputs_hash)
predictions (run_id, match, entity_id, market, line, lambda, dispersion,
         p_over, ci_low, ci_high, fair_odds, factors_json)
value_bets (prediction_id, odds_snapshot_id, edge_pp, ev_pct, confidence,
         risk, rank_score, reasoning_json, status)
bet_log (user_id, value_bet_id, stake, odds_taken, closing_odds, result, clv)
calibration_reports (period, market, brier, reliability_bins_json)
```

Zasady: snapshoty kursów append-only (historia ruchu linii + CLV + przyszły backtest);
predykcje wersjonowane per model_run (porównywanie wersji modelu); `factors_json` przechowuje
rozbicie λ na czynniki → z tego generujemy uzasadnienie w UI.

### Pipeline (harmonogram)

1. **Codziennie rano**: fixtures na 7 dni, obsady sędziowskie, kontuzje/zawieszenia.
2. **Po meczach (noc)**: ingest player/team match stats, aktualizacja posteriorów i czynników przeciwnika.
3. **T-48h do T-0**: snapshoty kursów co 30–60 min (częściej blisko kickoffu).
4. **T-24h**: pierwszy scoring (przewidywane składy) → wstępny value board.
5. **T-60min (składy oficjalne)**: re-scoring dotkniętych meczów → aktualizacja boardu, flagi „lineup confirmed".
6. **Po rozliczeniu**: wyniki rynków, aktualizacja kalibracji, CLV w bet_logu.

### UI / widoki

1. **Value Board (główny)** — dzisiejsze/jutrzejsze okazje, ranking po rank_score, filtry
   (liga, rynek, min. edge, min. confidence), badge „skład potwierdzony".
2. **Karta betu** — pełny output: p_model z CI, fair odds, edge, EV, confidence, risk,
   waterfall czynników (λ_base → ×minuty → ×przeciwnik → ×sędzia → λ_final), rozkład
   prawdopodobieństwa (wykres NB z zaznaczoną linią), historia linii, ostatnie 10 występów.
3. **Karta zawodnika** — posteriory per rynek, trend, rozkład minut, splity dom/wyjazd.
4. **Karta meczu** — wszystkie wygenerowane okazje w jednym miejscu, kontekst (sędzia, game script).
5. **Kalibracja / backtest** — reliability plots, Brier per rynek, ROI symulowany i realny, CLV.
6. **Bet tracker** — zalogowane bety, wynik, closing line value.

---

## ETAP 5 — MVP (konkret)

**Zakres rozgrywek**: top 5 lig (EPL, La Liga, Serie A, Bundesliga, Ligue 1). Nie 15 — jakość
danych i miękkość linii w top 5 wystarczą do walidacji, a rozszerzenie to zmiana konfiguracji, nie kodu.

**Rynki zawodnicze v1**: Shots, Shots on Target, Fouls Committed, Fouls Won, Tackles.
**Rynki drużynowe v1**: Team Fouls (główny), Team Cards/Booking Points, Team Shots/SOT (walidacja pipeline'u).

**Musi działać od razu**:
- pełny ingest historii (min. 2 sezony wstecz — do priorów i pierwszej kalibracji),
- model warstwy 1+2 dla powyższych rynków, z modelem minut,
- ingest/wpis kursów + devig + edge + confidence,
- Value Board + Karta betu z uzasadnieniem,
- zapis predykcji i snapshotów od dnia 1 (przyszły backtest).

**Świadomie odkładamy**: rynki z Understat (outside box, headed, 1H), kartki indywidualne,
top 15 lig i puchary, alerty, automatyczny scraping kursów wielu buków, Kelly/staking module, live.

**Kolejność budowy**: schema DB → ingest statystyk + backfill → model core + walidacja offline
(kalibracja na sezonie 24/25 jako holdout) → ingest kursów → betting engine → UI.
Model walidujemy ZANIM powstanie UI — jeśli kalibracja nie działa, ładny dashboard nie ma sensu.

---

## Decyzje podjęte

- **Bukmacherzy: Superbet, Betclic, STS (rynek polski).** Konsekwencje:
  - Żaden z nich nie ma publicznego API kursów. Agregatory (OddsJam/OpticOdds/The Odds API)
    ich nie pokrywają — odpada droga „kupujemy feed".
  - Realne opcje: (a) ingest z wewnętrznych JSON-owych endpointów, które zasilają ich własne
    strony (technicznie wykonalne, kruche, szara strefa ToS), (b) ręczne/półręczne wprowadzanie
    linii w MVP dla wyselekcjonowanych meczów. Rekomendacja: start od (b) dla walidacji modelu,
    równolegle budowa (a) dla 1 bukmachera (Superbet ma najszersze player props).
  - Plus produktowy: linie polskich buków na player props są bardziej miękkie niż u Pinnacle/Bet365
    — większa szansa na edge. Minus: szybkie limitowanie wygrywających kont (poza zakresem narzędzia,
    ale wpływa na praktykę gry).
  - Devig: Superbet/Betclic zwykle kwotują obie strony (over/under) → power/Shin devig działa;
    STS często tylko over → szacowana marża per rynek.

- **Hosting: darmowe tiery Vercel + Supabase wystarczą na MVP.** Analiza:
  - **Supabase Free (500 MB DB)**: statystyki meczowe top 5 lig × 2 sezony ≈ 120–150 tys. wierszy
    player_match_stats — mieści się z dużym zapasem. Jedyny rosnący stół to `odds_snapshots`
    (append-only); przy ręcznym/półautomatycznym wpisie kursów w MVP — bez znaczenia. Uwaga:
    projekt Free jest pauzowany po 7 dniach nieaktywności (cron z GitHub Actions to załatwia
    przy okazji). Upgrade do Pro ($25/mc) dopiero, gdy ruszą automatyczne snapshoty kursów
    co 30–60 min (to potrafi urosnąć do GB w sezon).
  - **Vercel Hobby**: w pełni wystarczy na osobisty dashboard. Ograniczenia: użycie niekomercyjne
    (OK dla narzędzia osobistego) i limity cronów na Hobby — dlatego wszystkie harmonogramy
    trzymamy w **GitHub Actions (darmowe)**, nie w Vercel Cron. To i tak zgodne z architekturą
    (pipeline w Pythonie poza Vercelem).
  - **Wniosek**: hosting = 0 zł na MVP. Realny koszt projektu to dane statystyczne
    (API-Football ~$40–60/mc lub scraping za 0 zł z ryzykiem kruchości), nie infrastruktura.

## ETAP 6 — decyzje użytkownika (2026-07-02) — WSZYSTKIE ROZSTRZYGNIĘTE

1. **Kursy**: Superbet, Betclic, STS. Start od ręcznego/półręcznego wprowadzania linii,
   równolegle budowa automatycznego ingestu (Superbet ma najszersze player props).
2. **Dane statystyczne: darmowe lub bardzo tanie, ale realne i działające.**
   → ZWERYFIKOWANE 2026-07-02 realnymi requestami:
   - **Sofascore (nieoficjalne API, przez curl_cffi z impersonacją TLS Chrome) — KRĘGOSŁUP.**
     Działa: statystyki per-zawodnik-mecz (tackles, interceptions, fouls, wasFouled, shots,
     minuty), shotmap (część ciała, minuta, współrzędne, xG → rynki outside box / headed / 1H),
     statystyki drużynowe, sędzia, terminarze i sezony wstecz. Pokrywa WSZYSTKIE 14 rynków.
   - **Understat** — zapas dla strzałów (endpoint main/getPlayersStats działa).
   - **ESPN site API** — zapas dla: shots, SOT, fouls, fouls won, offsides, kartki.
   - **FBref ODPADA** — Cloudflare blokuje nawet Playwright/patchright z realnym Chrome.
   Mitygacje ryzyka (nieoficjalne API): rate-limit ~1 req/2 s, uruchamianie lokalnie z domowego
   IP użytkownika (nie z chmury!), cache surowych odpowiedzi JSON na dysku, źródła zapasowe.
   Konsekwencja: pipeline działa lokalnie na PC (Harmonogram zadań Windows), NIE na GitHub Actions.
3. **Zakres statystyk: WSZYSTKIE 14 rynków zawodniczych zbieranych od dnia 1** (decyzja
   użytkownika — pełna lista jak na statshub, nic więcej). Modelowanie nadal warstwowe
   (rzadkie rynki z ostrzejszymi progami confidence), ale ingest i UI obejmują całość od razu.
4. **Narzędzie osobiste** — jeden użytkownik, bez rozbudowanego auth.
5. **Bet tracker + CLV od razu. BEZ sugerowanych stawek (bez Kelly).**
6. **Bez alertów.**
7. **UI wyłącznie po polsku** — prosty, klarowny język, bez żargonu; każdy wskaźnik
   opisany zrozumiale (np. „przewaga nad kursem" zamiast „edge" tam, gdzie się da,
   z tooltipami wyjaśniającymi).
8. **Design**: wg `docs/frontend-design-skill.md` — dopracowany wizualnie, animacje,
   pełna responsywność, estetyka priorytetem.
9. **Kontekst czasowy**: lipiec 2026 — przerwa ligowa (trwają MŚ). Idealny moment na
   backfill historii top 5 lig i walidację modelu przed startem sezonu 2026/27.
