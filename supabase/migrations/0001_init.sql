-- =============================================================================
-- FootStats Value Engine — schemat bazy danych (Supabase Postgres)
-- Migracja 0001: pełny rdzeń systemu
--
-- Zasady projektowe:
--  * odds_snapshots jest APPEND-ONLY — nigdy nie nadpisujemy kursów,
--    każdy odczyt linii to nowy wiersz (historia ruchu linii + CLV + backtest).
--  * predictions są wersjonowane przez model_runs — można porównywać wersje modelu.
--  * Wszystkie 14 rynków zawodniczych zbieramy od dnia 1 (decyzja użytkownika).
--  * Narzędzie osobiste: RLS wyłączone, dostęp przez service key / anon key.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Słowniki podstawowe
-- ---------------------------------------------------------------------------

create table leagues (
    id          bigint generated always as identity primary key,
    code        text not null unique,          -- np. 'EPL', 'LALIGA', 'SERIE_A', 'BUNDES', 'LIGUE1'
    name        text not null,                 -- nazwa po polsku, np. 'Premier League'
    country     text,
    tier        smallint default 1,
    -- identyfikatory w źródłach danych
    understat_code  text,                      -- np. 'EPL'
    fbref_comp_id   text                       -- np. '9'
);

create table seasons (
    id          bigint generated always as identity primary key,
    league_id   bigint not null references leagues(id),
    label       text not null,                 -- np. '2025/26'
    start_year  smallint not null,             -- np. 2025
    unique (league_id, start_year)
);

create table teams (
    id          bigint generated always as identity primary key,
    name        text not null,
    short_name  text,
    country     text,
    understat_id    text,
    fbref_id        text,
    unique (name, country)
);

create table referees (
    id          bigint generated always as identity primary key,
    name        text not null unique,
    country     text
);

-- Zagregowane profile sędziów (odświeżane przez pipeline; per sezon i liga)
create table referee_season_stats (
    id              bigint generated always as identity primary key,
    referee_id      bigint not null references referees(id),
    season_id       bigint not null references seasons(id),
    matches         int not null default 0,
    fouls_per_match     numeric,     -- gwizdane faule / mecz
    cards_per_match     numeric,     -- żółte kartki / mecz
    cards_per_foul      numeric,     -- surowość: kartki / faul
    fouls_multiplier    numeric,     -- vs średnia ligi (1.0 = neutralny)
    cards_multiplier    numeric,
    updated_at      timestamptz not null default now(),
    unique (referee_id, season_id)
);

create table players (
    id          bigint generated always as identity primary key,
    full_name   text not null,
    known_as    text,                          -- nazwisko wyświetlane, np. 'Lewandowski'
    birth_date  date,
    position    text,                          -- główna pozycja: GK/DF/MF/FW (+ szczegóły w profile)
    profile     jsonb not null default '{}',   -- rola, styl: {"rola":"skrzydłowy","drybler":true,...}
    understat_id    text,
    fbref_id        text
);

create index players_name_idx on players (full_name);

-- Przynależność klubowa w czasie (transfery)
create table player_team_stints (
    id          bigint generated always as identity primary key,
    player_id   bigint not null references players(id),
    team_id     bigint not null references teams(id),
    from_date   date not null,
    to_date     date                           -- null = obecny klub
);

create index stints_player_idx on player_team_stints (player_id, from_date desc);

-- ---------------------------------------------------------------------------
-- Mecze
-- ---------------------------------------------------------------------------

create type match_status as enum ('zaplanowany', 'trwa', 'zakonczony', 'przelozony', 'odwolany');

