# =============================================================================
# PS5 Dump & Image Converter v1.8.60 - EXE Build-Skript
# =============================================================================
# Einfach per Doppelklick starten - keine manuelle Execution Policy noetig!
# Das Skript startet sich bei Bedarf automatisch mit Bypass-Policy neu.
# =============================================================================

param(
    [switch]$MitOnly
)

# --- Selbst-Neustart mit Bypass-Policy (loest "Ausfuehrung deaktiviert"-Fehler) ---
if ($ExecutionContext.SessionState.LanguageMode -ne "FullLanguage") {
    $restartArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    foreach ($entry in $PSBoundParameters.GetEnumerator()) {
        $name = [string]$entry.Key
        $value = $entry.Value

        if ($value -is [System.Management.Automation.SwitchParameter]) {
            if ($value.IsPresent) {
                $restartArgs += "-$name"
            }
            continue
        }

        if ($null -eq $value) {
            continue
        }

        if ($value -is [SecureString]) {
            Write-Host "WARNUNG: Parameter '-$name' ist SecureString und wird beim Neustart nicht automatisch uebergeben." -ForegroundColor Yellow
            continue
        }

        $restartArgs += "-$name"
        $restartArgs += [string]$value
    }

    Start-Process powershell.exe -ArgumentList $restartArgs -Verb RunAs -Wait
    exit
}

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$EXE_VERSION = "v1.8.60"
$EXE_NAME    = "PS5_Dump_Image_Converter_$EXE_VERSION.exe"

if ($MitOnly) {
    Write-Host "      Hinweis: -MitOnly ist veraltet und hat keine zusaetzliche Wirkung." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  PS5 Dump & Image Converter - EXE Build   " -ForegroundColor Cyan
Write-Host "  Version: $EXE_VERSION                    " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# --- Interpreter waehlen ---
# Bevorzugt der Projekt-Interpreter aus .venv: Damit entstehen EXE und
# Testlaeufe auf derselben Python-Version. Fehlt die Umgebung, wird das
# System-Python verwendet.
$PYTHON = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON)) {
    $PYTHON = "python"
    Write-Host "      Hinweis: .venv nicht gefunden - System-Python wird verwendet." -ForegroundColor Yellow
}

# --- Schritt 1: Python pruefen ---
Write-Host "[1/5] Pruefe Python-Installation..." -ForegroundColor Yellow
Write-Host "      Interpreter: $PYTHON" -ForegroundColor Gray
try {
    $pyVer = & $PYTHON --version 2>&1
    Write-Host "      $pyVer gefunden." -ForegroundColor Green
} catch {
    Write-Host "FEHLER: Python nicht gefunden. Bitte von https://python.org installieren." -ForegroundColor Red
    exit 1
}

# --- Schritt 2: Pakete installieren ---
Write-Host ""
Write-Host "[2/5] Installiere/aktualisiere Abhaengigkeiten..." -ForegroundColor Yellow
Write-Host "      pip aktualisieren..." -ForegroundColor Gray
& $PYTHON -m pip install --upgrade pip --quiet
Write-Host "      PyInstaller installieren/aktualisieren..." -ForegroundColor Gray
& $PYTHON -m pip install pyinstaller --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: PyInstaller konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
$pyiVer = & $PYTHON -m PyInstaller --version 2>&1
Write-Host "      PyInstaller $pyiVer bereit." -ForegroundColor Green
Write-Host "      Pillow installieren/aktualisieren..." -ForegroundColor Gray
& $PYTHON -m pip install pillow --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Pillow konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
Write-Host "      cryptography installieren/aktualisieren..." -ForegroundColor Gray
& $PYTHON -m pip install cryptography --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: cryptography konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
Write-Host "      zstandard installieren/aktualisieren..." -ForegroundColor Gray
& $PYTHON -m pip install zstandard --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: zstandard konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
Write-Host "      zlib-ng installieren/aktualisieren (MkPFS-Abhaengigkeit)..." -ForegroundColor Gray
& $PYTHON -m pip install zlib-ng --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: zlib-ng konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
Write-Host "      paramiko installieren/aktualisieren (SFTP-Unterstuetzung)..." -ForegroundColor Gray
& $PYTHON -m pip install paramiko --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: paramiko konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
Write-Host "      tkinterdnd2 installieren/aktualisieren (Drag & Drop, optional)..." -ForegroundColor Gray
& $PYTHON -m pip install tkinterdnd2 --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNUNG: tkinterdnd2 konnte nicht installiert werden - EXE laeuft ohne Drag & Drop." -ForegroundColor Yellow
}
Write-Host "      psutil installieren/aktualisieren (Live-Systemtelemetrie, optional)..." -ForegroundColor Gray
& $PYTHON -m pip install psutil --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNUNG: psutil konnte nicht installiert werden - EXE zeigt keine CPU/RAM-Telemetrie." -ForegroundColor Yellow
}
Write-Host "      Alle Pakete installiert." -ForegroundColor Green

