"""Strict cost-v2 lookup from independently captured quote-spread statistics."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


class CostCoverageError(RuntimeError):
    """Raised instead of silently substituting a fee-only cost."""


@dataclass(frozen=True)
class CostQuote:
    symbol: str
    utc_hour: int
    sample_count: int
    p90_spread_bps: float
    fee_roundtrip_bps: float

    @property
    def conservative_roundtrip_bps(self) -> float:
        # Crossing from mid to ask at entry and bid to mid at exit costs one
        # quoted spread in total; fees are additive. Slippage remains unmodelled
        # and therefore this is a lower bound, not an execution claim.
        return self.fee_roundtrip_bps + self.p90_spread_bps


def cost_bps(db_path: str, symbol: str, utc_hour: int, *, fee_roundtrip_bps: float = 8.0,
             min_samples: int = 20) -> CostQuote:
    """Return the conservative observed cost or raise a coverage error.

    The caller must convert an execution timestamp to ``utc_hour``. Exact-hour
    matching is intentional: borrowing a future hour would be look-ahead and
    borrowing an arbitrary past hour would hide a missing-regime problem.
    """
    path = Path(db_path)
    if not path.exists():
        raise CostCoverageError(f"COST_V2_COVERAGE_MISSING: database absent: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        row = conn.execute("""
            SELECT sample_count,p90_spread_bps FROM spread_stats
            WHERE venue='binance_usdm' AND symbol=? AND utc_hour=?
        """, (symbol.upper(), int(utc_hour))).fetchone()
    finally:
        conn.close()
    if row is None or int(row[0]) < min_samples:
        found = 0 if row is None else int(row[0])
        raise CostCoverageError(f"COST_V2_COVERAGE_INSUFFICIENT: {symbol}@{utc_hour} samples={found}<{min_samples}")
    return CostQuote(symbol.upper(), int(utc_hour), int(row[0]), float(row[1]), float(fee_roundtrip_bps))
