[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$SnapshotPath,
    [switch]$VerifyOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Get-Location).Path
$snapshot = (Resolve-Path $SnapshotPath).Path
$manifestPath = Join-Path $snapshot 'MANIFEST.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'MANIFEST.json not found.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

$invalid = @()
foreach ($file in $manifest.files) {
    $path = Join-Path $snapshot $file.path
    if (-not (Test-Path -LiteralPath $path)) { $invalid += "$($file.path): missing"; continue }
    $hash = Get-Sha256 $path
    if ($hash -ne $file.sha256) { $invalid += "$($file.path): checksum mismatch" }
}
if ($invalid.Count) { throw ("Snapshot verification failed:`n" + ($invalid -join "`n")) }
Write-Host "Snapshot verified: $($manifest.files.Count) files, commit $($manifest.repositoryCommit)"
if ($VerifyOnly) { return }

if (-not $Force) { throw 'Restore modifies local databases. Stop Docker first, then rerun with -Force after verification.' }

function Restore-IfPresent([string]$RelativePath, [string]$Bucket) {
    $source = Join-Path $snapshot (Join-Path $Bucket (Split-Path $RelativePath -Leaf))
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $repoRoot $RelativePath) -Force
    }
}

Restore-IfPresent 'agent\data\binance_vision_clean.db' 'market-data'
Restore-IfPresent 'agent\data\klines.db' 'market-data'
Restore-IfPresent 'agent\data\klines.db-wal' 'market-data'
Restore-IfPresent 'agent\data\klines.db-shm' 'market-data'
Restore-IfPresent 'agent\data\trade_metrics.jsonl' 'agent-state'
Restore-IfPresent 'agent\data\trades.csv' 'agent-state'
Restore-IfPresent 'agent\data\positions.json' 'agent-state'
Restore-IfPresent 'agent\data\auto_tuner_recommendations.json' 'agent-state'

$dump = Join-Path $snapshot 'postgres\Verge.dump'
if (Test-Path -LiteralPath $dump) {
    & docker cp $dump 'verge-db:/tmp/verge-state.dump'
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy PostgreSQL dump into verge-db.' }
    & docker exec verge-db pg_restore -U postgres -d Verge --clean --if-exists /tmp/verge-state.dump
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL restore failed.' }
}

Write-Host 'Restore complete. Start Docker with: docker compose up -d'
