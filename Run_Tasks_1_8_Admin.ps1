param(
    [string]$Dump = "DumpA",
    [string]$Ffpkg = "",
    [string]$OutputDir = "",
    [string]$Task = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function ConvertTo-QuotedArgument([string]$Value) {
    return '"' + ($Value -replace '"', '\"') + '"'
}

$scriptPath = $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptPath
$runnerPy = Join-Path $repoRoot "run_tasks_1_8_e2e.py"
$preferredPy = Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"

if (Test-Path $preferredPy) {
    $pythonExe = $preferredPy
}
else {
    $pythonExe = "python"
}

if (-not (Test-Path $runnerPy)) {
    throw "Runner nicht gefunden: $runnerPy"
}

if (-not (Test-IsAdmin)) {
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (ConvertTo-QuotedArgument $scriptPath),
        "-Dump", (ConvertTo-QuotedArgument $Dump)
    )

    if ($Ffpkg) {
        $argList += @("-Ffpkg", (ConvertTo-QuotedArgument $Ffpkg))
    }
    if ($OutputDir) {
        $argList += @("-OutputDir", (ConvertTo-QuotedArgument $OutputDir))
    }
    if ($Task) {
        $argList += @("-Task", (ConvertTo-QuotedArgument $Task))
    }

    $proc = Start-Process -FilePath "powershell.exe" -Verb RunAs -WorkingDirectory $repoRoot -ArgumentList ($argList -join " ") -Wait -PassThru
    if ($null -eq $proc) {
        throw "Erhoehter Runner konnte nicht gestartet werden."
    }
    if ($proc.ExitCode -ne 0) {
        throw "Erhoehter Runner fehlgeschlagen (ExitCode $($proc.ExitCode))."
    }
    Write-Host "Erhoehter Runner abgeschlossen."
    exit 0
}

Push-Location $repoRoot
try {
    $pyArgs = @("run_tasks_1_8_e2e.py", "--dump", $Dump)
    if ($Ffpkg) {
        $pyArgs += @("--ffpkg", $Ffpkg)
    }
    if ($OutputDir) {
        $pyArgs += @("--output-dir", $OutputDir)
    }
    if ($Task) {
        $pyArgs += @("--task", $Task)
    }

    & $pythonExe @pyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Runner fehlgeschlagen (ExitCode $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
