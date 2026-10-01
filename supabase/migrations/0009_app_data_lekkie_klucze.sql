-- =============================================================================
-- Migracja 0009: lekkie klucze nowej strony (redesign 7B, 2026-10-01).
--
-- Pipeline (`jobs/lekkie_klucze.py`) wysyła obok dotychczasowych:
--   * `kursy_m00`..`kursy_m31` — kursy na zawodników per mecz, OSOBNO Superbet
--                               i Betclic (strona meczu czyta jeden koszyk),
--   * `zaw_k00`..`zaw_k63`     — strona zawodnika: jeden koszyk po numerze
--                               zawodnika (10 meczów historii + jego kursy),
--   * `zaw_indeks`             — zawodnicy z kursem albo typem (wyszukiwarka;
--                               czytany na serwerze, do przeglądarki idą
--                               tylko trafienia).
-- Reszta listy bez zmian względem 0008 – stare klucze zostają jako zapas
-- (strona wraca do nich, gdy nowych jeszcze nie ma).
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase PRZED wdrożeniem redesignu (jak
-- 0004–0008). Bez tego strona nie widzi nowych kluczy: działa na starych,
-- ale strona meczu podpisuje cenę Betclica jako Superbet, a transfer się nie
-- zmniejsza. Zgodności listy z kodem pilnuje `npm run test:klucze`.
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
        'players',
        'players_typy',
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
        'zaw_indeks'
    )) or regexp_replace(key, '__cz[0-9]+$', '') ~ '^(players_d|zaw_k|kursy_m)[0-9]{2}$');
