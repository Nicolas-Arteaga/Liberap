"""
Analiza trade_metrics.jsonl y propone (o aplica) ajustes conservadores a parámetros del agente.

Uso:
  python auto_tuner.py
  python auto_tuner.py --apply
  python auto_tuner.py --window 100 --min-trades 40

Sin ML: estadística por buckets (RR, MA99, reward). No ajusta con < min_trades cerrados.
Los overrides aplicables los escribe en data/auto_tuner_overrides.json (--apply).
El agente los carga al importar config si sample_size es suficiente.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import config
from trade_analytics import load_jsonl, pair_open_close

# Defaults conservadores (alineados con la conversación)
DEFAULT_MIN_TRADES = 30
DEFAULT_WINDOW = 100
RR_STEP = 0.1
RR_CAP = 2.5
TP_PCT_STEP = 0.0005
TP_PCT_CAP = 0.006


def _parse_ts(row: Dict[str, Any]) -> float:
    ts = row.get("ts_utc") or row.get("captured_at_utc")
    if not ts:
        return 0.0
    try:
        s = str(ts).replace("Z", "+00:00")
        if "T" not in s:
            return 0.0
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def merged_closed_trades(
    path: str,
    window: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Últimos `window` trades cerrados con WIN/LOSS, ordenados del más reciente al más viejo."""
    events = load_jsonl(path)
    merged = pair_open_close(events)
    rows: List[Dict[str, Any]] = []
    for tid, row in merged.items():
        if row.get("agent_version") != "risk_v2.0":
            continue
        res = str(row.get("result") or "").upper()
        if res not in ("WIN", "LOSS"):
            continue
        rows.append(dict(row))

    rows.sort(key=_parse_ts, reverse=True)
    total_available = len(rows)
    if window > 0:
        rows = rows[:window]
    return rows, total_available


def _winrate(sub: List[Dict[str, Any]]) -> float:
    if not sub:
        return 0.0
    w = sum(1 for r in sub if str(r.get("result") or "").upper() == "WIN")
    return w / len(sub)


def _bucket_rr(rr: Optional[float]) -> str:
    if rr is None:
        return "unknown"
    try:
        x = float(rr)
    except (TypeError, ValueError):
        return "unknown"
    if x < 1.5:
        return "lt_1_5"
    if x < 2.0:
        return "1_5_to_2"
    return "ge_2"


def analyze_rr_threshold(rows: List[Dict[str, Any]], current_min_rr: float) -> Tuple[Optional[float], str]:
    """
    Si el bucket RR bajo pierde claramente vs alto, subir MIN_RR_DEFAULT un paso.
    """
    by_b: Dict[str, List[Dict[str, Any]]] = {"lt_1_5": [], "1_5_to_2": [], "ge_2": [], "unknown": []}
    for r in rows:
        rr = r.get("rr")
        try:
            rr_f = float(rr) if rr is not None else None
        except (TypeError, ValueError):
            rr_f = None
        by_b[_bucket_rr(rr_f)].append(r)

    low = by_b["lt_1_5"]
    hi = by_b["ge_2"]
    wr_lo = _winrate(low)
    wr_hi = _winrate(hi)

    if len(low) < 5 or len(hi) < 5:
        return None, f"RR buckets: low n={len(low)} high n={len(hi)} (mínimo 5 por bucket para sugerir)"

    if wr_hi > wr_lo + 0.08:
        new_rr = min(current_min_rr + RR_STEP, RR_CAP)
        return new_rr, (
            f"winrate(ge_2)={wr_hi:.2f} vs winrate(<1.5)={wr_lo:.2f} → subir MIN_RR_DEFAULT "
            f"{current_min_rr} → {new_rr}"
        )
    return None, f"RR buckets estables: wr(<1.5)={wr_lo:.2f} wr(≥2)={wr_hi:.2f}"


def analyze_tp_distance(rows: List[Dict[str, Any]], current_pct: float) -> Tuple[Optional[float], str]:
    """Si reward_abs bajo correlaciona con más pérdidas, subir MIN_TP_DISTANCE_PCT_OF_PRICE."""
    vals: List[Tuple[float, bool]] = []
    for r in rows:
        try:
            rw = float(r.get("reward_abs") or 0)
        except (TypeError, ValueError):
            continue
        if rw <= 0:
            continue
        win = str(r.get("result") or "").upper() == "WIN"
        vals.append((rw, win))

    if len(vals) < 15:
        return None, "pocos trades con reward_abs para TP"

    vals.sort(key=lambda x: x[0])
    mid = len(vals) // 2
    low_half = vals[:mid]
    hi_half = vals[mid:]
    wins_l = sum(1 for _, w in low_half if w)
    wins_h = sum(1 for _, w in hi_half if w)
    wr_l = wins_l / len(low_half) if low_half else 0.0
    wr_h = wins_h / len(hi_half) if hi_half else 0.0

    if wr_h > wr_l + 0.1:
        new_pct = min(current_pct + TP_PCT_STEP, TP_PCT_CAP)
        return new_pct, (
            f"reward_abs bajo pierde más (wr_low={wr_l:.2f} vs wr_high={wr_h:.2f}) → "
            f"MIN_TP_DISTANCE_PCT_OF_PRICE {current_pct} → {new_pct}"
        )
    return None, f"reward quartiles: wr_low={wr_l:.2f} wr_high={wr_h:.2f}"


