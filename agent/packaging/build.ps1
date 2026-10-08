<#
.SYNOPSIS
  Build the WorkPulse agent: tests -> PyInstaller bundle -> (optional) signing -> (optional) installer.

.EXAMPLE
  ./packaging/build.ps1                                  # bundle only
  ./packaging/build.ps1 -Installer                       # bundle + Inno Setup installer
  ./packaging/build.ps1 -Installer -CertThumbprint ABC.. # signed bundle + signed installer
#>
param(
    [switch]$Installer,
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
    & iscc packaging/installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Get-ChildItem dist/WorkPulseAgentSetup-*.exe | ForEach-Object { Sign-File $_.FullName }
}
Write-Host "Done."