# --- Schritt 3: Pflicht-Dateien pruefen ---
Write-Host ""
Write-Host "[3/5] Pruefe Pflicht-Dateien..." -ForegroundColor Yellow
$missingFiles = @()
$requiredFiles = @(
    "PS5ImageConverter_Pro_FINAL_revised.py",
    "PS5ImageConverter_Pro.spec",
    "extract_icon.py"
) 
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path $requiredFile)) {
        Write-Host "      FEHLER: $requiredFile fehlt!" -ForegroundColor Red
        $missingFiles += $requiredFile
    } else {
        Write-Host "      OK: $requiredFile" -ForegroundColor Green
    }
}

# MkPFS 0.0.9 muss als entpackter Quellordner vorliegen
$mkpfsSrcOk = Test-Path "MkPFS-0.0.9\mkpfs\__init__.py"
if (-not $mkpfsSrcOk) {
    Write-Host "      FEHLER: MkPFS 0.0.9 fehlt (erwartet: MkPFS-0.0.9\\mkpfs\\__init__.py)" -ForegroundColor Red
    $missingFiles += "MkPFS 0.0.9"
} else {
    if ($mkpfsSrcOk) {
        Write-Host "      OK: MkPFS-0.0.9\\mkpfs\\__init__.py" -ForegroundColor Green
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "FEHLER: Pflicht-Dateien fehlen. Bitte den Quellordner vollständig bereitstellen." -ForegroundColor Red
    exit 1
}

# helloworld-Ordner pruefen (optional aber empfohlen)
if (Test-Path "helloworld") {
    $jsCount = (Get-ChildItem "helloworld" -Filter "*.js").Count
    $elfCount = (Get-ChildItem "helloworld" -Filter "*.elf").Count
    if (($jsCount + $elfCount) -gt 0) {
        Write-Host "      OK: helloworld/ ($jsCount JS, $elfCount ELF Dateien)" -ForegroundColor Green
    } else {
        # Ein leerer Ordner wird von PyInstaller nicht eingebettet - die
        # Schnellauswahl im JS Loader bleibt dann leer.
        Write-Host "      WARNUNG: helloworld/ ist leer - JS Loader hat keine Schnellzugriff-Dateien" -ForegroundColor Yellow
    }
} else {
    Write-Host "      WARNUNG: helloworld/ fehlt - JS Loader hat keine Schnellzugriff-Dateien" -ForegroundColor Yellow
}

# --- Schritt 4: Alt-Artefakte bereinigen + Icon synchronisieren ---
Write-Host ""
Write-Host "[4/5] Bereinige alte Build-Artefakte und synchronisiere App-Icon..." -ForegroundColor Yellow
$buildDir = Join-Path $PSScriptRoot "build"
$distExePath = Join-Path $PSScriptRoot "dist\$EXE_NAME"

if (Test-Path $buildDir) {
    Remove-Item $buildDir -Recurse -Force
    Write-Host "      build/ entfernt." -ForegroundColor Green
} else {
    Write-Host "      build/ bereits sauber." -ForegroundColor DarkGray
}

if (Test-Path $distExePath) {
    Remove-Item $distExePath -Force
    Write-Host "      Alte EXE entfernt: dist\$EXE_NAME" -ForegroundColor Green
} else {
    Write-Host "      Keine alte EXE im dist/-Ordner gefunden." -ForegroundColor DarkGray
}

& $PYTHON extract_icon.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Icon-Extraktion fehlgeschlagen." -ForegroundColor Red
    exit 1
}
Write-Host "      app_icon.ico synchronisiert." -ForegroundColor Green

# --- Schritt 5: EXE erstellen ---
Write-Host ""
Write-Host "[5/5] Erstelle EXE (dauert 2-5 Minuten)..." -ForegroundColor Yellow
Write-Host "      (paramiko und cryptography erhoehen die Groesse etwas)" -ForegroundColor Gray
Write-Host "      (UPX-Komprimierung ist deaktiviert, um False Positives zu reduzieren)" -ForegroundColor Gray
Write-Host ""
& $PYTHON -m PyInstaller PS5ImageConverter_Pro.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "FEHLER: EXE-Erstellung fehlgeschlagen." -ForegroundColor Red
    Write-Host "Tipp: Fehlermeldung oben lesen. Haeufige Ursachen:" -ForegroundColor Yellow
    Write-Host "  - Fehlende Pakete: pip install paramiko bcrypt" -ForegroundColor Yellow
    exit 1
}