def analyze_ma99(rows: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Solo recomendación (no hay override en config hasta implementar filtro)."""
    near: List[Dict[str, Any]] = []
    far: List[Dict[str, Any]] = []
    for r in rows:
        try:
            d = float(r.get("distance_to_ma99_pct"))
        except (TypeError, ValueError):
            continue
        if abs(d) < 1.0:
            near.append(r)
        else:
            far.append(r)

    if len(near) < 8 or len(far) < 8:
        return False, f"MA99: near n={len(near)} far n={len(far)} (mín. 8 cada uno para recomendar)"

    wr_n = _winrate(near)
    wr_f = _winrate(far)
    if wr_f > wr_n + 0.07:
        return True, (
            f"winrate lejos MA99={wr_f:.2f} vs cerca={wr_n:.2f} → "
            "considerar filtro min |distance_to_ma99_pct| (pendiente en validator)"
        )
    return False, f"MA99: wr_near={wr_n:.2f} wr_far={wr_f:.2f}"


def source_split(rows: List[Dict[str, Any]]) -> str:
    srcs: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        s = str(r.get("source") or "Nexus")
        srcs.setdefault(s, []).append(r)
    parts = []
    for s, lst in sorted(srcs.items(), key=lambda x: -len(x[1])):
        wr = _winrate(lst)
        parts.append(f"{s}: n={len(lst)} wr={wr:.2f}")
    return " | ".join(parts) if parts else "sin source"


def build_recommendations(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    cur_rr = float(getattr(config, "MIN_RR_DEFAULT", 1.5))
    cur_tp_pct = float(getattr(config, "MIN_TP_DISTANCE_PCT_OF_PRICE", 0.003))

    rr_new, rr_note = analyze_rr_threshold(rows, cur_rr)
    tp_new, tp_note = analyze_tp_distance(rows, cur_tp_pct)
    ma99_use, ma99_note = analyze_ma99(rows)

    overrides: Dict[str, Any] = {}
    notes: List[str] = []

    if rr_new is not None:
        overrides["MIN_RR_DEFAULT"] = round(rr_new, 4)
        notes.append(rr_note)
    else:
        notes.append(rr_note)

    if tp_new is not None:
        overrides["MIN_TP_DISTANCE_PCT_OF_PRICE"] = round(tp_new, 6)
        notes.append(tp_note)
    else:
        notes.append(tp_note)

    notes.append(ma99_note)
    if ma99_use:
        notes.append("(!) MA99: revisar implementación de filtro en setup_validator si querés automatizar")

    return {
        "version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "jsonl_path": getattr(config, "TRADE_METRICS_JSONL", ""),
        "trades_in_analysis": len(rows),
        "total_closed_in_window": total_in_window,
        "source_distribution": source_split(rows),
        "notes": notes,
        "suggested_overrides": overrides,
        "ma99_filter_recommended": ma99_use,
    }


def run_tuner(
    min_trades: int,
    window: int,
    apply_file: bool,
) -> int:
    path = getattr(config, "TRADE_METRICS_JSONL", "")
    rows, total_avail = merged_closed_trades(path, window)

    rep_path = getattr(config, "AUTO_TUNER_RECOMMENDATIONS_FILE", "")
    out_path = getattr(config, "AUTO_TUNER_OVERRIDES_FILE", "")

    if len(rows) < min_trades:
        msg = (
            f"Trades cerrados insuficientes: {len(rows)} < {min_trades} "
            f"(ventana={window}, disponibles tras merge={total_avail})"
        )
        print(msg)
        payload = {
            "version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "insufficient_data",
            "message": msg,
            "trades_used": len(rows),
            "min_trades_required": min_trades,
        }
        if rep_path:
            try:
                with open(rep_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                print(f"Escrito: {rep_path}")
            except Exception as e:
                print(f"No se pudo escribir recommendations: {e}")
        return 1

    rec = build_recommendations(rows)
    rec["min_trades_required"] = min_trades
    rec["window"] = window

    print("=== Auto-tuner ===")
    print(f"Trades analizados: {len(rows)} (ventana últimos {window})")
    print(f"Distribución: {rec['source_distribution']}")
    for n in rec["notes"]:
        print(f"  · {n}")
    print(f"Sugerencias override: {rec['suggested_overrides']}")

    if rep_path:
        try:
            with open(rep_path, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2, ensure_ascii=False)
            print(f"\nRecomendaciones: {rep_path}")
        except Exception as e:
            print(f"Error escribiendo recommendations: {e}")

    if apply_file and rec.get("suggested_overrides"):
        payload = {
            "version": 1,
            "generated_at_utc": rec["generated_at_utc"],
            "sample_size": len(rows),
            "min_trades_required": min_trades,
            "window": window,
            "rules_fired": [k for k in rec["suggested_overrides"]],
            "overrides": rec["suggested_overrides"],
        }
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"Overrides aplicables escritos: {out_path}")
            print("Reiniciá el agente para cargar cambios vía config.")
        except Exception as e:
            print(f"Error escribiendo overrides: {e}")
            return 1
    elif apply_file:
        print("--apply sin cambios sugeridos: no se escribe auto_tuner_overrides.json")

    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto-tuner desde trade_metrics.jsonl")
    ap.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Escribir auto_tuner_overrides.json si hay sugerencias",
    )
    args = ap.parse_args()
    raise SystemExit(run_tuner(args.min_trades, args.window, args.apply))


if __name__ == "__main__":
    main()
