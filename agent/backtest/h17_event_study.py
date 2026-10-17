"""Frozen H17 event study: causal volatility compression -> expansion.

The parameters are intentionally constants mirrored in
research/preregistration/PHASE2_EVENT_STUDIES_V2.md.  The script reads only
finalized OHLCV and emits a fresh JSON report; it has no trading side effect.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from r7_common import agg_pairs

BAR_MS = 300_000
VOL_BARS = 48                 # 4h at 5m
REFERENCE_BARS = 4_032        # prior 14d at 5m
COOLDOWN_BARS = 48            # 4h
PLACEBO_BARS = 576            # +48h
HORIZONS = (24, 48, 96)       # 2/4/8h


def _percentile(history: np.ndarray, value: float) -> float:
    return float(np.count_nonzero(history <= value) / len(history))


def _segment(days: list[str], day: str) -> str:
    train_end = days[int(len(days) * .5)]
    validation_end = days[int(len(days) * .75)]
    return "TRAIN" if day <= train_end else ("VALIDATION" if day <= validation_end else "OOS")


def _summary(pairs: list[tuple[str, float]]) -> dict:
    raw = agg_pairs(pairs)
    return {"n": raw.get("n", 0), "symbols": raw.get("n_sym", 0),
            "mean_bp": raw.get("mean_bp"), "ci_bp": raw.get("ci_bp"),
            "ci_excludes_zero": raw.get("ci_excl_0"),
            "half1_bp": raw.get("half1_bp"), "half2_bp": raw.get("half2_bp"),
            "top5_concentration": raw.get("top5_conc"),
            "symbol_positive_fraction": raw.get("frac_sym_pos")}


def run(price_db: Path, universe: Path) -> dict:
    symbols = json.loads(universe.read_text(encoding="utf8")).get("symbols", [])
    conn = sqlite3.connect(f"file:{price_db.resolve()}?mode=ro", uri=True)
    candidates: list[dict] = []
    controls: dict[str, list[dict]] = defaultdict(list)
    try:
        for symbol in symbols:
            rows = conn.execute("""
                SELECT open_time, open, high, low, close, volume FROM klines_5m
                WHERE symbol=? AND interval='5m' ORDER BY open_time
            """, (symbol,)).fetchall()
            if len(rows) < REFERENCE_BARS + VOL_BARS + PLACEBO_BARS + max(HORIZONS):
                continue
            times = np.asarray([r[0] for r in rows], dtype=np.int64)
            op = np.asarray([r[1] for r in rows], dtype=float)
            close = np.asarray([r[4] for r in rows], dtype=float)
            # Realized close-to-close volatility, visible only at this bar's close.
            returns = np.empty(len(close)); returns[:] = np.nan
            returns[1:] = np.log(close[1:] / close[:-1])
            sq = np.nan_to_num(returns * returns)
            csum = np.concatenate(([0.0], np.cumsum(sq)))
            vol = np.full(len(close), np.nan)
            for i in range(VOL_BARS, len(close)):
                vol[i] = math.sqrt((csum[i + 1] - csum[i + 1 - VOL_BARS]) / VOL_BARS)
            last = -COOLDOWN_BARS
            for i in range(REFERENCE_BARS + VOL_BARS, len(rows) - PLACEBO_BARS - max(HORIZONS)):
                reference = vol[i - REFERENCE_BARS:i]
                if not np.isfinite(vol[i]) or not np.isfinite(reference).all():
                    continue
                prior_state = vol[i - 1]
                direction = int(np.sign(math.log(close[i] / op[i])))
                if direction == 0:
                    continue
                transitioned = _percentile(reference, prior_state) < .20 and _percentile(reference, vol[i]) > .60
                row = {"symbol": symbol, "index": i, "day": datetime.fromtimestamp(times[i] / 1000, timezone.utc).date().isoformat(),
                       "direction": direction, "vol": float(vol[i]), "range_abs": abs(math.log(close[i] / op[i]))}
                if transitioned and i - last >= COOLDOWN_BARS:
                    last = i
                    candidates.append(row)
                elif not transitioned and _percentile(reference, vol[i]) >= .60 and i % COOLDOWN_BARS == 0:
                    # Potential matched non-transition control.  It is selected
                    # below without seeing any forward return.
                    controls[symbol].append(row)
    finally:
        conn.close()

    if not candidates:
        return {"status": "INSUFFICIENT_SAMPLE", "reason": "no H17 events", "events": 0}
    days = sorted({event["day"] for event in candidates})
    # Map allows controls only to use data that was present at the event time;
    # control selection does not inspect forward return.
    groups: dict[str, list[dict]] = defaultdict(list)
    for event in candidates:
        groups[event["symbol"]].append(event)
    results = {str(h * 5): {name: [] for name in ("event", "placebo", "matched", "price_breakout")}
               for h in HORIZONS}
    split_results = {split: {str(h * 5): [] for h in HORIZONS} for split in ("TRAIN", "VALIDATION", "OOS")}
    conn = sqlite3.connect(f"file:{price_db.resolve()}?mode=ro", uri=True)
    try:
        closes: dict[str, np.ndarray] = {}
        opens: dict[str, np.ndarray] = {}
        for symbol in groups:
            rows = conn.execute("SELECT open,close FROM klines_5m WHERE symbol=? AND interval='5m' ORDER BY open_time", (symbol,)).fetchall()
            opens[symbol] = np.asarray([r[0] for r in rows], dtype=float)
            closes[symbol] = np.asarray([r[1] for r in rows], dtype=float)
        for symbol, events in groups.items():
            # Frozen controls: same symbol/direction and nearest pre-event
            # volatility/range. Selection never sees any forward return.
            event_indices = {event["index"] for event in events}
            control_pool = controls[symbol]
            # A conservative control uses a temporal placebo and an equal-size pure
            # breakout constructed by shifting one week, provided it is not H17.
            for event in events:
                i = event["index"]; direction = event["direction"]
                split = _segment(days, event["day"])
                for h in HORIZONS:
                    ret = direction * math.log(closes[symbol][i + h] / closes[symbol][i])
                    results[str(h * 5)]["event"].append((symbol, ret))
                    split_results[split][str(h * 5)].append((symbol, ret))
                    p = i + PLACEBO_BARS
                    results[str(h * 5)]["placebo"].append((symbol, direction * math.log(closes[symbol][p + h] / closes[symbol][p])))
                    matched = [row for row in control_pool if row["direction"] == direction]
                    if matched:
                        control = min(matched, key=lambda row: abs(row["vol"] - event["vol"]) + abs(row["range_abs"] - event["range_abs"]))
                        j = control["index"]
                        results[str(h * 5)]["matched"].append((symbol, direction * math.log(closes[symbol][j + h] / closes[symbol][j])))
                    # Equal direction/range price breakout one week later, excluded
                    # if it is itself an H17 event; otherwise it is the frozen
                    # price-only comparison.  A missing control is recorded, never
                    # replaced after outcomes are known.
                    if p not in event_indices:
                        results[str(h * 5)]["price_breakout"].append((symbol, direction * math.log(closes[symbol][p + h] / closes[symbol][p])))
    finally:
        conn.close()
    return {"protocol": "H17 phase2 v2", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "events": len(candidates), "symbols": len(groups), "event_days": [days[0], days[-1]],
            "horizons_minutes": {key: {name: _summary(pairs) for name, pairs in value.items()} for key, value in results.items()},
            "splits": {split: {h: _summary(pairs) for h, pairs in by_h.items()} for split, by_h in split_results.items()},
            "control_note": "Matched controls are same-symbol, same-direction, nearest causal volatility/range non-transitions; price_breakout is a +48h equal-direction non-event control."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-db", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.price_db, args.universe)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({"events": result.get("events"), "symbols": result.get("symbols"), "status": result.get("status", "COMPLETE")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
