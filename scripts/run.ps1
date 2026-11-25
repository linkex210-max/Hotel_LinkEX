Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    Hotel LinkEX - Starting Django Backend Server" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $rootDir ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
    python (Join-Path $rootDir "backend\manage.py") runserver 127.0.0.1:8000
} else {
    Write-Host "Virtual environment not found in .venv" -ForegroundColor Red
}
