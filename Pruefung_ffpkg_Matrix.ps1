# =============================================================================
#  Pruefmatrix fuer die .ffpkg-Wege - braucht Administratorrechte
# =============================================================================
#  Warum dieses Skript:
#
#  Genau zwei Dinge im Programm verlangen einen erhoehten Prozess:
#
#    * ein .ffpkg ERZEUGEN   - UFS2Tool ruft newfs/makefs auf
#    * ein .ffpkg ENTPACKEN  - UFS2Tool/Dokan haengt ein Laufwerk ein
#
#  Alles andere laeuft ohne, und wird deshalb an anderer Stelle geprueft.
#  Dieses Skript faehrt die .ffpkg-Faelle der Pruefmatrix ab: einmal jede
#  Integrationsvariante beim Erzeugen, und jeden Rueckweg aus einem .ffpkg.
#
#  So starten:
#    1. Windows-Taste druecken, "PowerShell" tippen
#    2. Rechtsklick -> "Als Administrator ausfuehren"
#    3. Diesen Befehl einfuegen (mit Anfuehrungszeichen):
#
#       & "C:\Users\JBuserc0re\Documents\GitHub PS5 Dump & Image Converter\Pruefung_ffpkg_Matrix.ps1"
#
#  Es veraendert nichts an den Sicherungen auf F: - dort wird nur gelesen.
#  Geschrieben wird ausschliesslich nach E:\ClaudeMatrix_ffpkg und E:\PS5_Temp.
#
#  Dauer: Ein .ffpkg aus 51 GB dauert rund eine Stunde, die Varianten mit
#  Asset-Pack deutlich laenger. Das Skript laeuft ohne Rueckfragen durch.
# =============================================================================

$ErrorActionPreference = "Continue"

$Projekt = "C:\Users\JBuserc0re\Documents\GitHub PS5 Dump & Image Converter"
$Python  = Join-Path $Projekt ".venv\Scripts\python.exe"
$Haupt   = Join-Path $Projekt "PS5ImageConverter_Pro_FINAL_revised.py"
$Ziel    = "E:\ClaudeMatrix_ffpkg"
$Temp    = "E:\PS5_Temp"
$Bericht = Join-Path $Ziel "_ffpkg_matrix_bericht.txt"
$Dump    = "F:\Game Dumps\Prince of Persia The Lost Crown"
$KfgBase = Join-Path $env:TEMP "ps5conv_ffpkg_matrix_kfg"

# --- Rechte pruefen ----------------------------------------------------------
$istAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $istAdmin) {
    Write-Host ""
    Write-Host "  Dieses Fenster hat KEINE Administratorrechte." -ForegroundColor Red
    Write-Host "  Bitte PowerShell schliessen, mit Rechtsklick als" -ForegroundColor Red
    Write-Host "  Administrator neu oeffnen und den Befehl wiederholen." -ForegroundColor Red
    Write-Host ""
    Read-Host "  Mit Eingabetaste beenden"
    exit 1
}

if (-not (Test-Path $Dump)) {
    Write-Host "  Quelle nicht gefunden: $Dump" -ForegroundColor Red
    Read-Host "  Mit Eingabetaste beenden"
    exit 1
}

New-Item -ItemType Directory -Force -Path $Ziel | Out-Null
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
New-Item -ItemType Directory -Force -Path $KfgBase | Out-Null

"Pruefmatrix .ffpkg - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" |
    Out-File $Bericht -Encoding utf8
"Quelle: $Dump" | Out-File $Bericht -Append -Encoding utf8
"" | Out-File $Bericht -Append -Encoding utf8

Write-Host ""
Write-Host "  Administratorrechte: vorhanden" -ForegroundColor Green
Write-Host "  Quelle: $Dump"
Write-Host "  Ziel:   $Ziel"
Write-Host "  Temp:   $Temp"
Write-Host ""

