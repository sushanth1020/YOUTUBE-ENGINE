@echo off
REM One-time: lets the engine use your Claude Pro/Max subscription instead of API credits.
cd /d "%~dp0"
where npm >nul 2>nul
if errorlevel 1 (
  echo Installing Node.js... after it finishes, close this window and double-click this file again.
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  pause
  exit /b
)
call npm install -g @anthropic-ai/claude-code
echo.
echo A browser will open - log in with the Claude account that has your Pro/Max plan.
echo Then COPY the long token it prints (starts with sk-ant-oat...) into GitHub secret CLAUDE_CODE_OAUTH_TOKEN.
echo.
call claude setup-token
pause
