@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-demo.ps1"
if errorlevel 1 (
  echo.
  echo Ashr local demo could not be started. Keep this window open and send the error above to Codex.
  pause
)
endlocal
