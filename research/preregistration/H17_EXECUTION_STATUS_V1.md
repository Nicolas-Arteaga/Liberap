# H17 execution status — protocol/source audit

**Status:** `BLOCKED_FROZEN_EXECUTOR_NOT_FOUND`  
**Date:** 2026-10-16  
**Scope:** H17 only. This record does not revise the H17 hypothesis or
materialize a substitute study.

## Frozen H17 specification located

`ALPHA_HYPOTHESIS_LEDGER.md`, section **H17**, specifies the following:

- event: 4 h realized volatility crosses from below its causal 14 d p20 to
  above p60;
- direction: the return direction in the crossing candle;
- horizons: 2, 4, and 8 h;
- controls: temporal placebo, a sample matched on volatility level without a
  transition, and a price-range-breakout control matched in magnitude;
- population: full liquid universe using `klines_5m`.

That is a research protocol, not an executable frozen implementation. It does
not identify a source module, candidate revision, fixed liquidity filter, or
the exact construction necessary to reproduce all controls.

## Source audit

Repository searches for `H17`, `volatility compression`, and
`S2_compression_pending` found only:

1. the H17 prose in `ALPHA_HYPOTHESIS_LEDGER.md`;
2. this roadmap preregistration; and
3. `agent/backtest/r14_discovery.py` score `S2_compression_pending`.

`r14_discovery.py` is **not** an H17 executor: it ranks a restricted,
feature-complete cross-section on a 15-minute / four-hour rebalance grid and
combines compression with 4 h OI change. It neither implements H17's crossing
event, its direction/persistence test, nor its matched and breakout controls.
Treating it as H17 would alter the pre-registered study after inspecting the
code, so it is not eligible for execution under this roadmap.

## Decision

H17 remains **NOT RUN**, not failed and not passed. The permitted action is to
locate an already frozen executor/protocol with all H17 choices fixed. If none
exists, H17 is intentionally left unrun; creating a new implementation is a
new hypothesis/protocol and requires a separately dated preregistration.

