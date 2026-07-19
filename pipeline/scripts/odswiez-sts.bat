@echo off
REM Dwuklik = odswiezenie kursow value STS (on-demand, z domowego IP PL).
REM Skanuje STS vs Superbet + doklada p_model, wynik leci PROSTO do Supabase
REM (klucz sts_value) -> apka na Vercelu pokazuje swieze STS-y. Zero pliku lokalnego,
REM zero procesu w tle: dziala tylko te ~1 min, potem sie zamyka.
cd /d "%~dp0.."
echo == Odswiezam kursy value STS (STS vs Superbet + model) i wysylam do apki... ==
python -m footstats.jobs.sts_value --dni 3 --max-mecze 40 --rownolegle 10 --do-supabase --bez-pliku
echo.
echo Gotowe. Swieze value bety STS sa w apce (zakladka Value Bety).
pause
