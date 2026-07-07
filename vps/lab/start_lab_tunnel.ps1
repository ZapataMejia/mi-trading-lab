# Arranca API + tunel Cloudflare (quick tunnel). Deja esta ventana abierta.
# Uso: cd C:\Users\Administrador\mi-trading-lab
#      powershell -ExecutionPolicy Bypass -File vps\lab\start_lab_tunnel.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) {
    $cf = "C:\Program Files\cloudflared\cloudflared.exe"
}
if (-not (Test-Path $cf)) {
    Write-Host "ERROR: instala cloudflared (winget install Cloudflare.cloudflared)" -ForegroundColor Red
    exit 1
}

# Liberar puerto 8000 si quedo colgado (ignorar Idle/0)
$p = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -gt 0 }
if ($p) {
    $p | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Write-Host "Puerto 8000 liberado." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}

Write-Host "==> Abriendo API en ventana nueva..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "vps\lab\start_lab_api.ps1")
)

Write-Host "Esperando API (10 s)..." -ForegroundColor DarkGray
Start-Sleep -Seconds 10
try {
    $h = Invoke-RestMethod "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 5
    if ($h.status -ne "ok") { throw "health bad" }
    Write-Host "API OK en :8000" -ForegroundColor Green
} catch {
    Write-Host "AVISO: API aun no responde - revisa la otra ventana." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Tunel Cloudflare (NO CIERRES esta ventana)" -ForegroundColor Cyan
Write-Host "    Copia la URL https://....trycloudflare.com y pasala a Santiago para Vercel." -ForegroundColor Yellow
Write-Host ""
& $cf tunnel --url http://127.0.0.1:8000
