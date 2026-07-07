param(
    [string]$Dump = ".\Diverses\_dummy_inputs\DummyDump",
    [string]$Ffpkg = ".\PPSA16709 Asterix Obelix Heroes (01.000.000).ffpkg",
    [string]$OutputDir = ".\_e2e_output_a7_ffpkg_admin_live_20260707"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptPath
$adminRunner = Join-Path $repoRoot "Run_Tasks_1_8_Admin.ps1"

if (-not (Test-Path $adminRunner)) {
    throw "Admin-Runner nicht gefunden: $adminRunner"
}

Push-Location $repoRoot
try {
    & $adminRunner -Task "A7" -Dump $Dump -Ffpkg $Ffpkg -OutputDir $OutputDir
    if ($LASTEXITCODE -ne 0) {
        throw "A7 .ffpkg Admin-Runner fehlgeschlagen (ExitCode $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
