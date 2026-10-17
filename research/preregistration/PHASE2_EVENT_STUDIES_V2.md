# Phase 2 event studies v2 — frozen before execution

## Scope and provenance

Frozen at 2026-10-17 from `ROADMAP_ALPHA_MICROESTRUCTURA.md` (commit
`f9054b2`) and `ALPHA_HYPOTHESIS_LEDGER.md` (§H13, §H15, §H16, §H17).
This replaces neither prior exploratory runs nor their labels.  It is a fresh,
single, causal replication using the isolated OI/funding stores.  No result
may alter any rule below.

## Shared panel and splits

- Venue: Binance USD-M; price source: finalized Binance OHLCV only.
- Event clock: 15-minute bars.  OI is visible only after one completed
  five-minute bucket; funding only after its settlement timestamp.
- Universe: frozen `research/universe/microstructure_universe_v1.json`, then
  each hypothesis' coverage gate.  A cell with fewer than 300 events or 30
  symbols is `INSUFFICIENT_SAMPLE`, never a relaxed PASS/FAIL.
- Temporal split is 50% TRAIN / 25% VALIDATION / 25% OOS by event date.  Rule
  selection is prohibited: all cells and horizons listed below are reported.
- Controls per cell: temporal placebo at +48 h; matched non-event control
  within the same symbol, split, return-sign, prior-return and realized-vol
  quintiles; residualization against prior return and concurrent BTC return;
  symbol-cluster bootstrap (2,000 resamples); first/second temporal halves;
  BTC UP/FLAT/DOWN terciles; drop top 5% event returns and top 5 symbols.
- Multiplicity: Benjamini-Hochberg at q=0.05 across every eligible
  hypothesis/cell/horizon in this document.  No post-hoc removal.

## H17 — volatility compression to expansion

For each liquid 5m symbol, use close-to-close realized volatility over the
last 48 completed 5m closes.  Its causal reference distribution is the prior
4,032 completed 5m observations (14 days).  An event is the first bar after a
state below p20 for which the 4h realized volatility is above p60.  Event
direction is the sign of that bar's close/open log return; ties are excluded.
Cooldown is four hours per symbol.  Forward signed log returns are assessed at
2, 4 and 8 hours.  The matched control has the same event direction, prior
return/volatility quintiles and p60-or-higher volatility but no p20-to-p60
transition in its preceding four hours.  The price-only control is the same
matching without any volatility transition, selected on equal-magnitude range
breakout.  H0: incremental signed return versus both controls is zero.

## H13 — OI / price quadrants

At 15m resolution: prior-return and delta-OI windows are four bars (1h), OI
z-score uses the prior 7 days (672 bars), event thresholds are
`abs(z_price)>=1` and `abs(z_doi)>=1`, and cooldown is four hours per symbol.
The four frozen cells are A=(price down, OI up), B=(down, down), C=(up, up),
D=(up, down).  All are measured at 1, 2 and 4 hours.  Directional result is
the pre-registered mechanically implied direction from the ledger; raw
incremental effects are always also reported.  The control is identical price
sign/return/volatility matching with `abs(z_doi)<=0.3`.

## H15 — joint OI / taker / price exhaustion

At 15m resolution and the same 1h window, event=price return in bottom decile
AND delta-OI in top decile AND taker-sell ratio in top decile, each causal
within symbol.  The pre-registered directional outcome is long at 4, 8 and
12 hours.  The control has matching price return and volatility quintiles but
does not satisfy the joint OI+taker state.

## H16 — funding extreme / OI local high

Funding is the most recently settled rate; it is never shifted backward.
Event=rate in either causal 10% tail over the prior 90 settlements AND OI at
the causal maximum of the prior 72 hours.  Positive-funding events are short;
negative-funding events are long.  Horizons are 8, 16 and 24 hours.  The
control is the same funding-tail and price/volatility match with OI below its
72h maximum.  If <90 days of OI/funding overlap or the shared sample gate
fails, label `INSUFFICIENT_SAMPLE`.

## Two separate verdicts

**Mechanism** is PASS only if the matched-control incremental effect has the
pre-registered sign, its cluster-bootstrap CI excludes zero in both temporal
halves, concentration limits hold (no symbol >20%; top five <=50%), and BH
passes.  It is FAILED when an eligible cell fails those conditions, otherwise
INSUFFICIENT_SAMPLE/PARK.

**Economic** uses sensitivity-only round-trip cost bands of 10, 26 and 36 bp;
these are not substitute spreads and must never be called `cost_v2`.  Report
net signed return for each band.  If its sign differs across bands the verdict
is `PENDING_COST_V2`; otherwise state the common sign while still noting that
live spread calibration remains pending.

## Exclusions

H14 is forward-only and is not executed here. H20 is not executed unless an
H13 mechanism PASS occurs.  This study does not create a StrategyProfile,
touch the live agent/ledger, or activate a trade.