create table matches (
    id              bigint generated always as identity primary key,
    season_id       bigint not null references seasons(id),
    round           text,                      -- kolejka / faza
    utc_kickoff     timestamptz not null,
    home_team_id    bigint not null references teams(id),
    away_team_id    bigint not null references teams(id),
    referee_id      bigint references referees(id),
    status          match_status not null default 'zaplanowany',
    home_goals      smallint,
    away_goals      smallint,
    -- kontekst z rynku meczowego (kursy 1X2 / handicap / gole jako cechy modelu)
    implied_home_prob   numeric,               -- prawdopodobieństwo wygranej gospodarzy z kursów (po devigu)
    implied_spread      numeric,               -- implikowana różnica goli (dodatnia = gospodarze faworytem)
    implied_total       numeric,               -- implikowana suma goli
    importance      jsonb not null default '{}',  -- {"derby":true,"o_stawke":"utrzymanie",...}
    understat_id    text,
    fbref_id        text,
    unique (season_id, utc_kickoff, home_team_id, away_team_id)
);

create index matches_kickoff_idx on matches (utc_kickoff);
create index matches_status_idx on matches (status, utc_kickoff);

-- Składy: przewidywane i oficjalne
create table lineups (
    id              bigint generated always as identity primary key,
    match_id        bigint not null references matches(id),
    player_id       bigint not null references players(id),
    team_id         bigint not null references teams(id),
    started         boolean,                   -- wyszedł w pierwszym składzie
    minutes         smallint,                  -- rozegrane minuty (po meczu)
    position_played text,
    is_official     boolean not null default false,  -- false = przewidywany skład, true = ogłoszony
    confirmed_at    timestamptz,
    unique (match_id, player_id, is_official)
);

create index lineups_match_idx on lineups (match_id);
create index lineups_player_idx on lineups (player_id);

-- ---------------------------------------------------------------------------
-- Statystyki meczowe — WSZYSTKIE 14 rynków zawodniczych od dnia 1
-- ---------------------------------------------------------------------------

create table player_match_stats (
    id                  bigint generated always as identity primary key,
    match_id            bigint not null references matches(id),
    player_id           bigint not null references players(id),
    team_id             bigint not null references teams(id),
    minutes             smallint not null default 0,
    started             boolean,
    -- strzały (FBref + Understat)
    shots               smallint,
    shots_on_target     smallint,
    shots_outside_box   smallint,   -- z Understat (x,y strzału)
    sot_outside_box     smallint,
    headed_shots        smallint,   -- z Understat (część ciała)
    headed_sot          smallint,
    fh_shots            smallint,   -- strzały w 1. połowie (z minuty strzału)
    fh_sot              smallint,
    shots_blocked       smallint,   -- strzały zablokowane przez obrońców
    shots_off_target    smallint,   -- strzały niecelne (obok + słupek)
    -- gra bez piłki / dyscyplina (FBref)
    fouls_committed     smallint,
    fouls_won           smallint,
    tackles             smallint,
    interceptions       smallint,
    offsides            smallint,
    yellow_cards        smallint,
    red_cards           smallint,
    source              text not null default 'fbref+understat',
    ingested_at         timestamptz not null default now(),
    unique (match_id, player_id)
);

create index pms_player_idx on player_match_stats (player_id, match_id);
create index pms_match_idx on player_match_stats (match_id);

-- Surowe strzały (z Understat) — źródło prawdy dla rynków pochodnych strzałów
create table shot_events (
    id              bigint generated always as identity primary key,
    match_id        bigint not null references matches(id),
    player_id       bigint not null references players(id),
    minute          smallint not null,
    x               numeric,        -- współrzędne Understat (0..1)
    y               numeric,
    body_part       text,           -- 'noga_prawa','noga_lewa','glowa','inne'
    situation       text,           -- 'otwarta_gra','staly_fragment','kontra','rzut_wolny','rozny'
    result          text,           -- 'gol','obroniony','zablokowany','niecelny','slupek'
    is_on_target    boolean,
    is_outside_box  boolean,        -- wyliczone z (x,y)
    xg              numeric,
    understat_id    text unique
);

create index shots_player_idx on shot_events (player_id);
create index shots_match_idx on shot_events (match_id);

