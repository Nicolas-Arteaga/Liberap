# Microstructure roadmap — preregistration V1

**Frozen at:** 2026-10-16 (America/Argentina/Buenos_Aires)  
**Scope:** research only. No agent, Scan Ledger, StrategyProfiles, production, mainnet, testnet, or deployment endpoint is in scope.

## Canonical-source rule

The current code and `ALPHA_HYPOTHESIS_LEDGER.md` override earlier roadmap prose if they conflict. The ledger already records H13, H15, and H16 as **FAILED** in prior rounds. They are therefore excluded from re-testing and from all new multiple-testing families in this run. They are reported as prior closures, not re-labelled or rescued.

## Dataset and venue rules

- Price and OI/taker/ratio inputs use the Binance USD-M Vision datasets only.
- The live liquidation feed remains Bybit-only and is never merged with Binance price/OI in a claim of venue-identical execution. H14 is preparation-only until its frozen 60-day data gate passes.
- Missing coverage, duplicates, timestamp ambiguity, or unvalidated field semantics invalidate the affected symbol/split; zero must never be imputed.
- All derived inputs are lagged by one completed 5-minute bucket whenever `create_time` semantics cannot be established unambiguously.

## Ex-ante universe definition

`research/universe/build_microstructure_universe.py` will snapshot the top 200 Binance USD-M **PERPETUAL**, `TRADING`, USDT-quoted instruments ranked by the exchange's 24-hour `quoteVolume`, excluding leveraged tokens and stablecoin/stablecoin pairs. The snapshot JSON, UTC timestamp, source response hash, and resulting symbol list are immutable once committed. No later coverage or performance result may alter membership.

## Hypotheses and order

1. **H17 — pipeline sanity check:** its pre-existing protocol is run only if its frozen source protocol is found. A large apparent alpha is treated as a pipeline fault until independently audited.
2. **H14 — liquidation cascade:** no backtest in this run. Preserve/monitor data only. Formal execution requires the already frozen H14 gate: >=60 collection days, >=90% uptime, liquidity filter, matched control, placebo, and OI conditioning.

No other H13–H20 hypothesis is introduced, modified, relaxed, or optimized in this preregistration.

## Controls and gates for every newly-run study

- Entry uses the next executable completed-bar open; no same-bar execution.
- Train/validation/final-OOS are temporally ordered 50%/25%/25%; final OOS is consulted once.
- Matched non-event controls, +48h temporal placebo, residualization against prior return, bootstrap clustered by symbol (2,000 resamples), temporal halves, BTC-regime partition, removal of the top 5% events and top symbols are mandatory where the frozen protocol supports them.
- Costs use `max(fee_only_bps, cost_v2_bps(symbol, hour))`; no fee-only PASS is valid after cost v2 exists.
- PASS requires at least 300 events and 30 symbols, no symbol >20% of events, top five <=50%, both temporal halves with an incremental-control CI excluding zero, net >=15 bp after cost v2, >=10 bp after removing the top 5% events, and BH q<=0.05 over the frozen set of actually-open hypotheses.
- Anything else is `PARK`, `FAILED`, or `INSUFFICIENT_SAMPLE`; none is promoted to trading.

## Multiple-testing family

The family is exactly the pre-existing open, executable hypotheses after ledger closure review. Before a test is run, its identifier and cells are appended to `research/preregistration/MICROSTRUCTURE_TEST_MANIFEST_V1.jsonl`; BH is applied to that fixed manifest. Variants, rescue tests, and post-result parameter changes are prohibited.

## Stop conditions

- A result violating the protocol is discarded, not repaired by a new parameter set.
- H14 remains calendar-gated; this run prepares but does not execute it.
- A hard data limitation is reported with evidence while independent infrastructure tasks continue.
