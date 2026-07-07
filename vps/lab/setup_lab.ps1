# ============================================================
#  setup_lab.ps1 — Mi Trading Lab API en VPS grande (UNA vez)
#  Uso: powershell -ExecutionPolicy Bypass -File vps\lab\setup_lab.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

Write-Host "==> Mi Trading Lab — setup en VPS" -ForegroundColor Cyan
Write-Host "    Raiz: $root" -ForegroundColor DarkGray

Write-Host "==> Python:" -ForegroundColor Cyan
python --version

Write-Host "==> Entorno virtual (.venv-lab)..." -ForegroundColor Cyan
$venv = Join-Path $root ".venv-lab"
if (-not (Test-Path $venv)) { python -m venv $venv }

$py = Join-Path $venv "Scripts\python.exe"
$pip = Join-Path $venv "Scripts\pip.exe"

& $py -m pip install --upgrade pip
Write-Host "==> Dependencias (requirements.txt)..." -ForegroundColor Cyan
& $pip install -r (Join-Path $root "requirements.txt")

Write-Host "==> Carpeta datos forex..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path (Join-Path $root "data\forex_cache") | Out-Null

Write-Host "==> Instalar CSV (si existe gzip o deploy)..." -ForegroundColor Cyan
& $py (Join-Path $root "scripts\install_forex_data.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "AVISO: falta EURUSD. Copia desde tu Mac:" -ForegroundColor Yellow
    Write-Host "  data\forex_cache\EURUSD_M5_full.csv.gz" -ForegroundColor Yellow
    Write-Host "  Luego: .venv-lab\Scripts\python.exe scripts\install_forex_data.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "OK — setup listo." -ForegroundColor Green
Write-Host "Siguiente: vps\lab\start_lab_api.ps1" -ForegroundColor Yellow
