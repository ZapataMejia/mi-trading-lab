# ============================================================
#  start_lab_api.ps1 — Arranca API Mi Trading Lab (puerto 8000)
#  Uso: powershell -ExecutionPolicy Bypass -File vps\lab\start_lab_api.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

$venv = Join-Path $root ".venv-lab"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "ERROR: corre primero vps\lab\setup_lab.ps1" -ForegroundColor Red
    exit 1
}

$env:ALLOWED_ORIGINS = "https://frontend-kappa-sepia-16.vercel.app,http://localhost:3000"
$env:ONLINE_MODE = "0"
$env:ENABLE_CRYPTO_BACKTEST = "0"
$env:MAX_LIQ_SIM_DAYS = "730"
$env:MAX_FONDEO_SIM_DAYS = "730"

Write-Host "==> Mi Trading Lab API en http://0.0.0.0:8000" -ForegroundColor Green
Write-Host "    Health: http://127.0.0.1:8000/api/health" -ForegroundColor DarkGray
Write-Host "    Ctrl+C para parar" -ForegroundColor DarkGray

& $py -m uvicorn webapp.backend.vps_main:app --host 0.0.0.0 --port 8000
