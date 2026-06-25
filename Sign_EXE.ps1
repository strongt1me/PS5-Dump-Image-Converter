# =============================================================================
#  Sign_EXE.ps1  –  Automatischer Code-Signing-Vorgang für PS5_Dump_Image_Converter.exe
#  Unterstützt: Standard Code Signing & EV Code Signing (Hardware-Token / PFX-Datei)
# =============================================================================

param(
    [string]$ExePath     = "dist\PS5_Dump_Image_Converter.exe",
    [string]$PfxPath     = "",          # Pfad zur PFX-Datei (leer = Zertifikat aus Windows-Zertifikatspeicher)
    [string]$PfxPassword = "",          # Passwort der PFX-Datei (leer lassen bei EV-Token)
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$EV                         # EV-Zertifikat (Hardware-Token) – kein PFX nötig
)

# Farben für Ausgabe
function Write-OK    { param($msg) Write-Host "  [OK]  $msg" -ForegroundColor Green }
function Write-INFO  { param($msg) Write-Host "  [..] $msg"  -ForegroundColor Cyan }
function Write-WARN  { param($msg) Write-Host "  [!!] $msg"  -ForegroundColor Yellow }
function Write-FAIL  { param($msg) Write-Host "  [XX] $msg"  -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "   PS5 Dump & Image Converter – Code Signing" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host ""

# -----------------------------------------------------------------------------
# 1. EXE-Datei prüfen
# -----------------------------------------------------------------------------
Write-INFO "Prüfe EXE-Datei: $ExePath"
if (-not (Test-Path $ExePath)) {
    Write-FAIL "EXE nicht gefunden: $ExePath"
    Write-WARN "Bitte zuerst Build_EXE.ps1 ausführen um die EXE zu erstellen."
    exit 1
}
Write-OK "EXE gefunden: $ExePath"

# -----------------------------------------------------------------------------
# 2. signtool.exe suchen (Windows SDK)
# -----------------------------------------------------------------------------
Write-INFO "Suche signtool.exe ..."

$signtool = $null

# Bekannte Pfade für Windows SDK (verschiedene Versionen)
$sdkPaths = @(
    "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe",
    "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
    "C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe",
    "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
    "C:\Program Files\Windows Kits\10\bin\x64\signtool.exe"
)

foreach ($path in $sdkPaths) {
    if (Test-Path $path) {
        $signtool = $path
        break
    }
}

# Dynamische Suche falls nicht gefunden
if (-not $signtool) {
    $found = Get-ChildItem "C:\Program Files (x86)\Windows Kits" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -like "*x64*" } |
             Sort-Object LastWriteTime -Descending |
             Select-Object -First 1
    if ($found) { $signtool = $found.FullName }
}

if (-not $signtool) {
    Write-FAIL "signtool.exe nicht gefunden!"
    Write-Host ""
    Write-Host "  Bitte Windows SDK installieren:" -ForegroundColor Yellow
    Write-Host "  https://developer.microsoft.com/de-de/windows/downloads/windows-sdk/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Oder Visual Studio mit 'Windows 10/11 SDK' Komponente installieren." -ForegroundColor Yellow
    exit 1
}
Write-OK "signtool.exe gefunden: $signtool"

# -----------------------------------------------------------------------------
# 3. Zertifikat prüfen
# -----------------------------------------------------------------------------
Write-INFO "Prüfe Zertifikat ..."

if ($EV) {
    # EV-Zertifikat: liegt auf Hardware-Token (USB), wird automatisch erkannt
    Write-INFO "EV-Modus: Zertifikat wird vom Hardware-Token gelesen."
    Write-WARN "Bitte stellen Sie sicher, dass der USB-Token angeschlossen ist."
    $certSource = "EV-Token"
} elseif ($PfxPath -ne "") {
    # Standard Code Signing: PFX-Datei
    if (-not (Test-Path $PfxPath)) {
        Write-FAIL "PFX-Datei nicht gefunden: $PfxPath"
        exit 1
    }
    Write-OK "PFX-Datei gefunden: $PfxPath"
    $certSource = "PFX"
} else {
    # Zertifikat aus Windows-Zertifikatspeicher (automatisch)
    Write-INFO "Kein PFX angegeben – suche Zertifikat im Windows-Zertifikatspeicher ..."
    $cert = Get-ChildItem Cert:\CurrentUser\My |
            Where-Object { $_.EnhancedKeyUsageList -match "Code Signing" } |
            Sort-Object NotAfter -Descending |
            Select-Object -First 1

    if (-not $cert) {
        Write-FAIL "Kein Code-Signing-Zertifikat im Windows-Zertifikatspeicher gefunden!"
        Write-Host ""
        Write-Host "  Optionen:" -ForegroundColor Yellow
        Write-Host "  1. PFX-Datei angeben:  .\Sign_EXE.ps1 -PfxPath 'C:\Pfad\zertifikat.pfx' -PfxPassword 'passwort'" -ForegroundColor Cyan
        Write-Host "  2. EV-Token verwenden: .\Sign_EXE.ps1 -EV" -ForegroundColor Cyan
        Write-Host "  3. Zertifikat in Windows importieren und erneut versuchen." -ForegroundColor Cyan
        exit 1
    }

    Write-OK "Zertifikat gefunden: $($cert.Subject)"
    Write-OK "Gültig bis: $($cert.NotAfter.ToString('dd.MM.yyyy'))"

    # Ablaufwarnung
    $daysLeft = ($cert.NotAfter - (Get-Date)).Days
    if ($daysLeft -lt 30) {
        Write-WARN "Zertifikat läuft in $daysLeft Tagen ab – bitte erneuern!"
    }
    $certSource = "Store"
}

