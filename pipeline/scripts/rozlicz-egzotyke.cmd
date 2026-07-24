@echo off
chcp 65001 >nul
REM ============================================================
REM  AKTUALIZACJA DANYCH SOFASCORE (z domowego IP) — dwa zadania:
REM   1) rozliczenia egzotyki: staty zakonczonych meczow, ktorych
REM      chmura nie zna (domyka wiszace kupony),
REM   2) srednie sezonowe graczy z drabinek (sekcja "sezony").
REM  Klikaj co 1-2 dni (gdy komp jest wlaczony). Dziala z domowego
REM  IP, bo Sofascore blokuje chmure. Procesy w NISKIM priorytecie
REM  (/LOW) — nie obciazaja komputera podczas pracy w tle.
REM ============================================================
setlocal
set "PIPELINE_DIR=%~dp0.."
set "PYTHON=C:\Users\Jac\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONIOENCODING=utf-8"

cd /d "%PIPELINE_DIR%"
echo(
echo === Aktualizacja danych Sofascore (domowe IP) — %date% %time% ===
echo(

echo [1/2] Sofascore: staty zakonczonych meczow + srednie sezonowe graczy...
start "" /LOW /WAIT /B "%PYTHON%" -m footstats.jobs.sofa_worker

echo(
echo [2/2] Rozliczam kupony od razu lokalnie (chmura i tak powtorzy)...
start "" /LOW /WAIT /B "%PYTHON%" -m footstats.jobs.rozlicz_only

echo(
echo === Gotowe: kupony domkniete, srednie sezonowe dociagniete. ===
endlocal
pause