# --- Ergebnis ---
Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  BUILD ERFOLGREICH!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
$exePath = Join-Path $PSScriptRoot "dist\$EXE_NAME"
if (Test-Path $exePath) {
    $sizeMB = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "  EXE:     dist\$EXE_NAME" -ForegroundColor White
    Write-Host "  Groesse: $sizeMB MB" -ForegroundColor White
} else {
    Write-Host "  EXE:     dist\$EXE_NAME" -ForegroundColor White
}
# --- Auslieferungsbuendel zusammenstellen ---
#
# Bis v1.8.49 wurde dieser Ordner von Hand gefuellt. Nach einem Bau blieb er
# deshalb mit der alten Fassung liegen, ohne dass es jemand merkte - dieselbe
# Art Fehler, die schon das Handbuch-PDF zwei Versionen alt werden liess.
# Jetzt entsteht er bei jedem erfolgreichen Bau neu.
#
# Die Linux-Programmdatei kommt mit, WENN sie vorhanden ist. Sie entsteht in
# WSL ueber ./Build_Linux.sh und liegt danach in dist/; fehlt sie, ist das
# kein Fehler - das Buendel enthaelt dann nur die Windows-Fassung.
#
# Dasselbe gilt fuer die macOS-Fassung. Sie entsteht auf einem Mac ueber
# ./Build_macOS.sh --dmg; das .app-Buendel selbst ist ein Ordner und taugt
# nicht zum Weitergeben ueber Windows, weil dabei Rechte und erweiterte
# Attribute verlorengehen - und mit ihnen die Signatur. Deshalb wird nur das
# fertige Abbild uebernommen. Zwei Architekturen, weil ein Buendel immer nur
# zu einer passt.
$buendelName = "PS5_Dump_Image_Converter_$EXE_VERSION"
$buendel     = Join-Path $PSScriptRoot "dist\$buendelName"
$linuxName   = "PS5_Dump_Image_Converter_${EXE_VERSION}_linux_x86_64"
$macosNamen  = @(
    "PS5_Dump_Image_Converter_${EXE_VERSION}_macos_arm64.dmg",
    "PS5_Dump_Image_Converter_${EXE_VERSION}_macos_x86_64.dmg"
)

if (Test-Path $exePath) {
    Write-Host ""
    Write-Host "  Buendel: dist\$buendelName" -ForegroundColor White
    if (Test-Path $buendel) { Remove-Item $buendel -Recurse -Force }
    New-Item -ItemType Directory -Path $buendel -Force | Out-Null

    $mitnehmen = @($EXE_NAME, $linuxName) + $macosNamen |
                 ForEach-Object { Join-Path $PSScriptRoot "dist\$_" }
    $mitnehmen += @("README.md", "CHANGELOG.md", "BENUTZERHANDBUCH.pdf") |
                  ForEach-Object { Join-Path $PSScriptRoot $_ }

    foreach ($quelle in $mitnehmen) {
        $name = Split-Path $quelle -Leaf
        if (Test-Path $quelle) {
            Copy-Item $quelle $buendel -Force
            $mb = [math]::Round((Get-Item $quelle).Length / 1MB, 2)
            Write-Host ("           {0,-46} {1,8} MB" -f $name, $mb) -ForegroundColor Gray
        } elseif ($name -eq $linuxName) {
            Write-Host "           (keine Linux-Fassung in dist/ - uebersprungen)" -ForegroundColor DarkGray
        } elseif ($macosNamen -contains $name) {
            # Nur einmal melden: Von den beiden Architekturen kann hoechstens
            # eine dort liegen, die andere fehlt zwangslaeufig.
            if ($name -eq $macosNamen[0]) {
                Write-Host "           (keine macOS-Fassung in dist/ - uebersprungen)" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "           FEHLT: $name" -ForegroundColor Yellow
        }
    }
    $gesamt = (Get-ChildItem $buendel -File | Measure-Object -Property Length -Sum).Sum
    Write-Host ("           zusammen {0:N1} MB" -f ($gesamt / 1MB)) -ForegroundColor Gray
}

Write-Host ""
Write-Host "  Hinweis: Die EXE benoetigt Administratorrechte (UAC-Prompt beim Start)." -ForegroundColor Gray
Write-Host "  Hinweis: Antivirenprogramme koennen die EXE faelschlicherweise blockieren." -ForegroundColor Gray
Write-Host "           In diesem Fall: Ausnahme in Antivirus hinzufuegen." -ForegroundColor Gray

Write-Host ""
