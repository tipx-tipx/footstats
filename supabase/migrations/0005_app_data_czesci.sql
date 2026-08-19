-- =============================================================================
-- Migracja 0005: anon widzi także CZĘŚCI kluczy, które i tak wolno mu czytać.
--
-- PO CO: od 2026-08-19 klucz cięższy niż ~4 MB nie jedzie do bazy w całości,
-- tylko w kawałkach `<klucz>__cz00`, `<klucz>__cz01`… a pod głównym kluczem
-- zostaje marker `{"__czesci": n}` (patrz `supa.py`, sekcja SZARDY). Powód
-- jest twardy — zmierzone czasy upsertu tej samej struktury:
--
--      2 MB → 2,3 s     8 MB →  7,8 s     12 MB → 34,8 s
--      4 MB → 5,1 s    10 MB → 23,2 s     14 MB → 500 (57014 timeout)
--
-- `players` waży 9,1 MB i to on wywalał cały cykl po 36 minutach liczenia.
--
-- PROBLEM, KTÓRY TA MIGRACJA ZAŁATWIA: polityka z 0004 wylicza dozwolone
-- klucze z nazwy. `players` jest na liście, ale `players__cz00` już nie —
-- więc strona dostałaby marker i ANI JEDNEJ części. A brak wiersza to dla
-- PostgREST nie błąd, tylko pusta odpowiedź: `fetchKlucz` podstawiłby dane
-- DEMO i Zawodnicy wyglądaliby na sprawnych, pokazując wymyślone mecze.
--
-- ROZWIĄZANIE: zanim porównamy nazwę z listą, obcinamy sufiks `__czNN`.
-- Dzięki temu lista pozostaje JEDNA i nie trzeba jej ruszać, gdy któryś
-- kolejny klucz przekroczy próg (`typy_wyniki` ma dziś 4,2 MB, więc będzie
-- następny). Klucz wewnętrzny, którego na liście nie ma, dalej jest
-- niewidoczny — razem ze swoimi częściami.
--
-- LISTA MUSI SIĘ ZGADZAĆ Z `BUNDLE_KEYS` + `fetchKlucz()` w
-- `web/src/lib/data.ts`. Pilnuje tego `npm run test:klucze`.
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
