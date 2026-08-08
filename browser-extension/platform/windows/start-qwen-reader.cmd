@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-qwen-reader.ps1"
exit /b %ERRORLEVEL%
