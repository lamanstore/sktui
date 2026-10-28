# PowerShell script to install SKTUI on Windows 10/11
param (
    [switch]$Dev,
    [switch]$Uninstall,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host "SKTUI Workstation Windows Installer" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\install.ps1 [OPTIONS]"
    Write-Host "Options:"
    Write-Host "  -Dev         Install development and test dependencies (pytest, etc.)"
    Write-Host "  -Uninstall   Remove SKTUI virtual environment"
    Write-Host "  -Help        Display this help message"
    exit 0
}

$InstallDir = "$HOME\.local\share\sktui\venv"
$ScriptsDir = "$InstallDir\Scripts"

if ($Uninstall) {
    Write-Host "Removing SKTUI Workstation environment..." -ForegroundColor Yellow
    if (Test-Path "$InstallDir") {
        Remove-Item -Recurse -Force "$InstallDir"
        Write-Host "✓ Removed $InstallDir" -ForegroundColor Green
    }
    Write-Host "SKTUI uninstalled successfully." -ForegroundColor Green
    exit 0
}

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "⚡ SKTUI — Professional Terminal Trading Workstation Installer (Windows)" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Checking for Python 3.10+..." -ForegroundColor Cyan
try {
    & python --version
} catch {
    Write-Error "Python was not found in PATH. Please install Python 3.10+ from python.org or Microsoft Store."
    exit 1
}

Write-Host "Creating virtual environment in $InstallDir..." -ForegroundColor Cyan
python -m venv "$InstallDir"

Write-Host "Upgrading pip, setuptools, wheel..." -ForegroundColor Cyan
& "$ScriptsDir\python.exe" -m pip install --upgrade pip setuptools wheel

if ($Dev) {
    Write-Host "Installing SKTUI with [dev] test dependencies in editable mode..." -ForegroundColor Cyan
    & "$ScriptsDir\python.exe" -m pip install -e "$PSScriptRoot[dev]"
} else {
    Write-Host "Installing SKTUI in editable mode..." -ForegroundColor Cyan
    & "$ScriptsDir\python.exe" -m pip install -e "$PSScriptRoot"
}

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "✓ SKTUI Workstation installed successfully!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "To launch SKTUI:" -ForegroundColor Yellow
Write-Host "  $ScriptsDir\sktui.exe --paper   (Simulated Paper Trading Mode)"
Write-Host "  $ScriptsDir\sktui.exe           (Live Trading Mode)"
Write-Host "  $ScriptsDir\sktui.exe --profile live"
Write-Host ""
Write-Host "Tip: Add '$ScriptsDir' to your User PATH environment variable to run 'sktui' from any terminal." -ForegroundColor Gray
