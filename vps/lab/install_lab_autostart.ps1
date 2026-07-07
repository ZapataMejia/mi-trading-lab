# ============================================================
#  install_lab_autostart.ps1 — Tarea al iniciar sesion (API lab)
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$script = Join-Path $PSScriptRoot "start_lab_api.ps1"
$taskName = "MiTradingLabAPI"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$script`""

$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "OK — tarea '$taskName' registrada (arranca al iniciar sesion en el VPS)." -ForegroundColor Green
Write-Host "Prueba manual: powershell -ExecutionPolicy Bypass -File vps\lab\start_lab_api.ps1" -ForegroundColor Yellow
