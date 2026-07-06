param(
    [string]$Dump = "DumpA",
    [string]$Ffpkg = "",
    [string]$OutputDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
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
        "-File", ('"' + $scriptPath + '"'),
        "-Dump", ('"' + $Dump + '"')
    )

    if ($Ffpkg) {
        $argList += @("-Ffpkg", ('"' + $Ffpkg + '"'))
    }
    if ($OutputDir) {
        $argList += @("-OutputDir", ('"' + $OutputDir + '"'))
    }

    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList ($argList -join " ") | Out-Null
    Write-Host "UAC-Dialog gestartet. Der Admin-Runner oeffnet in einem neuen Fenster."
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

    & $pythonExe @pyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Runner fehlgeschlagen (ExitCode $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
