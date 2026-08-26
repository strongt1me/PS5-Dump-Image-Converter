# =============================================================================
#  Prüfung der Aufgaben, die Administratorrechte brauchen
# =============================================================================
#  Warum dieses Skript:
#
#  Zwei Dinge im Programm verlangen einen erhöhten Prozess, und nur diese:
#
#    * ein .ffpkg ERZEUGEN   - UFS2Tool ruft newfs/makefs auf
#    * ein .ffpkg ENTPACKEN  - UFS2Tool/Dokan hängt ein Laufwerk ein
#
#  Alles andere läuft ohne. Dieses Skript fährt genau die Fälle ab, die ohne
#  Rechte nicht prüfbar sind, und schreibt das Ergebnis in eine Datei.
#
#  So starten:
#    1. Windows-Taste drücken, "PowerShell" tippen
#    2. Rechtsklick -> "Als Administrator ausführen"
#    3. Diesen Befehl einfügen (mit Anführungszeichen):
#
#       & "C:\Users\JBuserc0re\Documents\GitHub PS5 Dump & Image Converter\Pruefung_mit_Adminrechten.ps1"
#
#  Es verändert nichts an Ihren Sicherungen auf F: - dort wird nur gelesen.
#  Geschrieben wird ausschließlich nach E:\Test\V100_admin und E:\PS5_Temp.
# =============================================================================

$ErrorActionPreference = "Continue"

$Projekt = "C:\Users\JBuserc0re\Documents\GitHub PS5 Dump & Image Converter"
$Python  = Join-Path $Projekt ".venv\Scripts\python.exe"
$Haupt   = Join-Path $Projekt "PS5ImageConverter_Pro_FINAL_revised.py"
$Ziel    = "E:\Test\V100b_admin"
$Temp    = "E:\PS5_Temp"
$Bericht = Join-Path $Ziel "_admin_bericht.txt"
$Dumps   = "F:\Game Dumps"

# --- Rechte prüfen -----------------------------------------------------------
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

New-Item -ItemType Directory -Force -Path $Ziel | Out-Null
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
"Pruefung mit Adminrechten - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" |
    Out-File $Bericht -Encoding utf8

Write-Host ""
Write-Host "  Administratorrechte: vorhanden" -ForegroundColor Green
Write-Host "  Ziel:  $Ziel"
Write-Host "  Temp:  $Temp"
Write-Host ""

# --- Ein Fall ----------------------------------------------------------------
function Invoke-Fall {
    param([string]$Nr, [string]$Was, [string[]]$Argumente)

    $unterordner = Join-Path $Ziel $Nr
    if (Test-Path $unterordner) { Remove-Item $unterordner -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $unterordner | Out-Null

    # Platzhalter ? durch den echten Zielordner ersetzen
    $fertig = @()
    foreach ($a in $Argumente) {
        if ($a -eq "?") { $fertig += $unterordner } else { $fertig += $a }
    }

    Write-Host ("  {0,-16} {1}" -f $Nr, $Was) -NoNewline
    $uhr = [Diagnostics.Stopwatch]::StartNew()
    $ausgabe = & $Python $Haupt @fertig 2>&1
    $code = $LASTEXITCODE
    $uhr.Stop()
    $sek = [math]::Round($uhr.Elapsed.TotalSeconds, 1)

    $bytes = 0
    if (Test-Path $unterordner) {
        $m = Get-ChildItem $unterordner -Recurse -File -ErrorAction SilentlyContinue |
             Measure-Object Length -Sum
        if ($m.Sum) { $bytes = $m.Sum }
    }
    $mb = [math]::Round($bytes / 1MB, 1)

    if ($code -eq 0) {
        Write-Host ("   OK    {0,7}s {1,9} MB" -f $sek, $mb) -ForegroundColor Green
    } else {
        Write-Host ("   FEHL  {0,7}s  rc={1}" -f $sek, $code) -ForegroundColor Yellow
    }

    "== $Nr  ($Was)"                     | Out-File $Bericht -Append -Encoding utf8
    "   Rueckgabe : $code"               | Out-File $Bericht -Append -Encoding utf8
    "   Sekunden  : $sek"                | Out-File $Bericht -Append -Encoding utf8
    "   Bytes     : $bytes"              | Out-File $Bericht -Append -Encoding utf8
    "   Dateien   : " + ((Get-ChildItem $unterordner -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Name }) -join ", ") | Out-File $Bericht -Append -Encoding utf8
    "   --- letzte Zeilen ---"           | Out-File $Bericht -Append -Encoding utf8
    ($ausgabe | Select-Object -Last 12)  | Out-File $Bericht -Append -Encoding utf8
    ""                                   | Out-File $Bericht -Append -Encoding utf8
}

