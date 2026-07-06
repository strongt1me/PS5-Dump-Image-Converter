# =============================================================================
# PS5 Dump & Image Converter v1.7.77 - EXE Build-Skript
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

$EXE_VERSION = "v1.7.77"
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

# --- Schritt 1: Python pruefen ---
Write-Host "[1/5] Pruefe Python-Installation..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "      $pyVer gefunden." -ForegroundColor Green
} catch {
    Write-Host "FEHLER: Python nicht gefunden. Bitte von https://python.org installieren." -ForegroundColor Red
    exit 1
}

# --- Schritt 2: Pakete installieren ---
Write-Host ""
Write-Host "[2/5] Installiere/aktualisiere Abhaengigkeiten..." -ForegroundColor Yellow
Write-Host "      pip aktualisieren..." -ForegroundColor Gray
python -m pip install --upgrade pip --quiet
Write-Host "      PyInstaller installieren/aktualisieren..." -ForegroundColor Gray
pip install pyinstaller --upgrade --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: PyInstaller konnte nicht installiert werden." -ForegroundColor Red
    exit 1
}
$pyiVer = pyinstaller --version 2>&1
Write-Host "      PyInstaller $pyiVer bereit." -ForegroundColor Green
Write-Host "      Pillow installieren/aktualisieren..." -ForegroundColor Gray
pip install pillow --upgrade --quiet
Write-Host "      cryptography installieren/aktualisieren..." -ForegroundColor Gray
pip install cryptography --upgrade --quiet
Write-Host "      zstandard installieren/aktualisieren..." -ForegroundColor Gray
pip install zstandard --upgrade --quiet
Write-Host "      zlib-ng installieren/aktualisieren (MkPFS-Abhaengigkeit)..." -ForegroundColor Gray
pip install zlib-ng --upgrade --quiet
Write-Host "      paramiko installieren/aktualisieren (SFTP-Unterstuetzung)..." -ForegroundColor Gray
pip install paramiko --upgrade --quiet
Write-Host "      Alle Pakete installiert." -ForegroundColor Green

# --- Schritt 3: Pflicht-Dateien pruefen ---
Write-Host ""
Write-Host "[3/5] Pruefe Pflicht-Dateien..." -ForegroundColor Yellow
$missingFiles = @()
$requiredFiles = @(
    "PS5ImageConverter_Pro_FINAL_revised.py",
    "ps5_ufs2tool_data.py",
    "PS5ImageConverter_Pro.spec",
    "app_icon.ico",
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

# MkPFS 0.0.9 muss entweder als ZIP oder als entpackter Quellordner vorliegen
$mkpfsZipOk = Test-Path "MkPFS-0.0.9.zip"
$mkpfsSrcOk = Test-Path "MkPFS-0.0.9\mkpfs\__init__.py"
if (-not ($mkpfsZipOk -or $mkpfsSrcOk)) {
    Write-Host "      FEHLER: MkPFS 0.0.9 fehlt (erwartet: MkPFS-0.0.9.zip ODER MkPFS-0.0.9\\mkpfs\\__init__.py)" -ForegroundColor Red
    $missingFiles += "MkPFS 0.0.9"
} else {
    if ($mkpfsZipOk) {
        Write-Host "      OK: MkPFS-0.0.9.zip" -ForegroundColor Green
    }
    if ($mkpfsSrcOk) {
        Write-Host "      OK: MkPFS-0.0.9\\mkpfs\\__init__.py" -ForegroundColor Green
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "FEHLER: Pflicht-Dateien fehlen. Bitte alle Dateien aus dem ZIP entpacken." -ForegroundColor Red
    exit 1
}

# helloworld-Ordner pruefen (optional aber empfohlen)
if (Test-Path "helloworld") {
    $jsCount = (Get-ChildItem "helloworld" -Filter "*.js").Count
    $elfCount = (Get-ChildItem "helloworld" -Filter "*.elf").Count
    Write-Host "      OK: helloworld/ ($jsCount JS, $elfCount ELF Dateien)" -ForegroundColor Green
} else {
    Write-Host "      WARNUNG: helloworld/ fehlt - JS Loader hat keine Schnellzugriff-Dateien" -ForegroundColor Yellow
}

# --- Schritt 4: Icon extrahieren ---
Write-Host ""
Write-Host "[4/5] Extrahiere App-Icon..." -ForegroundColor Yellow
python extract_icon.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Icon-Extraktion fehlgeschlagen." -ForegroundColor Red
    exit 1
}
Write-Host "      app_icon.ico bereit." -ForegroundColor Green

# --- Schritt 5: EXE erstellen ---
Write-Host ""
Write-Host "[5/5] Erstelle EXE (dauert 2-5 Minuten)..." -ForegroundColor Yellow
Write-Host "      (paramiko und cryptography erhoehen die Groesse etwas)" -ForegroundColor Gray
Write-Host ""
pyinstaller PS5ImageConverter_Pro.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "FEHLER: EXE-Erstellung fehlgeschlagen." -ForegroundColor Red
    Write-Host "Tipp: Fehlermeldung oben lesen. Haeufige Ursachen:" -ForegroundColor Yellow
    Write-Host "  - Fehlende Pakete: pip install paramiko bcrypt" -ForegroundColor Yellow
    Write-Host "  - UPX nicht gefunden: Kein Problem, EXE wird trotzdem erstellt" -ForegroundColor Yellow
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
Write-Host ""
Write-Host "  Hinweis: Die EXE benoetigt Administratorrechte (UAC-Prompt beim Start)." -ForegroundColor Gray
Write-Host "  Hinweis: Antivirenprogramme koennen die EXE faelschlicherweise blockieren." -ForegroundColor Gray
Write-Host "           In diesem Fall: Ausnahme in Antivirus hinzufuegen." -ForegroundColor Gray

Write-Host ""
