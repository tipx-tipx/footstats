-- =============================================================================
-- Migracja 0003: atomowy merge/usunięcie kluczy w app_data.payload (JSONB).
--
-- Dlaczego: api/kupon-pomin i api/login (rate-limit) robią read-modify-write
-- z klienta (fetch GET payload -> zmień w JS -> POST cały payload z powrotem).
-- Dwa równoległe żądania do TEGO SAMEGO klucza (np. dwie karty przeglądarki,
-- albo klik + auto-retry) mogą się nadpisać: B czyta przed zapisem A, B
-- zapisuje nadpisując zmianę A (lost update). Narzędzie jest osobiste
-- (jeden user — patrz 0001), więc ryzyko jest rzadkie i niskiej wagi, ale
-- funkcja niżej eliminuje całą klasę tego problemu jednym atomowym
-- zapytaniem SQL zamiast dwóch żądań HTTP w kliencie.
--
-- merge_app_data(p_key, p_patch, p_remove) atomowo:
--   1) merguje płytko p_patch w istniejący payload (nowe/zmienione klucze),
--   2) usuwa top-level klucze wymienione w p_remove,
--   3) tworzy wiersz, jeśli klucz jeszcze nie istnieje.
-- Wywoływane przez PostgREST jako POST /rest/v1/rpc/merge_app_data.
-- Aplikacja (web/src/app/api/*) wywołuje to z GRACEFUL FALLBACK do starego
-- read-modify-write, gdy RPC jeszcze nie istnieje (migracja niezaaplikowana)
-- — więc wdrożenie kodu jest bezpieczne niezależnie od kolejności.
-- =============================================================================

create or replace function merge_app_data(
    p_key text,
    p_patch jsonb default '{}'::jsonb,
    p_remove text[] default '{}'::text[]
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    result jsonb;
begin
    insert into app_data (key, payload, updated_at)
    values (p_key, p_patch, now())
    on conflict (key) do update
        set payload = (app_data.payload || excluded.payload) - p_remove,
            updated_at = now()
    returning payload into result;
    return result;
end;
$$;

-- service_role omija RLS (jak reszta zapisów pipeline'u); funkcja SECURITY
-- DEFINER + search_path ustawiony jawnie (dobra praktyka, nie do obejścia).
revoke all on function merge_app_data(text, jsonb, text[]) from public;
grant execute on function merge_app_data(text, jsonb, text[]) to service_role;
