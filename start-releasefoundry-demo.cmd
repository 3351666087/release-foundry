@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-demo.ps1"
if errorlevel 1 (
  echo.
  echo ReleaseFoundry local demo failed to start. Keep this window open and send the error above to Agent.
  pause
)
endlocal
