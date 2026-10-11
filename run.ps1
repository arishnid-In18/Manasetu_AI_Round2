<#
 MANASETU AI - one-command start (Windows PowerShell 5.1+ or PowerShell 7; also runs on Linux/macOS pwsh).
   .\run.ps1                          # victims & complainants profile (SIH26094), http://127.0.0.1:8000
   .\run.ps1 -Profile correctional    # inmate adaptation
   .\run.ps1 -Reset                   # wipe and re-seed the 50 synthetic people
   .\run.ps1 -Test                    # Python tests (+ Node voice-matcher tests if Node is installed)
   .\run.ps1 -NoBrowser -Port 8400    # do not open a browser / pick another port
 If Windows blocks the script:  powershell -ExecutionPolicy Bypass -File .\run.ps1
#>
param([ValidateSet("atrocity_victims","correctional")][string]$Profile = "atrocity_victims",
      [int]$Port = 8000, [switch]$Reset, [switch]$Test, [switch]$NoBrowser, [switch]$CheckOnly)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
function Run-Native {            # run a native command and stop on a non-zero exit code
    param([string]$Exe, [string[]]$CmdArgs)
    & $Exe @CmdArgs
    if ($LASTEXITCODE -ne 0) { Fail "'$Exe $($CmdArgs -join ' ')' failed with exit code $LASTEXITCODE" }
}

$onWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or ($IsWindows -eq $true)
$venvPy = if ($onWindows) { Join-Path ".venv" "Scripts\python.exe" } else { Join-Path ".venv" "bin/python" }

# --- find a system Python 3.10+ (python, py launcher, python3)
$sysPy = $null; $sysArgs = @()
foreach ($cand in @(@("python"), @("py", "-3"), @("python3"))) {
    if (Get-Command $cand[0] -ErrorAction SilentlyContinue) {
        $a = @(); if ($cand.Count -gt 1) { $a = $cand[1..($cand.Count - 1)] }
        $ver = & $cand[0] @a -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match "^3\.(\d+)$" -and [int]$Matches[1] -ge 10) { $sysPy = $cand[0]; $sysArgs = $a; break }
    }
}
if (-not (Test-Path -LiteralPath $venvPy)) {
    if (-not $sysPy) { Fail "Python 3.10 or newer was not found. Install it from python.org and tick 'Add python.exe to PATH'." }
    Write-Host "Creating virtual environment (.venv) ..." -ForegroundColor Cyan
    Run-Native $sysPy ($sysArgs + @("-m", "venv", ".venv"))
}
Write-Host "Installing requirements ..." -ForegroundColor Cyan
Run-Native $venvPy @("-m", "pip", "install", "-q", "-r", "requirements.txt")

$env:MANASETU_PROFILE = $Profile
$env:PYTHONUTF8 = "1"            # Tamil/Hindi text must never depend on the Windows code page
if ($CheckOnly) { Write-Host "Environment OK. profile=$Profile python=$venvPy windows=$onWindows" -ForegroundColor Green; exit 0 }

if ($Test) {
    Run-Native $venvPy @("-m", "pytest", "tests", "-q")
    if (Get-Command node -ErrorAction SilentlyContinue) { Run-Native "node" @("--test", "tests/voice_matcher.test.mjs") }
    else { Write-Host "Node.js not found: skipped the voice-matcher tests." -ForegroundColor Yellow }
    exit 0
}
if ($Reset) { Run-Native $venvPy @("-m", "app.seed", "--reset") }
Write-Host "MANASETU AI [$Profile] -> http://127.0.0.1:$Port   (Ctrl+C to stop)" -ForegroundColor Green
if (-not $NoBrowser -and $onWindows) { Start-Process "http://127.0.0.1:$Port" }
Run-Native $venvPy @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
