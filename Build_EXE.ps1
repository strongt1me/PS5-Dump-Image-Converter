# =============================================================================
# PS5 Dump & Image Converter v1.7.76 - EXE Build-Skript
# =============================================================================
# Einfach per Doppelklick starten - keine manuelle Execution Policy noetig!
# Das Skript startet sich bei Bedarf automatisch mit Bypass-Policy neu.
# =============================================================================

param(
    [switch]$SkipSigning,
    [switch]$MitOnly,
    [string]$SignPfxPath = "",
    [SecureString]$SignPfxPassword = $null,
    [string]$SignPfxPasswordPlain = "",
    [switch]$SignEV,
    [string]$SignTimestampUrl = "http://timestamp.digicert.com",
    [switch]$RequireSignature
)

# --- Selbst-Neustart mit Bypass-Policy (loest "Ausfuehrung deaktiviert"-Fehler) ---
if ($ExecutionContext.SessionState.LanguageMode -ne "FullLanguage" -or
    (Get-ExecutionPolicy -Scope Process) -eq "Restricted" -or
    (Get-ExecutionPolicy -Scope Process) -eq "AllSigned") {
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

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$EXE_VERSION = "v1.7.76"
$EXE_NAME    = "PS5_Dump_Image_Converter_$EXE_VERSION.exe"

# MIT-only ist der Standardmodus: keine EV/PFX/Store-Signierung.
# -MitOnly kann optional explizit gesetzt werden, ist aber nicht erforderlich.
$MitOnlyActive = $true
if ($MitOnly -or $MitOnlyActive) {
    if ($SignEV -or $RequireSignature -or -not [string]::IsNullOrWhiteSpace($SignPfxPath) -or $SignPfxPassword -or -not [string]::IsNullOrWhiteSpace($SignPfxPasswordPlain)) {
        Write-Host "" 
        Write-Host "FEHLER: MIT-only Modus ist aktiv. EV/PFX/Zertifikat-Parameter sind deaktiviert." -ForegroundColor Red
        Write-Host "        Bitte Signatur-Parameter entfernen und nur MIT-Lizenz-Flow verwenden." -ForegroundColor Yellow
        Read-Host "Druecke Enter zum Beenden"
        exit 1
    }
    $SkipSigning = $true
}

function Register-MitLicense {
    param(
        [string]$Version
    )

    $regPath = "HKCU:\Software\PS5DumpImageConverter\License"
    $year = (Get-Date).Year
    $mitLicenseText = @"
MIT License

Copyright (c) $year PS5 Dump & Image Converter Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"@

    if (-not (Test-Path $regPath)) {
        New-Item -Path $regPath -Force | Out-Null
    }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($mitLicenseText)
        $hashBytes = $sha.ComputeHash($bytes)
        $hashHex = [BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }

    New-ItemProperty -Path $regPath -Name "LicenseName" -Value "MIT" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name "SPDX" -Value "MIT" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name "LicenseText" -Value $mitLicenseText -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name "LicenseHashSHA256" -Value $hashHex -PropertyType String -Force | Out-Null
    $registeredAt = (Get-Date).ToUniversalTime().ToString("o")
    New-ItemProperty -Path $regPath -Name "RegisteredAtUTC" -Value $registeredAt -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name "RegisteredBy" -Value $env:USERNAME -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $regPath -Name "BuildVersion" -Value $Version -PropertyType String -Force | Out-Null

    return [PSCustomObject]@{
        RegistryPath     = $regPath
        LicenseName      = "MIT"
        SPDX             = "MIT"
        LicenseHashSHA256 = $hashHex
        RegisteredAtUTC  = $registeredAt
        BuildVersion     = $Version
    }
}

function Get-CodeSigningCertificates {
    $stores = @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")
    $found = @()
    foreach ($store in $stores) {
        try {
            $found += Get-ChildItem $store -ErrorAction Stop |
                Where-Object EnhancedKeyUsageList -Match "Code Signing"
        } catch {
            # Zugriff auf Store kann je nach Kontext eingeschraenkt sein.
        }
    }
    return $found
}

function Test-SigningPrerequisites {
    param(
        [switch]$SkipSigning,
        [switch]$RequireSignature,
        [switch]$SignEV,
        [string]$SignPfxPath
    )

    if (-not $RequireSignature) {
        return
    }

    if ($SkipSigning) {
        throw "-RequireSignature kann nicht mit -SkipSigning kombiniert werden."
    }

    if ($SignEV) {
        Write-Host "      Hinweis: EV-Modus aktiv. USB-Token und Middleware muessen verfuegbar sein." -ForegroundColor DarkGray
        return
    }

    if (-not [string]::IsNullOrWhiteSpace($SignPfxPath)) {
        if (-not (Test-Path $SignPfxPath)) {
            throw "PFX-Datei fuer Pflichtsignierung nicht gefunden: $SignPfxPath"
        }
        return
    }

    $certs = Get-CodeSigningCertificates
    if (-not $certs -or $certs.Count -eq 0) {
        throw "Pflichtsignierung aktiv, aber kein Code-Signing-Zertifikat im Cert:\CurrentUser\My oder Cert:\LocalMachine\My gefunden."
    }
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
    Read-Host "Druecke Enter zum Beenden"
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
    Read-Host "Druecke Enter zum Beenden"
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

# --- Signatur-Vorpruefung (nur bei Pflichtsignierung) ---
Write-Host ""
Write-Host "[2a/5] Pruefe Signatur-Voraussetzungen..." -ForegroundColor Yellow
if ($SkipSigning) {
    Write-Host "      MIT-only Modus aktiv: Signaturpruefung uebersprungen." -ForegroundColor Green
} else {
    try {
        Test-SigningPrerequisites -SkipSigning:$SkipSigning -RequireSignature:$RequireSignature -SignEV:$SignEV -SignPfxPath $SignPfxPath
        Write-Host "      Signatur-Vorpruefung: OK" -ForegroundColor Green
    } catch {
        Write-Host "      FEHLER: $($_.Exception.Message)" -ForegroundColor Red
        Read-Host "Druecke Enter zum Beenden"
        exit 1
    }
}

# --- MIT-Lizenz in Windows registrieren (vor EXE-Erstellung) ---
Write-Host ""
Write-Host "[2b/5] Registriere MIT-Lizenz in Windows (HKCU)..." -ForegroundColor Yellow
try {
    $licenseInfo = Register-MitLicense -Version $EXE_VERSION
    Write-Host "      MIT-Lizenz erfolgreich registriert." -ForegroundColor Green
    Write-Host "      Registry: $($licenseInfo.RegistryPath)" -ForegroundColor DarkGray
    Write-Host "      SPDX: $($licenseInfo.SPDX)" -ForegroundColor DarkGray
    Write-Host "      Hash (SHA256): $($licenseInfo.LicenseHashSHA256)" -ForegroundColor DarkGray
    Write-Host "      Zeit (UTC): $($licenseInfo.RegisteredAtUTC)" -ForegroundColor DarkGray

    # Gegenprüfung: Werte aus Registry zurücklesen und mit Soll vergleichen
    $regCheck = Get-ItemProperty -Path $licenseInfo.RegistryPath -ErrorAction Stop
    if ($regCheck.SPDX -ne $licenseInfo.SPDX) {
        throw "SPDX-Mismatch (ist '$($regCheck.SPDX)', soll '$($licenseInfo.SPDX)')"
    }
    if ($regCheck.LicenseHashSHA256 -ne $licenseInfo.LicenseHashSHA256) {
        throw "LicenseHashSHA256-Mismatch (Registry ungleich berechnetem Hash)"
    }
    if ($regCheck.BuildVersion -ne $licenseInfo.BuildVersion) {
        throw "BuildVersion-Mismatch (ist '$($regCheck.BuildVersion)', soll '$($licenseInfo.BuildVersion)')"
    }
    if ([string]::IsNullOrWhiteSpace([string]$regCheck.RegisteredAtUTC)) {
        throw "RegisteredAtUTC fehlt in der Registry"
    }

    Write-Host "      Registry-Verifikation: OK" -ForegroundColor Green
    Write-Host "      Verifiziertes BuildVersion: $($regCheck.BuildVersion)" -ForegroundColor DarkGray
} catch {
    Write-Host "      FEHLER: MIT-Lizenz konnte nicht registriert werden: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Druecke Enter zum Beenden"
    exit 1
}

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
    Read-Host "Druecke Enter zum Beenden"
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
    Read-Host "Druecke Enter zum Beenden"
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
    Read-Host "Druecke Enter zum Beenden"
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

# --- Automatische Signierung ---
if (-not (Test-Path $exePath)) {
    Write-Host "" 
    Write-Host "  Signierung uebersprungen: EXE wurde nicht gefunden." -ForegroundColor Yellow
} elseif ($SkipSigning) {
    Write-Host "" 
    Write-Host "  Signierung uebersprungen (Schalter -SkipSigning aktiv)." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[SIGN] Starte automatische EXE-Signierung..." -ForegroundColor Yellow
    $signScript = Join-Path $PSScriptRoot "Sign_EXE.ps1"
    if (-not (Test-Path $signScript)) {
        Write-Host "  FEHLER: Sign_EXE.ps1 wurde nicht gefunden." -ForegroundColor Red
        if ($RequireSignature) {
            Read-Host "Druecke Enter zum Beenden"
            exit 1
        }
        Write-Host "  Build bleibt unsigniert (fortgesetzt, da -RequireSignature nicht gesetzt)." -ForegroundColor Yellow
    } else {
        $signArgs = @{
            ExePath = $exePath
            TimestampUrl = $SignTimestampUrl
        }

        if ($SignEV) {
            $signArgs["EV"] = $true
        } elseif (-not [string]::IsNullOrWhiteSpace($SignPfxPath)) {
            $signArgs["PfxPath"] = $SignPfxPath
            $effectivePfxPassword = $SignPfxPassword
            if ($null -eq $effectivePfxPassword -and -not [string]::IsNullOrWhiteSpace($SignPfxPasswordPlain)) {
                $effectivePfxPassword = ConvertTo-SecureString -String $SignPfxPasswordPlain -AsPlainText -Force
            }
            if ($null -ne $effectivePfxPassword) {
                $signArgs["PfxPassword"] = $effectivePfxPassword
            }
        }

        & $signScript @signArgs
        $signExit = $LASTEXITCODE

        if ($signExit -ne 0) {
            Write-Host "  Signierung fehlgeschlagen (Exit-Code: $signExit)." -ForegroundColor Red
            if ($RequireSignature) {
                Read-Host "Druecke Enter zum Beenden"
                exit 1
            }
            Write-Host "  Build bleibt unsigniert (fortgesetzt, da -RequireSignature nicht gesetzt)." -ForegroundColor Yellow
        }
    }
}

if (Test-Path $exePath) {
    try {
        $sig = Get-AuthenticodeSignature -FilePath $exePath
        if ($sig.Status -eq "Valid") {
            Write-Host "  Signaturstatus: GUELTIG" -ForegroundColor Green
        } elseif ($sig.Status -eq "NotSigned") {
            Write-Host "  Signaturstatus: NICHT SIGNIERT" -ForegroundColor Yellow
        } else {
            Write-Host "  Signaturstatus: $($sig.Status)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Signaturstatus konnte nicht ermittelt werden." -ForegroundColor Yellow
    }
}

Write-Host ""
Read-Host "Druecke Enter zum Beenden"
