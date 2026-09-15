-- =============================================================================
-- Migracja 0007: zdjęcie klucza `rywale` z odczytu dla anon (2026-09-15).
--
-- Ekran /rywale usunięty decyzją właściciela (pomiar 14.09: ranking rywali nie
-- poprawia trafności typów, a rywal i tak jest opisany na karcie typu). Cykl
-- przestał liczyć klucz, więc wystawianie go anonimowo byłoby martwym
-- wyciekiem. Stary wiersz `rywale` (pusta lista) można skasować w bazie.
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase (jak 0004–0006). Zgodności listy
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
        'pokrycie_liga'
    ));

delete from app_data where key = 'rywale';
