-- =============================================================================
-- Migracja 0006: klucz `rywale` (ekran „Rywale", 2026-09-14) czytelny dla anon.
--
-- Ekran /rywale czyta leniwie klucz `rywale` (koncesje rywali w meczach
-- z najbliższych 3 dni, ~100 kB). Polityka z 0005 wylicza dozwolone klucze
-- z nazwy, więc nowy klucz trzeba dopisać — inaczej PostgREST oddaje pustą
-- odpowiedź, a strona pokazuje „brak profili" mimo danych w bazie.
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase (jak 0004/0005). Zgodności listy
-- z `BUNDLE_KEYS` + `fetchKlucz()` pilnuje `npm run test:klucze`.
-- =============================================================================
alter table app_data enable row level security;

drop policy if exists "app_data public read" on app_data;
drop policy if exists "app_data anon czyta klucze strony" on app_data;

create policy "app_data anon czyta klucze strony"
    on app_data for select
    to anon
    using (regexp_replace(key, '__cz[0-9]+$', '') in (
        'value_bets',
        'matches',
        'players',
        'calibration',
        'meta',
        'kupony',
        'typy_wyniki',
        'odds_superbet',
        'legi_pool',
        'odrzucenia',
        'sts_value',
        'druzyny_forma',
        'radar',
        'pokrycie_liga',
        'rywale'
    ));
