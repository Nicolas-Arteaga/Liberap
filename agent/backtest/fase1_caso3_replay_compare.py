"""Fase 1: replay autónomo de Caso 3 y comparación posterior contra ground truth.

El replay base nunca recibe los trades reales para decidir entradas. Sólo después
de correr todo el universo se usan `scratch_caso3_gt.json` para matching.
La variante `shadow_missing_coverage` es diagnóstica y está etiquetada: reserva
slots para los siete trades reales sin klines, para medir el sesgo de cobertura.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
from datetime import datetime

from ma_geometry_cached import CachedMaSlopeReplay, FEE_PER_SIDE


HOUR_MS = 60 * 60 * 1000
BAR_MS = 15 * 60 * 1000
DEFAULT_DB = "/app/data/binance_vision_clean.db"


def millis(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def norm_reason(value: str | None) -> str:
    value = (value or "").upper()
    if value in {"SL", "STOP", "STOP_LOSS"}:
        return "SL"
    if value in {"TP", "TAKE_PROFIT"}:
        return "TP"
    return "TIMEOUT"


def return_pct(side: str, entry: float, close: float) -> float:
    return ((entry - close) / entry * 100.0) if side == "short" else ((close - entry) / entry * 100.0)


def build_trades(replay: CachedMaSlopeReplay, start_ms: int, end_ms: int, symbols: list[str], reservations=None):
    """Mismo orden global/cupos que CachedMaSlopeReplay.run; sin guía real en base."""
    raw = []
    for symbol in symbols:
        raw.extend(replay.signals(symbol, start_ms, end_ms))
    raw = [replay._exit(signal) for signal in raw]
    raw.sort(key=lambda trade: (trade["open_time"], trade["symbol"]))
    reservations = sorted(reservations or [])
    reservation_index = 0
    open_until = []
    accepted = []
    for trade in raw:
        while reservation_index < len(reservations) and reservations[reservation_index][0] <= trade["open_time"]:
            open_until.append(reservations[reservation_index][1])
            reservation_index += 1
        open_until = [close for close in open_until if close > trade["open_time"]]
        if len(open_until) >= replay.slots:
            continue
        open_until.append(trade["close_time"])
        qty = replay.margin / trade["entry"]
        trade["pnl"] = qty * (trade["entry"] - trade["close"]) - (replay.margin + qty * trade["close"]) * FEE_PER_SIDE
        trade["return_pct"] = return_pct(trade["side"], trade["entry"], trade["close"])
        accepted.append({key: value for key, value in trade.items() if key not in {"rows", "index"}})
    return raw, accepted


def compare(replay_trades, real_trades, bar_ms=BAR_MS):
    matched_replay = set()
    matches = []
    real_without = []
    for real_index, real in enumerate(real_trades):
        candidates = [
            (abs(trade["open_time"] - real["open_time"]), index, trade)
            for index, trade in enumerate(replay_trades)
            if index not in matched_replay
            and trade["symbol"] == real["symbol"]
            and trade["side"] == real["side"]
            and abs(trade["open_time"] - real["open_time"]) <= bar_ms
        ]
        if not candidates:
            real_without.append(real_index)
            continue
        _, replay_index, replay = min(candidates)
        matched_replay.add(replay_index)
        matches.append({
            "real_index": real_index,
            "symbol": real["symbol"],
            "real_open_time": real["open_time"],
            "replay_open_time": replay["open_time"],
            "entry_delta_ms": replay["open_time"] - real["open_time"],
            "real_reason": real["reason"],
            "replay_reason": norm_reason(replay["reason"]),
            "exit_reason_match": real["reason"] == norm_reason(replay["reason"]),
            "real_return_pct": real["return_pct"],
            "replay_return_pct": replay["return_pct"],
            "return_pct_delta": replay["return_pct"] - real["return_pct"],
        })
    return {
        "matches": matches,
        "real_without_match": real_without,
        "replay_without_match": [index for index in range(len(replay_trades)) if index not in matched_replay],
    }


def summarize(comparison, replay_trades, total_real, measurable_real):
    matches = comparison["matches"]
    reason_matches = sum(item["exit_reason_match"] for item in matches)
    return {
        "real_total": total_real,
        "real_measurable": measurable_real,
        "matched": len(matches),
        "match_rate_total": len(matches) / total_real if total_real else None,
        "match_rate_measurable": len(matches) / measurable_real if measurable_real else None,
        "real_without_match": len(comparison["real_without_match"]),
        "replay_total": len(replay_trades),
        "replay_without_match": len(comparison["replay_without_match"]),
        "exit_reason_matched": reason_matches,
        "exit_reason_match_rate": reason_matches / len(matches) if matches else None,
        "replay_return_pct_sum": sum(item["replay_return_pct"] for item in matches),
        "real_return_pct_sum": sum(item["real_return_pct"] for item in matches),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--limit-symbols", type=int, default=None, help="Sólo para smoke tests; nunca usar en la corrida completa.")
    args = parser.parse_args()
    real_source = json.load(open(args.scratch, encoding="utf-8"))
    real = []
    for item in real_source:
        # Caso 3 es short; se valida estructuralmente por SL > entrada.
        side = "short" if item["sl"] > item["entry"] else "long"
        real.append({
            "symbol": item["sym"], "side": side, "open_time": millis(item["open_utc"]),
            "close_time": millis(item["close_utc"]), "reason": norm_reason(item.get("real_outcome")),
            "return_pct": return_pct(side, item["entry"], item["exit_px"]),
        })
    start_ms = min(item["open_time"] for item in real)
    end_ms = max(item["open_time"] for item in real)
    replay = CachedMaSlopeReplay(args.db, margin=150.0, slots=3)
    available = replay.symbols()
    symbols = available[:args.limit_symbols] if args.limit_symbols else available
    available_set = set(available)
    measurable = [item for item in real if item["symbol"] in available_set]
    missing = [item for item in real if item["symbol"] not in available_set]
    raw, base = build_trades(replay, start_ms, end_ms, symbols)
    base_cmp = compare(base, real)
    # Sólo diagnóstico de cobertura: los ausentes consumen sus slots reales.
    reservations = sorted((item["open_time"], item["close_time"]) for item in missing)
    _, shadow = build_trades(replay, start_ms, end_ms, symbols, reservations=reservations)
    shadow_cmp = compare(shadow, real)
    payload = {
        "run_mode": "autonomous_replay_then_compare",
        "baseline": {"slots": 3, "margin": 150.0, "timeout": "48h unconditional", "bar_ms": BAR_MS},
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "universe": {"available_symbols": len(available), "executed_symbols": len(symbols), "smoke_limit": args.limit_symbols},
        "coverage": {"real_total": len(real), "measurable": len(measurable), "missing": len(missing), "missing_symbols": [item["symbol"] for item in missing]},
        "base": {"raw_signals": len(raw), "trades": base, "comparison": base_cmp, "summary": summarize(base_cmp, base, len(real), len(measurable))},
        "shadow_missing_coverage": {
            "description": "diagnostic only; seven real no-kline trades reserve a slot until their real close, never used by base replay",
            "trades": shadow, "comparison": shadow_cmp,
            "summary": summarize(shadow_cmp, shadow, len(real), len(measurable)),
        },
    }
    replay.close()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "coverage": payload["coverage"], "base": payload["base"]["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
