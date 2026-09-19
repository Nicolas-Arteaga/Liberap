# Verge Invariant Research Engine (VIRE) — Specification

## Purpose

VIRE is a new, isolated research track. It does not read, modify, rank, or
promote legacy `StrategyProfiles`. Its job is to turn the historical market
data already available to Verge into a small, auditable queue of **paper-only
candidates**.

It is deliberately not a generator of "winning strategies". A candidate must
survive an explicit falsification protocol before it can be shown as eligible
for paper trading.

## Research model

Every experiment is composed from independent modules:

1. **Relationship** — a structural relationship (initially a hedge-ratio pair
   spread / cointegration candidate).
2. **Direction** — long spread, short spread, or both independently.
3. **Entry** — a measurable deviation event, never a hand-picked trade.
4. **Exit policy** — mean reversion, stop, timeout, and optional giveback are
   evaluated separately on the same signal stream.
5. **Execution model** — fees, slippage and two-leg execution are deducted.
6. **Validation** — chronological train/validation/OOS splits plus
   perturbation, parameter-neighbourhood, concentration and cross-pair tests.

The engine records the complete experiment, including failed candidates. It
never overwrites an earlier run.

## Initial scope

The first vertical slice is intentionally narrow and executable now:

- discover statistically stationary log-price spreads from the locally cached
  OHLCV universe;
- simulate market-neutral pair trades for both directions;
- search a bounded, pre-declared exit matrix;
- account for both legs' fees and slippage;
- run chronological validation and adversarial checks;
- persist results to the research SQLite database;
- expose a REST API and a dedicated Angular research cockpit.

Future modules (funding carry, OI/liquidation sequences, order-flow and
cross-venue basis) use the same experiment contract. They are not silently
mixed into the first result set.

## Promotion gate

`PAPER_READY` requires all of the following:

- positive validation and OOS net PnL after configured costs;
- minimum trade count in OOS;
- no single trade contributes more than the configured concentration cap;
- neighbouring parameters do not reverse the result;
- perturbing fills/slippage does not make OOS negative;
- no look-ahead data is used;
- explicit provenance, data range and assumptions are stored.

Anything else is `REJECTED`, `INSUFFICIENT_DATA`, or `RESEARCH_ONLY`.
No status reaches a live strategy, an existing profile, or an execution API.

## E2E contract

The backend E2E test creates a temporary SQLite dataset with a synthetic
cointegrated pair and a non-stationary control, runs discovery and validation,
and asserts that: the valid relationship is persisted, the control is rejected,
costs are applied, and no production endpoint/database is touched. The frontend
build is run after the route and cockpit are added.
