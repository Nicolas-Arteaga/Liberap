<#
Registra la tarea programada "VergeOICollector" que mantiene vivo el colector de
Open Interest (TRACK A): arranca al iniciar sesion, se reinicia sola si el
proceso muere o la PC se reinicia, una sola instancia.

Uso (PowerShell ELEVADO -- "Ejecutar como administrador"):
    powershell -ExecutionPolicy Bypass -File agent\register_oi_collector_task.ps1

Nota 2026-09-06: en este entorno Register-ScheduledTask exige elevacion
(HRESULT 0x80070005 sin admin). El backfill de arranque del colector es
idempotente y cubre huecos < 30 dias, asi que un reinicio ocasional no pierde
historia mientras algo lo re-arranque dentro de esos 30 dias.

Para quitarla:
    Unregister-ScheduledTask -TaskName VergeOICollector -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$bat = Join-Path $PSScriptRoot "oi_collector_run.bat"
if (-not (Test-Path $bat)) { throw "no existe $bat" }

$action  = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT30S"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 5) -RestartCount 999 `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "VergeOICollector" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Colector historico de Open Interest de Verge (TRACK A). Auto-reinicio." -Force

Write-Host ""
Write-Host "OK - tarea 'VergeOICollector' registrada." -ForegroundColor Green
Write-Host "Arrancala ahora sin esperar al proximo login:"
Write-Host "    Start-ScheduledTask -TaskName VergeOICollector"
Write-Host ""
Write-Host "Verificar (tras ~10-20 min):"
Write-Host "    python agent\verify_oi_collector.py"
