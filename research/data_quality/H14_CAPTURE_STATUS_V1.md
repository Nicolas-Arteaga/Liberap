# H14 liquidation capture status V1

**Observed at:** 2026-10-16T23:11:34Z  
**Method:** read-only query of the primary agent's local `klines.db`; no
process, task, agent configuration, or data was modified.

## Measured state

- `liquidations_research`: **222,197 events**, **50 symbols**.
- Youngest event age at observation: **2,380.97 minutes** (~39.7 hours).
- The latest `liq_collector_health` records are from the same stale period;
  the most recent recorded connection subscribed to 63 symbols.

## Consequence

H14's frozen gate requires at least 60 collection days and 90% uptime, plus
the pre-specified liquidity, matched-control, placebo, and OI-conditioning
tests. The current append-only source is stale, so its calendar cannot mature
and no H14 study may run. This is a **data-source block**, not a negative
strategy result and not permission to replace the dataset with a different
venue or synthetic events.

## Scope boundary

Repairing or restarting the live collector/agent is intentionally outside this
research worktree and was not performed. The safe next step is an owner-led
restoration of the existing collector, followed by fresh read-only coverage
verification before any H14 execution is considered.
