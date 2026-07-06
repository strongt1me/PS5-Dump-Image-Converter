# =============================================================================
#  Sign_EXE.ps1  – Automatischer Code-Signing-Vorgang für PS5_Dump_Image_Converter.exe
#  Unterstützt: Standard Code Signing & EV Code Signing (Hardware-Token / PFX-Datei)
# =============================================================================

param(
    [string]$ExePath     = "",
    [string]$PfxPath     = "",
    [SecureString]$PfxPassword = $null,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$EV
)

function Write-OK    { param($msg) Write-Host "  [OK]  $msg" -ForegroundColor Green }
function Write-INFO  { param($msg) Write-Host "  [..] $msg"  -ForegroundColor Cyan }
function Write-WARN  { param($msg) Write-Host "  [!!] $msg"  -ForegroundColor Yellow }
function Write-FAIL  { param($msg) Write-Host "  [XX] $msg"  -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "   PS5 Dump & Image Converter – Code Signing" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host ""

# Finde EXE automatisch falls nicht angegeben
if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $candidate = Get-ChildItem "dist" -Filter "PS5_Dump_Image_Converter_*.exe" -File -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime -Descending |
                 Select-Object -First 1
    if ($candidate) {
        $ExePath = $candidate.FullName
    } elseif (Test-Path "dist\PS5_Dump_Image_Converter.exe") {
        $ExePath = "dist\PS5_Dump_Image_Converter.exe"
    }
}

# Prüfe EXE-Datei
Write-INFO "Prüfe EXE-Datei: $ExePath"
if (-not (Test-Path $ExePath)) {
    Write-FAIL "EXE nicht gefunden: $ExePath"
    Write-WARN "Bitte zuerst Build_EXE.ps1 ausführen um die EXE zu erstellen."
    exit 1
}
Write-OK "EXE gefunden: $ExePath"

# Suche signtool.exe
Write-INFO "Suche signtool.exe ..."
$signtool = $null

# Pfade mit einfachen Anführungszeichen (verhindert PowerShell-Parser-Fehler bei (x86))
$sdkPaths = @(
    'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe',
    'C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe',
    'C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe',
    'C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe',
    'C:\Program Files\Windows Kits\10\bin\x64\signtool.exe'
)

foreach ($path in $sdkPaths) {
    if (Test-Path $path) {
        $signtool = $path
        break
    }
}

# Dynamische Suche falls nicht gefunden
if (-not $signtool) {
    $found = Get-ChildItem 'C:\Program Files (x86)\Windows Kits' -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
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
    exit 1
}
Write-OK "signtool.exe gefunden: $signtool"

# Prüfe Zertifikat
Write-INFO "Prüfe Zertifikat ..."

if ($EV) {
    Write-INFO "EV-Modus: Zertifikat wird vom Hardware-Token gelesen."
    Write-WARN "Bitte stellen Sie sicher dass der USB-Token angeschlossen ist."
    $certMode = "EV-Token"
} elseif ($PfxPath -ne "") {
    if (-not (Test-Path $PfxPath)) {
        Write-FAIL "PFX-Datei nicht gefunden: $PfxPath"
        exit 1
    }
    Write-OK "PFX-Datei gefunden: $PfxPath"
    $certMode = "PFX"
} else {
    Write-INFO "Kein PFX angegeben – suche Zertifikat im Windows-Zertifikatspeicher ..."
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue | Select-Object -First 1
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
    $certMode = "Windows Store"
}

# Starte Signing
Write-Host ""
Write-INFO "Starte Code-Signing..."
Write-INFO "Methode: $certMode"
Write-INFO "Timestamp-Server: $TimestampUrl"

$signcmd = @(
    "`"$signtool`"",
    "sign",
    "/fd SHA256",
    "/tr `"$TimestampUrl`"",
    "/td SHA256"
)

if ($EV) {
    # EV-Token: Zertifikat wird automatisch erkannt
} elseif ($PfxPath -ne "") {
    $signcmd += "/f"
    $signcmd += "`"$PfxPath`""
    if ($PfxPassword) {
        $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($PfxPassword)
        $pwdPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
        $signcmd += "/p"
        $signcmd += "`"$pwdPlain`""
    }
}

$signcmd += "`"$ExePath`""

$signCmdStr = $signcmd -join " "
Write-HOST "  Kommando: $signCmdStr" -ForegroundColor DarkGray

Invoke-Expression $signCmdStr

if ($LASTEXITCODE -eq 0) {
    Write-OK "Code-Signing erfolgreich!"
    Write-Host ""
    Write-Host "  EXE signiert: $ExePath" -ForegroundColor Green
    Write-Host "  Hash-Algorithmus: SHA256" -ForegroundColor Green
    Write-Host "  Zertifikat-Modus: $certMode" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-FAIL "Code-Signing fehlgeschlagen (Exit-Code: $LASTEXITCODE)"
    exit 1
}
