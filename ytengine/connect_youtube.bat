@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Installing Python 3.12... after it finishes, double-click this file again.
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  pause
  exit /b
)
py -m pip install --quiet --upgrade google-auth-oauthlib
py connect_youtube.py
if exist youtube_token.json clip < youtube_token.json
pause
