# PowerShell script to install SKTUI on Windows 11
$ErrorActionPreference = "Stop"

$InstallDir = "$HOME\.local\share\sktui\venv"

Write-Host "Checking for Python..." -ForegroundColor Cyan
try {
    & python --version
} catch {
    Write-Error "Python is not found in PATH. Please install Python 3.10+ from python.org or Microsoft Store."
    exit 1
}

Write-Host "Creating virtual environment in $InstallDir..." -ForegroundColor Cyan
python -m venv "$InstallDir"

Write-Host "Installing dependencies and SKTUI (editable mode)..." -ForegroundColor Cyan
& "$InstallDir\Scripts\python.exe" -m pip install --upgrade pip
& "$InstallDir\Scripts\python.exe" -m pip install -e "$PSScriptRoot"

$ScriptsDir = "$InstallDir\Scripts"
Write-Host "`nSKTUI installed successfully!" -ForegroundColor Green
Write-Host "To run SKTUI:" -ForegroundColor Yellow
Write-Host "  $ScriptsDir\sktui.exe --paper   (dry-run)"
Write-Host "  $ScriptsDir\sktui.exe           (live)"
Write-Host "`nTip: Add '$ScriptsDir' to your User PATH environment variable to run 'sktui' directly from any terminal." -ForegroundColor Gray