create table team_match_stats (
    id              bigint generated always as identity primary key,
    match_id        bigint not null references matches(id),
    team_id         bigint not null references teams(id),
    is_home         boolean not null,
    fouls           smallint,
    fouls_won       smallint,
    shots           smallint,
    shots_on_target smallint,
    yellow_cards    smallint,
    red_cards       smallint,
    offsides        smallint,
    corners         smallint,
    possession      numeric,
    source          text not null default 'fbref',
    ingested_at     timestamptz not null default now(),
    unique (match_id, team_id)
);

create index tms_team_idx on team_match_stats (team_id, match_id);

-- ---------------------------------------------------------------------------
-- Rynki i kursy
-- ---------------------------------------------------------------------------

create table bookmakers (
    id      bigint generated always as identity primary key,
    code    text not null unique,      -- 'superbet', 'betclic', 'sts'
    name    text not null
);

insert into bookmakers (code, name) values
    ('superbet', 'Superbet'),
    ('betclic', 'Betclic'),
    ('sts', 'STS');

create type entity_kind as enum ('zawodnik', 'druzyna');
create type market_kind as enum ('licznik', 'binarny');   -- licznik = over/under liczby zdarzeń

create table market_defs (
    id          bigint generated always as identity primary key,
    code        text not null unique,
    entity      entity_kind not null,
    kind        market_kind not null,
    name_pl     text not null,             -- pełna polska nazwa w UI
    short_pl    text not null,             -- krótka etykieta
    description_pl text not null,          -- proste wyjaśnienie dla użytkownika
    stat_column text not null,             -- kolumna w player/team_match_stats
    rare        boolean not null default false,  -- rynek rzadkich zdarzeń → ostrzejsze progi
    sort_order  smallint not null default 100
);

insert into market_defs (code, entity, kind, name_pl, short_pl, description_pl, stat_column, rare, sort_order) values
    ('shots',             'zawodnik', 'licznik', 'Strzały',                            'Strzały',            'Wszystkie strzały zawodnika w meczu.', 'shots', false, 10),
    ('sot',               'zawodnik', 'licznik', 'Strzały celne',                      'Celne',              'Strzały w światło bramki.', 'shots_on_target', false, 20),
    ('shots_outside_box', 'zawodnik', 'licznik', 'Strzały zza pola karnego',           'Zza pola',           'Strzały oddane spoza pola karnego.', 'shots_outside_box', false, 30),
    ('sot_outside_box',   'zawodnik', 'licznik', 'Strzały celne zza pola karnego',     'Celne zza pola',     'Celne strzały spoza pola karnego. Rzadkie zdarzenie — ostrożnie.', 'sot_outside_box', true, 40),
    ('headed_shots',      'zawodnik', 'licznik', 'Strzały głową',                      'Głową',              'Strzały oddane głową. Rzadkie zdarzenie — ostrożnie.', 'headed_shots', true, 50),
    ('headed_sot',        'zawodnik', 'licznik', 'Celne strzały głową',                'Celne głową',        'Celne strzały głową. Bardzo rzadkie zdarzenie.', 'headed_sot', true, 60),
    ('fh_shots',          'zawodnik', 'licznik', 'Strzały w 1. połowie',               'Strzały 1P',         'Strzały oddane do przerwy.', 'fh_shots', false, 70),
    ('fh_sot',            'zawodnik', 'licznik', 'Strzały celne w 1. połowie',         'Celne 1P',           'Celne strzały do przerwy. Rzadkie zdarzenie — ostrożnie.', 'fh_sot', true, 80),
    ('fouls_committed',   'zawodnik', 'licznik', 'Faule popełnione',                   'Faule',              'Faule popełnione przez zawodnika.', 'fouls_committed', false, 90),
    ('fouls_won',         'zawodnik', 'licznik', 'Faule wywalczone',                   'Wywalczone',         'Faule na zawodniku (przeciwnik fauluje jego).', 'fouls_won', false, 100),
    ('tackles',           'zawodnik', 'licznik', 'Odbiory',                            'Odbiory',            'Skuteczne wślizgi i odbiory piłki.', 'tackles', false, 110),
    ('interceptions',     'zawodnik', 'licznik', 'Przechwyty',                         'Przechwyty',         'Przechwycone podania przeciwnika.', 'interceptions', false, 120),
    ('yellow_card',       'zawodnik', 'binarny', 'Żółta kartka',                       'Żółta',              'Czy zawodnik dostanie żółtą kartkę.', 'yellow_cards', false, 130),
    ('offsides',          'zawodnik', 'licznik', 'Spalone',                            'Spalone',            'Pozycje spalone zawodnika. Rzadkie zdarzenie — ostrożnie.', 'offsides', true, 140),
    ('shots_blocked',     'zawodnik', 'licznik', 'Strzały zablokowane',                'Zablokowane',        'Strzały zawodnika zablokowane przez obrońców.', 'shots_blocked', false, 150),
    ('shots_off_target',  'zawodnik', 'licznik', 'Strzały niecelne',                   'Niecelne',           'Strzały obok bramki (w tym słupek i poprzeczka).', 'shots_off_target', false, 160),
    ('team_fouls',        'druzyna',  'licznik', 'Faule drużyny',                      'Faule drużyny',      'Wszystkie faule popełnione przez drużynę.', 'fouls', false, 200),
    ('team_cards',        'druzyna',  'licznik', 'Kartki drużyny',                     'Kartki drużyny',     'Żółte kartki dla drużyny.', 'yellow_cards', false, 210),
    ('team_shots',        'druzyna',  'licznik', 'Strzały drużyny',                    'Strzały drużyny',    'Wszystkie strzały drużyny.', 'shots', false, 220),
    ('team_sot',          'druzyna',  'licznik', 'Strzały celne drużyny',              'Celne drużyny',      'Celne strzały drużyny.', 'shots_on_target', false, 230);

