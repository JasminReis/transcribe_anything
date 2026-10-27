@echo off
rem Prueft, ob die Live-Transkription auf diesem Geraet mithaelt.
rem Benutzung: eine Audiodatei mit deutscher Sprache (mind. 5 Minuten) auf diese Datei ziehen.
cd /d "%~dp0..\.."
if "%~1"=="" (
  echo Bitte eine Audiodatei mit Sprache ^(mind. 5 Minuten, z. B. .mp3/.m4a/.wav^) auf diese Datei ziehen.
  pause
  exit /b
)
echo Simuliert ein 10-Minuten-Meeting in Echtzeit. Dauert ca. 11 Minuten.
".venv\Scripts\python.exe" tools\simulate_live.py "%~1" --minutes 10 --speed 1
pause
