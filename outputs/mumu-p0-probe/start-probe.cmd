@echo off
setlocal
set "PROBE_PYTHON=%~dp0..\..\work\p0-runtime\Scripts\python.exe"
if not exist "%PROBE_PYTHON%" (
  echo Local test runtime is missing. See README.md.
  pause
  exit /b 1
)
"%PROBE_PYTHON%" -X utf8 "%~dp0probe.py" %*
if errorlevel 1 pause
