# register_research_tasks.ps1
# Registra en Windows Task Scheduler los 5 componentes de research infra con
# auto-arranque tras reboot/login.  REQUIERE POWERSHELL ELEVADO (Run as Admin).
#
#   powershell -ExecutionPolicy Bypass -File research\ops\register_research_tasks.ps1
#
# Idempotente: -Force sobrescribe si ya existen.
# Para VER estado:   Get-ScheduledTask -TaskName "Verge*" | ft TaskName,State
# Para BORRAR todo:   Get-ScheduledTask -TaskName "Verge*Research*","Verge*Collector*","Verge*Tracker*","Verge*Monitor*" | Unregister-ScheduledTask -Confirm:$false

$ErrorActionPreference = "Stop"
$repo   = "C:\Users\Nicolas\Desktop\Verge\Verge"
$agent  = "$repo\agent"
$py     = (Get-Command python).Source
$user   = "$env:USERDOMAIN\$env:USERNAME"

function New-VergeTask {
    param($Name, $Exec, $Args, $WorkDir, $Triggers, [switch]$RestartOnFail)
    $action  = New-ScheduledTaskAction -Execute $Exec -Argument $Args -WorkingDirectory $WorkDir
    $set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                 -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    if ($RestartOnFail) {
        $set.RestartInterval = "PT5M"
        $set.RestartCount    = 999
    }
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Triggers -Settings $set `
        -RunLevel Highest -User $user -Force | Out-Null
    Write-Host "OK  $Name"
}

# 1. OI collector — al login, reinicio cada 5 min si se cae
New-VergeTask -Name "VergeOICollector" -Exec $py -Args "-u open_interest_collector.py" `
    -WorkDir $agent -Triggers (New-ScheduledTaskTrigger -AtLogOn) -RestartOnFail

# 2. Liquidation tracker — al login, reinicio cada 5 min
New-VergeTask -Name "VergeLiqTracker" -Exec $py -Args "-u _run_liq_tracker.py" `
    -WorkDir $agent -Triggers (New-ScheduledTaskTrigger -AtLogOn) -RestartOnFail

# 3. OI coverage monitor — cada 6 h
$t6h = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval ([TimeSpan]::FromHours(6))
New-VergeTask -Name "VergeOIMonitor" -Exec $py -Args "research\data_quality\oi_quality_monitor.py" `
    -WorkDir $repo -Triggers $t6h

# 4. Liquidation coverage monitor — cada 6 h
$t6h2 = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddMinutes(30)) -RepetitionInterval ([TimeSpan]::FromHours(6))
New-VergeTask -Name "VergeLiqMonitor" -Exec $py -Args "research\data_quality\liquidation_quality_monitor.py" `
    -WorkDir $repo -Triggers $t6h2

# 5. Research backup — diario 4am + al login
New-VergeTask -Name "VergeResearchBackup" -Exec $py -Args "-u research\backup\backup_research_data.py" `
    -WorkDir $repo -Triggers @((New-ScheduledTaskTrigger -Daily -At 4am), (New-ScheduledTaskTrigger -AtLogOn))

Write-Host ""
Write-Host "Registradas. Estado:"
Get-ScheduledTask -TaskName "Verge*" | Sort-Object TaskName | Format-Table TaskName, State -AutoSize
