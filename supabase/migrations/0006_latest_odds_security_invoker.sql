-- Doradca Supabase (2026-09-13): CRITICAL „Security Definer View" na
-- public.latest_odds. Widok z 0001_init.sql działał z prawami właściciela,
-- więc omijał RLS tabeli odds_snapshots dla każdego z kluczem publicznym.
-- Dziś tabela jest pusta i kod widoku nie używa — naprawa bez ryzyka:
-- widok respektuje uprawnienia pytającego. Wykonane na produkcji 13.09.
alter view public.latest_odds set (security_invoker = true);
