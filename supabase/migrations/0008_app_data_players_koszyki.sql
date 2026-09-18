-- =============================================================================
-- Migracja 0008: zawodnicy w kawałkach dla strony (2026-09-18).
--
-- Pełny `players` (~44 MB) szedł na stronę w całości przy każdym odświeżeniu
-- i to on zjadał prawie cały dzienny transfer Supabase (panel 18.09: 1,03 GB
-- w 9 dni przy limicie Free 5 GB/mies.). Pipeline wysyła obok niego:
--   * `players_typy`            — zawodnicy z typami (strona główna, ~50 KB),
--   * `players_d00`..`players_d95` — koszyki po nazwie drużyny (strona meczu,
--                                  2 koszyki ≈ 1–3 MB zamiast 44 MB).
-- Pełny `players` ZOSTAJE na liście — strona wraca do niego, gdy nowych
-- kluczy jeszcze nie ma (pierwszy cykl po wdrożeniu).
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase (jak 0004–0007). Bez tego strona
-- nie widzi nowych kluczy i dalej czyta pełny `players` — nic się nie psuje,
-- ale transfer się nie zmniejsza. Zgodności listy z kodem pilnuje
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
        'pokrycie_liga'
    )) or regexp_replace(key, '__cz[0-9]+$', '') ~ '^players_d[0-9]{2}$');
