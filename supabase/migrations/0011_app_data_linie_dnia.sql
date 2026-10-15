-- =============================================================================
-- Migracja 0011: klucz `linie_dnia` (Mecze › „Najlepsze linie”, 2026-10-15).
--
-- Pipeline (`lekkie_klucze.klucz_linii_dnia`, wysyłka w `push_supabase`)
-- liczy linie ze WSZYSTKICH meczów naraz: cena ≥ 1,30, pokrycie ≥ 70%,
-- ~190 KB. Bez niego strona musiałaby ciągnąć 96 koszyków (~29 MB).
-- Lista = 0010 + `linie_dnia`; reszta bez zmian.
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase (jak 0004–0010) PRZED wdrożeniem
-- strony z „Najlepszymi liniami”. Bez tego zakładka pokaże „Linie pojawią się
-- po najbliższym odświeżeniu danych”, a lista meczów – bez „mocnych linii”.
-- Zgodności listy z kodem pilnuje `npm run test:klucze`.
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
        'zaw_indeks',
        'linie_dnia'
    )) or regexp_replace(key, '__cz[0-9]+$', '') ~ '^(players_d|zaw_k|kursy_m)[0-9]{2}$');
