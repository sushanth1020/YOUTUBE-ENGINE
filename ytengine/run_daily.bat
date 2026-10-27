@echo off
REM Called by Windows Task Scheduler every day. Logs go to logs\task.log
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if not exist logs mkdir logs
echo ===== %date% %time% ===== >> "logs\task.log"
".venv\Scripts\python.exe" run_daily.py >> "logs\task.log" 2>&1