# --- Konfiguration je Variante schreiben -------------------------------------
function New-Konfig {
    param([string]$Name, [bool]$Ampr, [string]$Methode, [bool]$PlayGo, [bool]$Backport)

    $ordner = Join-Path $KfgBase $Name
    New-Item -ItemType Directory -Force -Path $ordner | Out-Null
    $daten = [ordered]@{
        temp_dir                = $Temp
        integrate_ampr          = $Ampr
        integrate_ampr_methode  = $Methode
        integrate_playgo        = $PlayGo
        integrate_backport      = $Backport
        integrate_backport_fw   = 7
        integrate_ampr_version  = "0.4.2.1 test-pack"
        bauform                 = "exfat"
        mkpfs_verify            = "schnell"
        zstd_level              = 6
        language                = "de"
    }
    $daten | ConvertTo-Json | Out-File (Join-Path $ordner "paths.json") -Encoding utf8
    return $ordner
}

# --- Ein Fall ----------------------------------------------------------------
function Invoke-Fall {
    param([string]$Nr, [string]$Was, [string]$Konfig, [string[]]$Argumente)

    $unterordner = Join-Path $Ziel $Nr
    if (Test-Path $unterordner) { Remove-Item $unterordner -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $unterordner | Out-Null

    $fertig = @()
    foreach ($a in $Argumente) {
        if ($a -eq "?") { $fertig += $unterordner } else { $fertig += $a }
    }

    Write-Host ("  {0,-22} {1}" -f $Nr, $Was)
    $env:PS5CONV_KONFIGORDNER = $Konfig
    $uhr = [Diagnostics.Stopwatch]::StartNew()
    $ausgabe = & $Python $Haupt @fertig 2>&1
    $code = $LASTEXITCODE
    $uhr.Stop()
    $sek = [math]::Round($uhr.Elapsed.TotalSeconds, 1)

    $bytes = 0
    $anzahl = 0
    if (Test-Path $unterordner) {
        $m = Get-ChildItem $unterordner -Recurse -File -ErrorAction SilentlyContinue |
             Measure-Object Length -Sum
        if ($m.Sum) { $bytes = $m.Sum }
        if ($m.Count) { $anzahl = $m.Count }
    }
    $gb = [math]::Round($bytes / 1GB, 2)

    if ($code -eq 0 -and $bytes -gt 0) {
        Write-Host ("      OK    {0,8}s {1,9} GB  {2} Datei(en)" -f $sek, $gb, $anzahl) -ForegroundColor Green
    } else {
        Write-Host ("      FEHL  {0,8}s  rc={1}  {2} GB" -f $sek, $code, $gb) -ForegroundColor Yellow
    }

    "== $Nr  ($Was)"        | Out-File $Bericht -Append -Encoding utf8
    "   Rueckgabe : $code"  | Out-File $Bericht -Append -Encoding utf8
    "   Sekunden  : $sek"   | Out-File $Bericht -Append -Encoding utf8
    "   Bytes     : $bytes" | Out-File $Bericht -Append -Encoding utf8
    "   Dateien   : $anzahl" | Out-File $Bericht -Append -Encoding utf8
    "   --- letzte Zeilen ---" | Out-File $Bericht -Append -Encoding utf8
    ($ausgabe | Select-Object -Last 18) | Out-File $Bericht -Append -Encoding utf8
    "" | Out-File $Bericht -Append -Encoding utf8

    return $unterordner
}

function Basis {
    param([int]$Aufgabe, [string]$Quelle, [string]$Format)
    $a = @("--cli", "--task", "$Aufgabe", "--source", $Quelle,
           "--dest", "?", "--temp", $Temp, "--yes")
    if ($Format) { $a += @("--format", $Format) }
    return $a
}

# =============================================================================
Write-Host "  --- Achse 1: Dump-Ordner -> .ffpkg, je Integrationsvariante ---" -ForegroundColor Cyan
Write-Host ""

$varianten = @(
    @{ n = "E1_ohne";          a = $false; m = "normal";    p = $false; b = $false; t = "ohne Integration" },
    @{ n = "E2_nur_backport";  a = $false; m = "normal";    p = $false; b = $true;  t = "nur BACKPORT FW 7" },
    @{ n = "E3_nur_ampr";      a = $true;  m = "normal";    p = $false; b = $false; t = "nur AMPR EMU" },
    @{ n = "E4_nur_assetpack"; a = $true;  m = "assetpack"; p = $false; b = $false; t = "nur AMPR EMU + Asset-Pack" },
    @{ n = "E5_ampr_playgo";   a = $true;  m = "normal";    p = $true;  b = $false; t = "AMPR EMU + PlayGo" },
    @{ n = "E6_ampr_backport"; a = $true;  m = "normal";    p = $false; b = $true;  t = "AMPR EMU + BACKPORT" },
    @{ n = "E7_alles";         a = $true;  m = "assetpack"; p = $true;  b = $true;  t = "alles zusammen" }
)

$ersteFfpkg = ""
foreach ($v in $varianten) {
    $kfg = New-Konfig -Name $v.n -Ampr $v.a -Methode $v.m -PlayGo $v.p -Backport $v.b
    $ordner = Invoke-Fall -Nr $v.n -Was $v.t -Konfig $kfg `
        -Argumente (Basis -Aufgabe 1 -Quelle $Dump -Format "ffpkg")
    if (-not $ersteFfpkg) {
        $treffer = Get-ChildItem $ordner -Filter "*.ffpkg" -File -ErrorAction SilentlyContinue |
                   Select-Object -First 1
        if ($treffer) { $ersteFfpkg = $treffer.FullName }
    }
}

# =============================================================================
Write-Host ""
Write-Host "  --- Achse 2: die Rueckwege aus einem .ffpkg ---" -ForegroundColor Cyan
Write-Host ""

if (-not $ersteFfpkg) {
    Write-Host "  Kein .ffpkg entstanden - die Rueckwege werden uebersprungen." -ForegroundColor Yellow
    "== Rueckwege uebersprungen: kein .ffpkg vorhanden" |
        Out-File $Bericht -Append -Encoding utf8
} else {
    Write-Host "  Quelle fuer die Rueckwege: $ersteFfpkg"
    $kfgOhne = New-Konfig -Name "rueckweg" -Ampr $false -Methode "normal" -PlayGo $false -Backport $false
    Invoke-Fall -Nr "F1_ffpkg_zu_ordner" -Was ".ffpkg -> Dump-Ordner" -Konfig $kfgOhne `
        -Argumente (Basis -Aufgabe 4 -Quelle $ersteFfpkg -Format "folder") | Out-Null
    Invoke-Fall -Nr "F2_ffpkg_zu_ffpfsc" -Was ".ffpkg -> .ffpfsc" -Konfig $kfgOhne `
        -Argumente (Basis -Aufgabe 4 -Quelle $ersteFfpkg -Format "ffpfsc") | Out-Null
    Invoke-Fall -Nr "F3_ffpkg_zu_exfat" -Was ".ffpkg -> .exFAT" -Konfig $kfgOhne `
        -Argumente (Basis -Aufgabe 4 -Quelle $ersteFfpkg -Format "exfat") | Out-Null
    Invoke-Fall -Nr "F4_validator_ffpkg" -Was "Aufgabe 8 auf dem .ffpkg" -Konfig $kfgOhne `
        -Argumente @("--cli", "--task", "8", "--source", $ersteFfpkg, "--temp", $Temp, "--yes")  | Out-Null
}

Remove-Item Env:\PS5CONV_KONFIGORDNER -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host "  Fertig. Bericht:" -ForegroundColor Cyan
Write-Host "  $Bericht" -ForegroundColor White
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "  Mit Eingabetaste beenden"
