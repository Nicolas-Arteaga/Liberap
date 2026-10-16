# One isolated, public-data collection pass for cost-v2 research.
# Designed to be called by Task Scheduler; never starts Verge or the agent.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = 'C:\Users\Nicolas\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$collector = Join-Path $root 'agent\backtest\collect_quote_spreads.py'
$db = Join-Path $root 'research\data\quote_spreads_v1.db'
$universe = Join-Path $root 'research\universe\microstructure_universe_v1.json'

& $python $collector --db $db --universe $universe --once --refresh-stats
if ($LASTEXITCODE -ne 0) { throw "quote spread collection failed: exit $LASTEXITCODE" }
