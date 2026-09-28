@echo off
start "" /wait "%~dp0TFT-DataJ.exe" --diagnose
explorer "%LOCALAPPDATA%\TFT-DataJ"
