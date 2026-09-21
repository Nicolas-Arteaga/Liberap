param(
  [Parameter(Mandatory = $true)][string]$Repository,
  [Parameter(Mandatory = $true)][string]$RunDirectory
)

$ErrorActionPreference = 'Stop'
$started = Get-Date
$progressPath = Join-Path $RunDirectory 'progress.json'
$stdoutPath = Join-Path $RunDirectory 'signal_detection.stdout.log'
$scratch = Join-Path $Repository 'scratch_caso3_gt.json'

function Write-ProgressFile([string]$status, [int]$completed, [string]$step, [int]$exitCode) {
  [ordered]@{
    id = 'f1-caso3-signal-detection-20260920-1945'
    phase = 1
    status = $status
    started_at = $started.ToString('o')
    updated_at = (Get-Date).ToString('o')
    scope = 'Comparación de detección del motor MA Geometry contra los 45 trades de scratch Caso 3.'
    completed = $completed
    total = 45
    current_step = $step
    command = 'docker compose exec -T backtest python /app/backtest/diag_caso3_detection.py'
    stdout_path = 'lab/runs/f1-caso3-signal-detection-20260920-1945/signal_detection.stdout.log'
    exit_code = $exitCode
    production_writes = $false
  } | ConvertTo-Json | Set-Content -LiteralPath $progressPath -Encoding utf8
}

Set-Location -LiteralPath $Repository
Write-ProgressFile 'running' 0 'Copiando ground truth temporal al contenedor' -1
docker cp $scratch 'verge-backtest:/scratch_caso3_gt.json' 2>&1 | Tee-Object -LiteralPath $stdoutPath
Write-ProgressFile 'running' 0 'Ejecutando detección señal por señal' -1
docker compose exec -T backtest python /app/backtest/diag_caso3_detection.py 2>&1 | Tee-Object -LiteralPath $stdoutPath -Append
$exitCode = $LASTEXITCODE
$elapsed = ((Get-Date) - $started).TotalSeconds
Add-Content -LiteralPath $stdoutPath -Value ("`nRUN_STARTED={0}`nRUN_FINISHED={1}`nDURATION_SECONDS={2:N3}`nEXIT_CODE={3}" -f $started.ToString('o'), (Get-Date).ToString('o'), $elapsed, $exitCode)
Write-ProgressFile $(if ($exitCode -eq 0) { 'completed' } else { 'failed' }) 45 'Detección terminada; revisar stdout' $exitCode
exit $exitCode
