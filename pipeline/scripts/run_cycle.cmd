@echo off
REM FootStats cycle runner - called by Windows Task Scheduler every ~30 min.
REM Recomputes value bets (statshub + Superbet + STS) and writes app data.
REM Run LOCALLY (home IP). Logs to pipeline\logs\cycle.log.

setlocal
set "PIPELINE_DIR=%~dp0.."
set "PYTHON=C:\Users\Jac\AppData\Local\Programs\Python\Python312\python.exe"
set "PYTHONIOENCODING=utf-8"

if not exist "%PIPELINE_DIR%\logs" mkdir "%PIPELINE_DIR%\logs"

cd /d "%PIPELINE_DIR%"
"%PYTHON%" -m footstats.jobs.cycle >> "%PIPELINE_DIR%\logs\cycle.log" 2>&1

endlocal
