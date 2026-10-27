# YT Money Engine - one-time Windows setup
# Run:  right-click this file > "Run with PowerShell"
#   or: powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "`n=== YT Money Engine setup ===`n" -ForegroundColor Cyan

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# 1) Python 3.12 + ffmpeg (via winget, built into Windows 10/11)
if (-not (Have "py")) {
  Write-Host "Installing Python 3.12..." ; winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
}
if (-not (Have "ffmpeg")) {
  Write-Host "Installing ffmpeg..." ; winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
if (-not (Have "ffmpeg")) { Write-Host "ffmpeg was just installed. Close this window, open a new PowerShell and run setup again." -ForegroundColor Yellow; exit 1 }

# 2) Virtual environment + packages
if (-not (Test-Path ".venv")) { py -3.12 -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

# 3) API keys
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "`nNotepad will open. Paste your API keys, save, close Notepad." -ForegroundColor Yellow
  Start-Process notepad ".env" -Wait
}

# 4) Connect YouTube (opens your browser once)
if (-not (Test-Path "client_secret.json")) {
  Write-Host "`nclient_secret.json is missing. Follow README > Step 3 (Google Cloud OAuth), save the file in this folder." -ForegroundColor Yellow
  Read-Host "Press Enter when client_secret.json is in place"
}
& $py run_daily.py --auth

# 5) Health check
& $py run_daily.py --check

# 6) Daily scheduled task (+ a catch-up run when you log on, in case the PC was off at the scheduled time)
$time = Read-Host "`nWhat time should your PC build the video each day? (24h HH:MM, Enter = 10:00)"
if (-not $time) { $time = "10:00" }
$action   = New-ScheduledTaskAction -Execute "$PSScriptRoot\run_daily.bat" -WorkingDirectory $PSScriptRoot
$triggers = @( (New-ScheduledTaskTrigger -Daily -At $time), (New-ScheduledTaskTrigger -AtLogOn) )
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Hours 5) -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "YT Money Engine" -Action $action -Trigger $triggers -Settings $settings `
  -Description "Researches, renders and schedules the daily YouTube video" -Force | Out-Null
Write-Host "`nDone. Task 'YT Money Engine' runs daily at $time (and at log-on to catch up)." -ForegroundColor Green
Write-Host "Test it now:  .\.venv\Scripts\python.exe run_daily.py --no-upload" -ForegroundColor Green