-- Kursy: APPEND-ONLY. entity_id wskazuje na players.id lub teams.id zależnie od rynku.
create table odds_snapshots (
    id              bigint generated always as identity primary key,
    match_id        bigint not null references matches(id),
    market_id       bigint not null references market_defs(id),
    entity_id       bigint not null,
    line            numeric not null,          -- np. 0.5, 1.5, 2.5 (dla binarnych: 0.5)
    over_odds       numeric,                   -- kurs na "powyżej" / "tak"
    under_odds      numeric,                   -- kurs na "poniżej" / "nie" (może być null — jednostronne)
    bookmaker_id    bigint not null references bookmakers(id),
    captured_at     timestamptz not null default now(),
    source          text not null default 'reczny'   -- 'reczny' | 'scraper'
);

create index odds_match_idx on odds_snapshots (match_id, market_id, entity_id, line, bookmaker_id, captured_at desc);

-- Najnowszy kurs dla każdej kombinacji (widok pomocniczy)
create view latest_odds as
select distinct on (match_id, market_id, entity_id, line, bookmaker_id)
    id, match_id, market_id, entity_id, line, over_odds, under_odds, bookmaker_id, captured_at, source
from odds_snapshots
order by match_id, market_id, entity_id, line, bookmaker_id, captured_at desc;

-- ---------------------------------------------------------------------------
-- Model i predykcje
-- ---------------------------------------------------------------------------

create table model_runs (
    id              bigint generated always as identity primary key,
    model_version   text not null,             -- np. 'v0.1.0'
    ran_at          timestamptz not null default now(),
    lineups_official boolean not null default false,  -- czy scoring po oficjalnych składach
    notes           text
);

create table predictions (
    id              bigint generated always as identity primary key,
    run_id          bigint not null references model_runs(id),
    match_id        bigint not null references matches(id),
    market_id       bigint not null references market_defs(id),
    entity_id       bigint not null,
    line            numeric not null,
    -- parametry rozkładu predykcyjnego (Gamma-Poisson → ujemny dwumianowy)
    lambda          numeric not null,          -- oczekiwana liczba zdarzeń w meczu
    dispersion      numeric,                   -- parametr naddyspersji (null = Poisson)
    p_over          numeric not null,          -- P(wynik > linia)
    ci_low          numeric,                   -- dolna granica przedziału (95%)
    ci_high         numeric,
    fair_odds       numeric not null,          -- 1 / p_over
    expected_minutes numeric,
    factors         jsonb not null default '{}',  -- rozbicie: {"baza_90":1.8,"minuty":0.93,"rywal":1.08,...}
    created_at      timestamptz not null default now(),
    unique (run_id, match_id, market_id, entity_id, line)
);

