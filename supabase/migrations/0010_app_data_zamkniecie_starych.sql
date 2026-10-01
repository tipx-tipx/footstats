-- =============================================================================
-- Migracja 0010: zamknięcie publicznego odczytu kluczy, których nowa strona
-- już nie czyta (redesign, 2026-10-01).
--
--   * `players`       – pełna kadra (~44 MB); strona czyta koszyki
--                       `players_typy`, `players_dNN` i `zaw_kNN`,
--   * `odrzucenia`    – rejestr „czemu ta para nie dostała typu” (~17 MB);
--                       czytała go stara strona Drużyny, nowa nie,
--   * `sts_value`, `pokrycie_liga` – stare panele, nowa strona ich nie ma,
--   * `odds_superbet` – siatka z jedną ceną bez nazwy bukmachera; strona czyta
--                       `kursy_mNN` (obaj bukmacherzy osobno).
-- Pipeline pisze i czyta je dalej kluczem service_role (omija RLS) – np. job
-- STS korzysta z `odrzucenia`. Zamykamy tylko odczyt anonimowy.
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase (jak 0004–0009), PO wdrożeniu
-- strony, która tych kluczy już nie czyta. Zgodności listy z kodem pilnuje
-- `npm run test:klucze`.
-- =============================================================================
alter table app_data enable row level security;

drop policy if exists "app_data public read" on app_data;
drop policy if exists "app_data anon czyta klucze strony" on app_data;

create policy "app_data anon czyta klucze strony"
    on app_data for select
    to anon
    using ((regexp_replace(key, '__cz[0-9]+$', '') in (
        'value_bets',
        'matches',
        'players_typy',
        'calibration',
        'meta',
        'kupony',
        'typy_wyniki',
        'legi_pool',
        'druzyny_forma',
        'radar',
        'zaw_indeks'
    )) or regexp_replace(key, '__cz[0-9]+$', '') ~ '^(players_d|zaw_k|kursy_m)[0-9]{2}$');
