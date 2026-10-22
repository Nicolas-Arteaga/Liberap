# Long/short ratios: one frozen event family

Frozen before execution on 2026-10-17.  This is deliberately not H13/R29:
R29 tested OI level/change/acceleration/shock and combinations with price and
volume. It did not apply the Phase-2 event-study contract to
`toptrader_ls_pos`, `global_ls_acct`, or `taker_ls_vol`.

## Cells

For each of the three ratios, a causal z-score uses the preceding 672 complete
15m observations (7 days).  Events are `z >= +2` and `z <= -2`; cooldown is
4h per symbol and feature/sign.  Horizons: 1h, 4h, 8h.  Directional returns
are reported raw plus both long and short signed views; no sign is selected
after seeing results.

## Controls and decisions

Temporal placebo: same event direction at +48h. Matched control: same symbol,
same sign of prior 1h return and same realized-volatility quintile, with
`abs(z)<0.3` for that ratio. Splits: 50/25/25 chronological. Report bootstrap
CI by symbol, halves, concentration, and BH q=.05 over 18 cells
(3 ratios x 2 tails x 3 horizons). Cost sensitivity only: 10/26/36bp RT.
Mechanism PASS requires positive incremental matched-control effect, CI
excluding zero in both halves, BH pass, >=300 events/30 symbols and
concentration limits. Economic verdict is PENDING_COST_V2 when bands differ
in sign. No variants, grids or rescue tests are allowed.