function Basis {
    param([int]$Aufgabe, [string[]]$Quellen, [string]$Format)
    $a = @("--cli", "--task", "$Aufgabe", "--source") + $Quellen +
         @("--dest", "?", "--temp", $Temp, "--yes", "--quiet")
    if ($Format) { $a += @("--format", $Format) }
    return $a
}

# =============================================================================
Write-Host "  --- 1) Dump-Ordner -> .ffpkg (UFS2Tool newfs/makefs) ---"
$spiele = @(
    @{ k = "A"; p = "$Dumps\Personality and Psychology Premium" },
    @{ k = "B"; p = "$Dumps\Asterix & Obelix Heroes" },
    @{ k = "C"; p = "$Dumps\Instant Sports Plus" },
    @{ k = "D"; p = "$Dumps\Wer wird Millionaer" }
)
foreach ($s in $spiele) {
    if (-not (Test-Path $s.p)) { Write-Host "  fehlt: $($s.p)"; continue }
    Invoke-Fall "AD1-$($s.k)-ffpkg" "Aufgabe 1: $(Split-Path $s.p -Leaf) -> ffpkg" `
        (Basis 1 @($s.p) "ffpkg")
}

Write-Host ""
Write-Host "  --- 2) .ffpkg -> Ordner / .exFAT (Dokan-Mount) ---"
$ffpkg = "$Dumps\PPSA16709 Asterix Obelix Heroes (01.000.000).ffpkg"
if (Test-Path $ffpkg) {
    foreach ($f in @("folder", "exfat")) {
        Invoke-Fall "AD4-$f" "Aufgabe 4: .ffpkg -> $f" (Basis 4 @($ffpkg) $f)
    }
} else {
    Write-Host "  fehlt: $ffpkg"
}

Write-Host ""
Write-Host "  --- 3) Sammel- und AIO-Konvertierung nach .ffpkg ---"
$q1 = "$Ziel\AD1-A-ffpkg"
$erste = Get-ChildItem "$Ziel\AD1-A-ffpkg" -Filter *.ffpkg -ErrorAction SilentlyContinue |
         Select-Object -First 1
if ($erste) {
    Invoke-Fall "AD6-ffpkg" "Aufgabe 6: .ffpkg -> Ordner" `
        (Basis 6 @($erste.FullName) "folder")
}
Invoke-Fall "AD5-ffpkg" "Aufgabe 5: zwei Dumps -> ffpkg" `
    (Basis 5 @("$Dumps\Instant Sports Plus", "$Dumps\Wer wird Millionaer") "ffpkg")

Write-Host ""
Write-Host "  --- 4) Aufgabe 3 mit echtem Einhaengen ---"
$exfat = Get-ChildItem "E:\Test\V100b\A1-A-exfat" -Filter *.exfat -ErrorAction SilentlyContinue |
         Select-Object -First 1
if ($exfat) {
    Invoke-Fall "AD3-folder" "Aufgabe 3: .exFAT -> Ordner (eleviert)" `
        (Basis 3 @($exfat.FullName) "folder")
} else {
    Write-Host "  keine .exfat aus der vorigen Runde gefunden - uebersprungen"
}

Write-Host ""
Write-Host "  Fertig. Bericht: $Bericht" -ForegroundColor Cyan
Write-Host ""
Read-Host "  Mit Eingabetaste schliessen"
