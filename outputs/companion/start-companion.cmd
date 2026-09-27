@echo off
setlocal
set "RUNTIME=%~dp0..\..\work\p0-runtime\Scripts\pythonw.exe"
if not exist "%RUNTIME%" (
  echo Local runtime missing. See README.md.
  pause
  exit /b 1
)
start "" "%RUNTIME%" -X utf8 "%~dp0launch.py"
