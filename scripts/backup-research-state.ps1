[CmdletBinding()]
param(
    [string]$DestinationRoot,
    [switch]$SkipPostgres,
    [string]$FinalizeExistingSnapshot
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Get-Location).Path
if (-not $DestinationRoot) { $DestinationRoot = Join-Path $repoRoot 'backups' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$snapshot = if ($FinalizeExistingSnapshot) { (Resolve-Path $FinalizeExistingSnapshot).Path } else { Join-Path $DestinationRoot "verge-state-$stamp" }
$reuseSnapshot = -not [string]::IsNullOrWhiteSpace($FinalizeExistingSnapshot)

if (-not $reuseSnapshot) {
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $snapshot -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $snapshot 'market-data') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $snapshot 'agent-state') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $snapshot 'postgres') | Out-Null
}

function Copy-IfPresent([string]$RelativePath, [string]$Bucket) {
    $source = Join-Path $repoRoot $RelativePath
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $snapshot $Bucket) -Force
    }
}

function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

function Snapshot-SqliteIfPresent([string]$RelativePath) {
    $source = Join-Path $repoRoot $RelativePath
    if (Test-Path -LiteralPath $source) {
        $destination = Join-Path $snapshot (Join-Path 'market-data' (Split-Path $RelativePath -Leaf))
        & py -3 (Join-Path $repoRoot 'scripts\snapshot_sqlite.py') $source $destination
        if ($LASTEXITCODE -ne 0) { throw "SQLite snapshot failed: $RelativePath" }
    }
}

if (-not $reuseSnapshot) {
    Snapshot-SqliteIfPresent 'agent\data\binance_vision_clean.db'
    Snapshot-SqliteIfPresent 'agent\data\klines.db'
    Copy-IfPresent 'agent\data\trade_metrics.jsonl' 'agent-state'
    Copy-IfPresent 'agent\data\trades.csv' 'agent-state'
    Copy-IfPresent 'agent\data\positions.json' 'agent-state'
    Copy-IfPresent 'agent\data\auto_tuner_recommendations.json' 'agent-state'
    Copy-IfPresent 'docker-compose.yml' '.'
    Copy-IfPresent '.env.example' '.'

    # Generated research models and result ledgers are reproducibility inputs, not
    # Git blobs. Keep them alongside the raw data in the same verified snapshot.
    $artifactDir = Join-Path $snapshot 'research-artifacts'
    New-Item -ItemType Directory -Path $artifactDir | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'agent\backtest') -File |
        Where-Object { $_.Name -like '*.pkl' -or $_.Name -like '*_model.txt' -or $_.Name -like '*.jsonl' } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $artifactDir -Force }

    if (-not $SkipPostgres) {
        & docker exec verge-db pg_dump -U postgres -d Verge --format=custom --file=/tmp/verge-state.dump
        if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed. Is verge-db running?' }
        & docker cp 'verge-db:/tmp/verge-state.dump' (Join-Path $snapshot 'postgres\Verge.dump')
        if ($LASTEXITCODE -ne 0) { throw 'Could not copy PostgreSQL dump from verge-db.' }
    }
}

$gitSha = (& git -C $repoRoot rev-parse HEAD 2>$null)
$manifest = Get-ChildItem -LiteralPath $snapshot -Recurse -File |
    Where-Object { $_.Name -ne 'MANIFEST.json' } |
    ForEach-Object {
        [pscustomobject]@{
            path = $_.FullName.Substring($snapshot.Length + 1).Replace('\', '/')
            bytes = $_.Length
            sha256 = Get-Sha256 $_.FullName
        }
    }

[pscustomobject]@{
    schema = 'verge-state-backup/v1'
    createdAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    repositoryCommit = $gitSha
    files = $manifest
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $snapshot 'MANIFEST.json') -Encoding utf8

Write-Host "Snapshot complete: $snapshot"
Write-Host "Files: $($manifest.Count). Verify with scripts\restore-research-state.ps1 -SnapshotPath '$snapshot' -VerifyOnly"
