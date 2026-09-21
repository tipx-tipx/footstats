-- =============================================================================
-- Migracja 0009: imienny rentgen drabinek (2026-09-21).
--
-- Radar zapisuje tu dla KAŻDEJ pary (mecz, zawodnik) z oferty bramę, na której
-- para odpadła („rzadko_w_pierwszym_skladzie", „sito_pokrycie_ponizej_6_z_10",
-- …) albo „karta" z miejscem — jeden wiersz na parę, ~300 B, nadpisywany co
-- cykl. Dotąd rentgen radaru trzymał wyłącznie SUMY per brama, więc na pytanie
-- „czemu nie było Mandragory?" nie było odpowiedzi po meczu (sesja 21.09).
--
-- DLACZEGO TABELA, A NIE KLUCZ W `app_data`: klucz trzeba czytać, żeby go
-- dopisać (70 cykli/dobę × MB = transfer, który dwa razy zatrzymał projekt).
-- Upsert z `Prefer: return=minimal` nie odsyła nic. Czyta wyłącznie człowiek,
-- po nazwisku (`python -m footstats.jobs.radar_imienny Mandragora`).
-- Wiersze starsze niż 4 dni kasuje cykl.
--
-- ⚑ WKLEIĆ RĘCZNIE w SQL Editorze Supabase (jak 0004–0008). Bez tego cykl
-- pisze raz na przebieg „tabeli nie ma — wklej migrację" i idzie dalej.
-- =============================================================================
create table if not exists public.radar_imienny (
    mecz_id     bigint      not null,
    podmiot_id  bigint      not null,
    dzien       date        not null,
    mecz        text,
    podmiot     text,
    druzyna     text,
    brama       text        not null,
    szczegol    text,
    cykl_ts     bigint      not null,
    primary key (mecz_id, podmiot_id)
);

create index if not exists radar_imienny_dzien_idx on public.radar_imienny (dzien);
create index if not exists radar_imienny_podmiot_idx on public.radar_imienny (podmiot);

alter table public.radar_imienny enable row level security;

-- pipeline pisze kluczem service (omija RLS); klucz anon tylko czyta —
-- to jest narzędzie diagnostyczne właściciela, nie dane strony
drop policy if exists "radar_imienny anon czyta" on public.radar_imienny;
create policy "radar_imienny anon czyta"
    on public.radar_imienny for select
    to anon
    using (true);