# -----------------------------------------------------------------------------
# 4. Timestamp-Server prüfen
# -----------------------------------------------------------------------------
Write-INFO "Prüfe Timestamp-Server: $TimestampUrl"
try {
    $response = Invoke-WebRequest -Uri $TimestampUrl -Method Head -TimeoutSec 5 -ErrorAction Stop
    Write-OK "Timestamp-Server erreichbar."
} catch {
    Write-WARN "Timestamp-Server nicht erreichbar – Signierung ohne Timestamp ist möglich, aber nicht empfohlen."
    Write-WARN "Die EXE verliert ihre Gültigkeit wenn das Zertifikat abläuft."
    $response = $null
}

# -----------------------------------------------------------------------------
# 5. Signiervorgang
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "  Starte Signiervorgang ..." -ForegroundColor Cyan
Write-Host ""

# signtool-Argumente zusammenbauen
$signArgs = @(
    "sign",
    "/fd", "sha256",          # Datei-Hash-Algorithmus: SHA-256
    "/td", "sha256",          # Timestamp-Hash-Algorithmus: SHA-256
    "/tr", $TimestampUrl      # Timestamp-Server (RFC 3161)
)

switch ($certSource) {
    "PFX" {
        $signArgs += "/f", $PfxPath
        if ($PfxPassword -ne "") {
            $signArgs += "/p", $PfxPassword
        }
    }
    "EV-Token" {
        # EV: signtool findet das Zertifikat automatisch über den Token-Treiber
        $signArgs += "/a"
    }
    "Store" {
        # Automatisch bestes Zertifikat aus dem Store wählen
        $signArgs += "/a"
    }
}

# Verbose-Ausgabe aktivieren
$signArgs += "/v"

# EXE-Pfad ans Ende
$signArgs += $ExePath

# Signiervorgang ausführen
Write-INFO "Führe aus: signtool $($signArgs -join ' ')"
Write-Host ""

& $signtool @signArgs
$exitCode = $LASTEXITCODE

Write-Host ""

# -----------------------------------------------------------------------------
# 6. Ergebnis prüfen
# -----------------------------------------------------------------------------
if ($exitCode -eq 0) {
    Write-OK "Signierung erfolgreich abgeschlossen!"
    Write-Host ""

    # Signatur verifizieren
    Write-INFO "Verifiziere Signatur ..."
    & $signtool verify /pa /v $ExePath
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Signatur verifiziert – EXE ist gültig signiert."
    } else {
        Write-WARN "Verifikation fehlgeschlagen – bitte manuell prüfen."
    }

    # Dateiinfo ausgeben
    Write-Host ""
    $fileInfo = Get-Item $ExePath
    Write-OK "Datei:    $($fileInfo.FullName)"
    Write-OK "Größe:    $([math]::Round($fileInfo.Length / 1MB, 2)) MB"
    Write-OK "Geändert: $($fileInfo.LastWriteTime.ToString('dd.MM.yyyy HH:mm:ss'))"

} else {
    Write-FAIL "Signierung fehlgeschlagen! (Exit-Code: $exitCode)"
    Write-Host ""
    Write-Host "  Häufige Ursachen:" -ForegroundColor Yellow
    Write-Host "  - Falsches PFX-Passwort" -ForegroundColor White
    Write-Host "  - USB-Token nicht angeschlossen (EV)" -ForegroundColor White
    Write-Host "  - Token-Treiber nicht installiert (EV)" -ForegroundColor White
    Write-Host "  - Zertifikat abgelaufen" -ForegroundColor White
    Write-Host "  - Timestamp-Server nicht erreichbar" -ForegroundColor White
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "   Fertig!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host ""
