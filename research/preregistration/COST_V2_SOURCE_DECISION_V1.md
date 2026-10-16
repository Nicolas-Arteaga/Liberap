# Cost v2 source decision — V1

**Recorded:** 2026-10-16 UTC.  This is a data-availability decision, not a
result or a relaxation of the research gate.

## Reproducible probe

The frozen 200-symbol universe was probed at the start, midpoint, and end of
the requested Vision range.  The generated report is
`research/reports/vision_archive_probe_sample_v1.json` (ignored because it is
a generated network observation).  For all three sample days:

| Vision daily dataset | Symbols with all samples available |
| --- | ---: |
| `metrics` | 176 / 200 |
| `aggTrades` | 176 / 200 |
| `bookDepth` | 176 / 200 |
| `bookTicker` | **0 / 200** |

The canonical URL pattern requested by the original roadmap,
`data/futures/um/daily/bookTicker/{symbol}/{symbol}-bookTicker-{date}.zip`,
returned HTTP 404.  `bookDepth` exists, but its CSV fields are
`timestamp,percentage,depth,notional`; it contains no best bid or best ask and
therefore cannot produce an observed quoted spread.

## Decision

`cost_v2` is **BLOCKED_MISSING_HISTORICAL_QUOTE_SPREAD**.  It must not be
silently synthesized from OHLC range, book depth, or the legacy fee proxy.
The existing `cost_hourly_range_ge_2x_roundtrip` remains an *opportunity
filter*, not a spread estimate.  No event study may report a fee-only PASS as
a cost-v2 PASS.

Unblocking requires one of the following, with its own frozen provenance and
coverage audit: (1) an archived best-bid/best-ask dataset, or (2) a live
append-only quote collector mature enough for the target forward study.  Until
then, hypotheses that require the cost-v2 gate remain `PARK`/data-blocked;
they are not reparameterized or rescued.
