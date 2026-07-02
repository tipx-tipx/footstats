-- =============================================================================
-- Migracja 0002: prosta tabela snapshotów dla aplikacji (MVP hostingu na Vercel).
--
-- Aplikacja czyta gotowe JSON-y (value_bets, matches, players, calibration, meta).
-- Zamiast mapować je od razu w pełny znormalizowany schemat (0001 — zostaje pod
-- przyszłą analitykę), trzymamy je jako JSONB pod kluczem. Pipeline wypycha 5
-- wierszy, aplikacja czyta najnowsze. Proste, szybkie, działa od ręki.
-- =============================================================================

create table if not exists app_data (
    key         text primary key,        -- 'value_bets' | 'matches' | 'players' | 'calibration' | 'meta'
    payload     jsonb not null,
    updated_at  timestamptz not null default now()
);

-- Publiczny ODCZYT (aplikacja czyta anon key). Zapis tylko service_role (pipeline).
alter table app_data enable row level security;

drop policy if exists "app_data public read" on app_data;
create policy "app_data public read"
    on app_data for select
    using (true);

-- service_role omija RLS, więc zapis z pipeline działa bez dodatkowej polityki.
