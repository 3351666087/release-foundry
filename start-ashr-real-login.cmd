@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-auth.ps1"
if errorlevel 1 (
  echo.
  echo Ashr real local login failed to start. Keep this window open and send the error above to Codex.
  pause
)
endlocal