create index pred_match_idx on predictions (match_id, market_id, entity_id);

create type confidence_level as enum ('niska', 'srednia', 'wysoka');
create type risk_level as enum ('niskie', 'srednie', 'wysokie');
create type bet_side as enum ('powyzej', 'ponizej');

-- Okazje: predykcja × kurs
create table value_bets (
    id              bigint generated always as identity primary key,
    prediction_id   bigint not null references predictions(id),
    odds_snapshot_id bigint not null references odds_snapshots(id),
    side            bet_side not null,
    model_prob      numeric not null,          -- P modelu dla wybranej strony
    implied_prob    numeric not null,          -- P z kursu po usunięciu marży
    edge_pp         numeric not null,          -- przewaga w punktach procentowych
    ev_pct          numeric not null,          -- wartość oczekiwana zakładu w %
    confidence      confidence_level not null,
    confidence_score numeric not null,         -- 0-100
    risk            risk_level not null,
    rank_score      numeric not null,          -- do sortowania listy okazji
    reasoning       jsonb not null default '{}',  -- uzasadnienie po polsku dla UI
    created_at      timestamptz not null default now(),
    unique (prediction_id, odds_snapshot_id, side)
);

create index vb_rank_idx on value_bets (rank_score desc);

-- ---------------------------------------------------------------------------
-- Moje zakłady (tracker + CLV, bez sugerowanych stawek)
-- ---------------------------------------------------------------------------

create type bet_result as enum ('oczekuje', 'wygrany', 'przegrany', 'zwrot');

create table bet_log (
    id              bigint generated always as identity primary key,
    value_bet_id    bigint references value_bets(id),   -- null = zakład spoza systemu
    match_id        bigint not null references matches(id),
    market_id       bigint not null references market_defs(id),
    entity_id       bigint not null,
    side            bet_side not null,
    line            numeric not null,
    odds_taken      numeric not null,          -- kurs, po którym postawiono
    stake           numeric,                   -- stawka (opcjonalna, do ROI)
    bookmaker_id    bigint references bookmakers(id),
    placed_at       timestamptz not null default now(),
    closing_odds    numeric,                   -- kurs zamknięcia (do CLV)
    clv_pct         numeric,                   -- (odds_taken / closing_odds - 1) * 100
    result          bet_result not null default 'oczekuje',
    actual_value    numeric,                   -- faktyczna liczba zdarzeń po meczu
    notes           text
);

create index betlog_placed_idx on bet_log (placed_at desc);

-- ---------------------------------------------------------------------------
-- Kalibracja modelu
-- ---------------------------------------------------------------------------

create table calibration_reports (
    id              bigint generated always as identity primary key,
    model_version   text not null,
    market_id       bigint references market_defs(id),   -- null = wszystkie rynki łącznie
    period_start    date not null,
    period_end      date not null,
    n_predictions   int not null,
    brier_score     numeric,
    log_loss        numeric,
    reliability     jsonb not null default '[]',  -- kubełki: [{"p_pred":0.55,"p_real":0.53,"n":120},...]
    created_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Czynniki drużynowe "ile rywal dopuszcza" (odświeżane przez pipeline)
-- ---------------------------------------------------------------------------

create table team_concession_factors (
    id              bigint generated always as identity primary key,
    team_id         bigint not null references teams(id),
    season_id       bigint not null references seasons(id),
    market_code     text not null,             -- rynek, którego dotyczy czynnik
    factor          numeric not null,          -- 1.0 = liga średnio; 1.15 = dopuszcza 15% więcej
    sample_matches  int not null,
    updated_at      timestamptz not null default now(),
    unique (team_id, season_id, market_code)
);
