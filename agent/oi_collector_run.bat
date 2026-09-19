@echo off
REM Lanzador del colector de Open Interest (TRACK A). Lo usa la tarea programada
REM "VergeOICollector" — ver register_oi_collector_task.ps1 / OPEN_INTEREST_COLLECTOR.md.
REM Reinicios de PC: la tarea lo re-arranca sola; el backfill de 30d (idempotente) rellena
REM cualquier hueco < 30 días, así que 2-3 reinicios por semana no cuestan historia.

cd /d "%~dp0"
if not exist logs mkdir logs

REM rotación simple: si el log pasa 20 MB, se archiva
for %%A in (logs\oi_collector.log) do if exist logs\oi_collector.log if %%~zA GTR 20000000 move /y logs\oi_collector.log logs\oi_collector.log.1 >nul 2>&1

echo === arranque %date% %time% === >> logs\oi_collector.log
"C:\Users\Nicolas\AppData\Local\Programs\Python\Python311\pythonw.exe" -u open_interest_collector.py >> logs\oi_collector.log 2>&1
