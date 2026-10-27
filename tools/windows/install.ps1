# Transcribe Anywhere – Installation für Windows 10/11
# Pro Benutzer, ohne Administratorrechte (nur die Microsoft-C++-Laufzeit fragt ggf. nach).
# Wird von install-windows.bat gestartet. Kann gefahrlos mehrfach ausgeführt werden (Update).

$ErrorActionPreference = "Stop"
$App = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)     # tools\windows -> Programmordner
Set-Location $App

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "FEHLER: $text" -ForegroundColor Red; exit 1 }

try {
    Step "Python 3.11 suchen"
    $py = $null
    try {
        $found = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) { $py = "$found".Trim() }
    } catch { }
    $userPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (-not $py -and (Test-Path $userPython)) { $py = $userPython }
    if (-not $py) {
        Step "Python 3.11 installieren (einmalig, ca. 1-2 Minuten)"
        winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
        if (-not (Test-Path $userPython)) {
            Fail "Python konnte nicht automatisch installiert werden. Bitte Python 3.11 von https://www.python.org/downloads/ installieren und install-windows.bat erneut starten."
        }
        $py = $userPython
    }
    Write-Host "Python: $py"

    Step "Microsoft Visual C++ Laufzeit prüfen"
    $vc = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
    if ($vc -and $vc.Installed -eq 1) {
        Write-Host "vorhanden"
    } else {
        Write-Host "wird installiert (Windows fragt eventuell nach Erlaubnis) ..."
        winget install -e --id Microsoft.VCRedist.2015+.x64 --silent --accept-package-agreements --accept-source-agreements
    }

    Step "Programm installieren (einige Minuten, lädt ca. 400 MB)"
    if (-not (Test-Path ".venv\Scripts\python.exe")) { & $py -m venv .venv }
    $venvPy = Join-Path $App ".venv\Scripts\python.exe"
    & $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
    $target = "."
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        Write-Host "NVIDIA-Grafikkarte gefunden - GPU-Unterstützung wird mitinstalliert."
        $target = ".[cuda]"
    }
    & $venvPy -m pip install $target --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "Installation fehlgeschlagen (siehe Meldungen oben)." }

    Step "Spracherkennung herunterladen (ca. 670 MB, einmalig)"
    & (Join-Path $App ".venv\Scripts\transcribe-anywhere-cli.exe") setup
    if ($LASTEXITCODE -ne 0) { Fail "Modell konnte nicht geladen werden. Internetverbindung prüfen und erneut starten." }

    Step "Verknüpfungen anlegen (Desktop und Startmenü)"
    $exe = Join-Path $App ".venv\Scripts\transcribe-anywhere.exe"
    $shell = New-Object -ComObject WScript.Shell
    $places = @([Environment]::GetFolderPath("Desktop"),
                (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))
    foreach ($dir in $places) {
        $link = $shell.CreateShortcut((Join-Path $dir "Transcribe Anywhere.lnk"))
        $link.TargetPath = $exe
        $link.WorkingDirectory = $App
        $link.Description = "Meetings lokal transkribieren"
        $link.Save()
    }

    Step "Fertig!"
    Write-Host "Starte 'Transcribe Anywhere' über das Symbol auf dem Desktop." -ForegroundColor Green
} catch {
    Fail $_.Exception.Message
}
