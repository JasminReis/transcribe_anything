@echo off
rem Transcribe Anywhere - Installation fuer Windows 10/11 (ohne Administratorrechte)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\install.ps1"
echo.
pause
