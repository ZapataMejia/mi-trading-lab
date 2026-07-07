# Copia los fixes de ejecucion live (Jul 2026) al repo del VPS.
# Ejecutar DESDE la carpeta polymarket-bot en el VPS:
#   powershell -ExecutionPolicy Bypass -File vps\update_jul2026\APLICAR_EN_VPS.ps1
#
# Si esta carpeta no existe en el VPS, copiala desde el Mac:
#   vps/update_jul2026/  (toda la carpeta)

$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$src = Join-Path $root "vps\update_jul2026"

if (-not (Test-Path $src)) {
    Write-Host "ERROR: no encuentro $src" -ForegroundColor Red
    Write-Host "Copia la carpeta update_jul2026 desde tu Mac al VPS." -ForegroundColor Yellow
    exit 1
}

$files = @(
    @{ From = "src\polymarket\live_clob.py";       To = "src\polymarket\live_clob.py" },
    @{ From = "src\polymarket\paper_trader.py";    To = "src\polymarket\paper_trader.py" },
    @{ From = "run_v4a_live.ps1";                  To = "vps\run_v4a_live.ps1" },
    @{ From = ".env.example";                      To = ".env.example" }
)

foreach ($f in $files) {
    $from = Join-Path $src $f.From
    $to = Join-Path $root $f.To
    if (-not (Test-Path $from)) {
        Write-Host "Falta: $from" -ForegroundColor Red
        exit 1
    }
    Copy-Item -Force $from $to
    Write-Host "OK: $($f.To)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Archivos actualizados. Siguiente:" -ForegroundColor Cyan
Write-Host "  1. notepad .env  ->  POLYMARKET_MAX_SLIPPAGE_CENTS=20" -ForegroundColor White
Write-Host "  2. powershell -File vps\stop_all_bots.ps1" -ForegroundColor White
Write-Host "  3. powershell -File vps\run_v4a_live.ps1" -ForegroundColor White
