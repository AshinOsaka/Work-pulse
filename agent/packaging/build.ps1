<#
.SYNOPSIS
  Build the WorkPulse agent: tests -> PyInstaller bundle -> (optional) signing -> (optional) installer.

.EXAMPLE
  ./packaging/build.ps1                                  # bundle only
  ./packaging/build.ps1 -Installer                       # bundle + Inno Setup installer
  ./packaging/build.ps1 -Installer -CertThumbprint ABC.. # signed bundle + signed installer
  ./packaging/build.ps1 -Installer -Production           # installer with the company server address baked in
#>
param(
    [switch]$Installer,
    [switch]$Production,
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "==> Tests"
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Host "==> Icon"
& $python packaging/make_icon.py

Write-Host "==> PyInstaller bundle"
if ($Production) { $env:WORKPULSE_PRODUCTION_BUILD = "1" } else { Remove-Item Env:WORKPULSE_PRODUCTION_BUILD -ErrorAction SilentlyContinue }
& $python -m PyInstaller packaging/workpulse-agent.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

function Sign-File([string]$path) {
    if (-not $CertThumbprint) { return }
    & signtool sign /sha1 $CertThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 /d "WorkPulse Agent" $path
    if ($LASTEXITCODE -ne 0) { throw "Signing failed for $path" }
}
Sign-File "dist/WorkPulseAgent/WorkPulseAgent.exe"

Write-Host "==> Smoke test"
& "dist/WorkPulseAgent/WorkPulseAgent.exe" --version
if ($LASTEXITCODE -ne 0) { throw "Smoke test failed" }

if ($Installer) {
    Write-Host "==> Installer (Inno Setup)"
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $iscc = @("$env:ProgramFiles\Inno Setup 7\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
                  "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $iscc) { throw "Inno Setup (ISCC.exe) not found. Install it from https://jrsoftware.org/isdl.php" }
    & $iscc packaging/installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Get-ChildItem dist/WorkPulseAgentSetup-*.exe | ForEach-Object { Sign-File $_.FullName }
}
Write-Host "Done."
