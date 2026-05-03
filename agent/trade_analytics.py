"""
Agrega métricas guardadas en trade_metrics.jsonl (eventos open/close).
Uso: python trade_analytics.py   o importar winrate_by_rr_bucket(rows).

Requiere que los eventos `open` incluyan `rr` (LSE) y `close` incluyan `result`.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

import config


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def pair_open_close(events: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Une phase=open y phase=close por trade_id."""
    opens: Dict[str, Dict[str, Any]] = {}
    merged: Dict[str, Dict[str, Any]] = {}
    for e in events:
        tid = e.get("trade_id")
        if not tid:
            continue
        ph = e.get("phase")
        if ph == "open":
            opens[tid] = dict(e)
        elif ph == "close":
            base = opens.pop(tid, {})
            merged[tid] = {**base, **e}
    return merged


def _rr_bucket(rr: float | None) -> str:
    if rr is None:
        return "unknown"
    if rr < 1.5:
        return "<1.5"
    if rr < 2.0:
        return "1.5–2"
    if rr < 3.0:
        return "2–3"
    return ">3"


def _atr_bucket(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio < 1.0:
        return "<1"
    if ratio < 1.7:
        return "1–1.7"
    return ">1.7"


def winrate_by_rr_bucket(merged: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Lista de (bucket, texto resumen)."""
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0})
    for row in merged.values():
        res = str(row.get("result") or "").upper()
        if res not in ("WIN", "LOSS"):
            continue
        try:
            rr = float(row.get("rr")) if row.get("rr") is not None else None
        except (TypeError, ValueError):
            rr = None
        b = _rr_bucket(rr)
        if res == "WIN":
            stats[b]["w"] += 1
        else:
            stats[b]["l"] += 1

    lines: List[Tuple[str, str]] = []
    order = ["<1.5", "1.5–2", "2–3", ">3", "unknown"]
    for b in order:
        if b not in stats:
            continue
        w, el = stats[b]["w"], stats[b]["l"]
        tot = w + el
        if tot == 0:
            continue
        wr = 100.0 * w / tot
        lines.append((b, f"RR {b}: {wr:.0f}% win ({w}W/{el}L, n={tot})"))
    return lines


def winrate_by_atr_bucket(merged: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0})
    for row in merged.values():
        res = str(row.get("result") or "").upper()
        if res not in ("WIN", "LOSS"):
            continue
        try:
            ar = float(row["atr_ratio"]) if row.get("atr_ratio") is not None else None
        except (TypeError, ValueError):
            ar = None
        b = _atr_bucket(ar)
        if res == "WIN":
            stats[b]["w"] += 1
        else:
            stats[b]["l"] += 1

    lines: List[Tuple[str, str]] = []
    order = ["<1", "1–1.7", ">1.7", "unknown"]
    for b in order:
        if b not in stats:
            continue
        w, el = stats[b]["w"], stats[b]["l"]
        tot = w + el
        if tot == 0:
            continue
        wr = 100.0 * w / tot
        lines.append((b, f"ATR ratio {b}: {wr:.0f}% win ({w}W/{el}L, n={tot})"))
    return lines


def _ma99_dist_bucket(pct: float | None) -> str:
    if pct is None:
        return "unknown"
    if pct < -5:
        return "<-5%"
    if pct < 0:
        return "-5–0%"
    if pct < 2:
        return "0–2%"
    if pct < 5:
        return "2–5%"
    return ">5%"


def winrate_by_ma99_distance_bucket(merged: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    """distance_to_ma99_pct en apertura (precio señal vs MA99)."""
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0})
    for row in merged.values():
        res = str(row.get("result") or "").upper()
        if res not in ("WIN", "LOSS"):
            continue
        try:
            d = float(row["distance_to_ma99_pct"]) if row.get("distance_to_ma99_pct") is not None else None
        except (TypeError, ValueError):
            d = None
        b = _ma99_dist_bucket(d)
        if res == "WIN":
            stats[b]["w"] += 1
        else:
            stats[b]["l"] += 1

    lines: List[Tuple[str, str]] = []
    order = ["<-5%", "-5–0%", "0–2%", "2–5%", ">5%", "unknown"]
    for b in order:
        if b not in stats:
            continue
        w, el = stats[b]["w"], stats[b]["l"]
        tot = w + el
        if tot == 0:
            continue
        wr = 100.0 * w / tot
        lines.append((b, f"dist→MA99 {b}: {wr:.0f}% win ({w}W/{el}L, n={tot})"))
    return lines


def print_report(path: str | None = None) -> None:
    p = path or getattr(config, "TRADE_METRICS_JSONL", "")
    events = load_jsonl(p)
    merged = pair_open_close(events)
    print(f"=== trade_analytics ({p}) ===")
    print(f"Pares open+close: {len(merged)}\n")
    for _, line in winrate_by_rr_bucket(merged):
        print(line)
    print()
    for _, line in winrate_by_atr_bucket(merged):
        print(line)
    print()
    for _, line in winrate_by_ma99_distance_bucket(merged):
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Winrate por buckets desde trade_metrics.jsonl")
    ap.add_argument(
        "jsonl",
        nargs="?",
        default=None,
        help="Ruta al JSONL (default: config.TRADE_METRICS_JSONL)",
    )
    args = ap.parse_args()
    print_report(args.jsonl)
