-- =============================================================================
-- Migracja 0004: odczyt anonimowy TYLKO tych kluczy, które strona pokazuje.
--
-- STAN PRZED: `app_data public read` z `using (true)`. Kto ma klucz anon, czyta
-- CAŁĄ tabelę — a leżą w niej rzeczy, których strona nigdy nie pokazuje:
--
--     typy_log        ~1,7 MB   pełna księga rozliczeń, każdy typ z historii
--     styl_bank_liga  ~2,6 MB   bank stylu drużyn
--     trend_lib       ~5,3 MB   biblioteka trendów
--     publikacje_typy           rejestr publikacji z pełnym rachunkiem
--     kupony_log / kupony_pominiete / kalibracja / diagnostyka
--
-- Klucz anon jest w Supabase z założenia PUBLICZNY (Supabase dokumentuje go
-- jako bezpieczny do wysłania do przeglądarki) — jedyne, co dziś chroni te
-- dane, to fakt, że akurat nie wstawiamy go do kodu klienta. To nie jest
-- zabezpieczenie, to zbieg okoliczności: jedna zmienna `NEXT_PUBLIC_` od
-- wycieku całej kuchni modelu.
--
-- STAN PO: anon widzi wyłącznie 14 kluczy, które i tak jadą do przeglądarki
-- w renderze strony. Nic nie ubywa użytkownikowi.
--
-- PIPELINE NIETKNIĘTY: `service_role` omija RLS w całości, więc zapis i odczyt
-- wewnętrznych kluczy (rozliczanie, bank stylu, rejestr) działa jak dotąd.
--
-- LISTA MUSI SIĘ ZGADZAĆ Z `BUNDLE_KEYS` w `web/src/lib/data.ts`. Pilnuje tego
-- test `npm run test:klucze` — bez niego rozjazd jest CICHY: PostgREST nie
-- zwraca błędu, tylko mniej wierszy, a `fetchBundle` podstawia pod brakujący
-- klucz dane demo. Strona wygląda wtedy na działającą i pokazuje wymyślone
-- mecze. Dokładnie ta klasa błędu co front trzymający kopię konfiguracji
-- backendu (patrz KuponyScena i przedziały kursowe).
-- =============================================================================

alter table app_data enable row level security;

drop policy if exists "app_data public read" on app_data;
drop policy if exists "app_data anon czyta klucze strony" on app_data;

create policy "app_data anon czyta klucze strony"
    on app_data for select
    to anon
    using (key in (
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
