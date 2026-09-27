"""Prueba de la máquina (Fase 3, punto 3): controles negativos y positivos sobre velas REALES.

Mide lo que el Gate V4 nunca pudo medir: la tasa de falsos positivos de la máquina.
Usa las mismas velas y la misma matriz/criterio que `lab_diagnose`; solo cambia la población de entradas.

Poblaciones sintéticas (todas con símbolo/instante al azar y geometría SL/TP tomada de señales reales de MA3):
  NULL        lado al azar (moneda). Sin información: ninguna variante debería salir CORREGIBLE-ROBUSTO
              ni la DIRECCION INVERTIDA-ROBUSTA. Cada población NULL es un intento de falso positivo.
  HINDSIGHT   lado = dirección del movimiento de las próximas 24 h (usa el futuro a propósito). Control positivo de
              dirección: la máquina debe decir DIRECCION = CORRECTA.
  ANTI        lado contrario al movimiento de las próximas 24 h. Control positivo de inversión: debe decir
              DIRECCION = INVERTIDA-ROBUSTA.
  GIVEBACK    entradas elegidas con futuro para tener MFE >= 3 % en las primeras 12 h y volver por debajo de la
              entrada a las 48 h; SL/TP anchos (25 %). Ganancia flotante que se devuelve: la máquina debería marcar la
              SALIDA como CORREGIBLE-ROBUSTO (control positivo de salida).
Cada población usa fechas repartidas en TRAIN/VAL/OOS con los mismos cortes que MA3 y N OOS >= 200.

    python /app/backtest/lab_fptest.py --n-null 30 --size 3000 --workers 14
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_core as C  # noqa: E402
from lab_adapters import ma3 as M  # noqa: E402

HOUR = 3_600_000
_ADAPTER = None
_GEOM = None


def _rows(symbol):
    return _ADAPTER.candles(symbol)


def _make_population(kind, size, seed, symbols):
    """Devuelve entradas sintéticas [{open_ms,symbol,entry,side,sl,tp}] usando velas reales.
    Se toman varias entradas por cada símbolo cargado (una sola lectura de velas por visita)."""
    rnd = random.Random(seed)
    out, visits = [], 0
    per_visit_cap = 25
    attempts = 600 if kind == "GIVEBACK" else 40
    while len(out) < size and visits < 4000:
        visits += 1
        sym = rnd.choice(symbols)
        rows = _rows(sym)
        if len(rows) < 800:
            continue
        taken = 0
        for _ in range(attempts):
            if taken >= per_visit_cap or len(out) >= size:
                break
            i = rnd.randrange(300, len(rows) - 600)
            ot, _, _, close = rows[i]
            if not (M.START <= ot < M.END):
                continue
            sl_pct, tp_pct = rnd.choice(_GEOM)  # geometría medida sobre señales reales de MA3
            ret24 = (rows[min(i + 288, len(rows) - 1)][3] - close) / close * 100.0  # próximas 24 h (5m)
            if kind == "NULL":
                side = rnd.randrange(2)
            elif kind == "HINDSIGHT":
                side = 1 if ret24 < 0 else 0            # short si baja, long si sube
            elif kind == "ANTI":
                side = 0 if ret24 < 0 else 1
            elif kind == "GIVEBACK":
                side = 1
                mfe12 = max((close - r[2]) / close * 100.0 for r in rows[i + 1:i + 145])
                end48 = (close - rows[i + 576][3]) / close * 100.0
                if not (mfe12 >= 3.0 and end48 <= 0.0):
                    continue
                sl_pct = tp_pct = 25.0
            else:
                raise ValueError(kind)
            if side == 1:   # short
                sl, tp = close * (1 + sl_pct / 100.0), close * (1 - tp_pct / 100.0)
            else:           # long: geometría espejada
                sl, tp = close * (1 - sl_pct / 100.0), close * (1 + tp_pct / 100.0)
            out.append({"open_ms": ot, "symbol": sym, "entry": close, "side": side, "sl": sl, "tp": tp})
            taken += 1
    return out


def _run_population(item):
    """Corre la matriz completa sobre una población y devuelve veredictos + fracción de variantes que pasan."""
    kind, seed, size, symbols = item
    entries = _make_population(kind, size, seed, symbols)
    a = _ADAPTER
    by_symbol = {}
    for t in entries:
        by_symbol.setdefault(t["symbol"], []).append(t)
    records = []
    for sym, ts in by_symbol.items():
        rows = a.candles(sym)
        opens = [r[0] for r in rows]
        hours = C.hourly_series(rows)
        hst = [h[0] for h in hours]
        for t in ts:
            split = a.split_of(t["open_ms"])
            atr = C.atr_before(hours, hst, t["open_ms"])
            for v in C.ALL_VARIANTS:
                side = C.trade_side(t, v)
                for (mode, bias), key in zip(C.SCENARIOS, C.SCEN_KEYS):
                    px, _ = C.simulate(rows, opens, a.bar_ms, t, v, mode, bias, atr)
                    records.append((split, key, v, C.pct(side, t["entry"], px) - a.cost_pct))
    summary = C.summarize_matrix(records, a.split_names, a.cost_pct)
    n_oos = summary[C.SCEN_KEYS[0]]["baseline"]["n_oos"]
    traj = {"OOS": _traj(entries, a)}
    verd = C.verdicts(summary, traj, n_oos)
    passing = [v for v in C.NON_BASELINE if C.passes_criterion(summary, v)]
    return {"kind": kind, "seed": seed, "n": len(entries), "n_oos": n_oos, "verdicts": verd, "passing": passing,
            "baseline_oos_mean": {k: summary[k]["baseline"]["oos_mean"] for k in C.SCEN_KEYS}}


def _traj(entries, a):
    paths = []
    for t in entries:
        if a.split_of(t["open_ms"]) != "OOS":
            continue
        rows = a.candles(t["symbol"])
        pm = C.path_metrics(rows, [r[0] for r in rows], a.bar_ms, t)
        if pm:
            paths.append(pm)
    if not paths:
        return {}
    return {"mfe_median": C.median([p["mfe"] for p in paths]), "giveback_median": C.median([p["giveback"] for p in paths])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-null", type=int, default=30)
    ap.add_argument("--n-control", type=int, default=3, help="poblaciones por cada control positivo")
    ap.add_argument("--size", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--out", default="/app/backtest/lab_artifacts/lab_fptest/result.json")
    args = ap.parse_args()

    global _ADAPTER, _GEOM
    _ADAPTER = M.MA3Adapter()
    entries = _ADAPTER.entries()
    _GEOM = [(abs(e["sl"] - e["entry"]) / e["entry"] * 100.0, abs(e["entry"] - e["tp"]) / e["entry"] * 100.0)
             for e in entries[::7]]
    symbols = sorted({e["symbol"] for e in entries})
    jobs = [("NULL", args.seed + i, args.size, symbols) for i in range(args.n_null)]
    for kind in ("HINDSIGHT", "ANTI", "GIVEBACK"):
        jobs += [(kind, args.seed + 1000 + i, args.size, symbols) for i in range(args.n_control)]
    t0 = time.time()
    results = []
    with mp.get_context("fork").Pool(args.workers) as pool:
        for r in pool.imap_unordered(_run_population, jobs, chunksize=1):
            results.append(r)
            print(f"[{len(results)}/{len(jobs)}] {r['kind']} n={r['n']} nOOS={r['n_oos']} DIR={r['verdicts']['DIRECCION'][:22]} "
                  f"SALIDA={r['verdicts']['SALIDA'][:22]} pasan={len(r['passing'])}", flush=True)

    def is_fp(r):
        exit_fp = r["verdicts"]["SALIDA"].startswith("CORREGIBLE-ROBUSTO") or r["verdicts"]["SL"].startswith("CORREGIBLE-ROBUSTO")
        dir_fp = r["verdicts"]["DIRECCION"].startswith("INVERTIDA-ROBUSTA")
        return exit_fp or dir_fp

    nulls = [r for r in results if r["kind"] == "NULL"]
    fp = sum(1 for r in nulls if is_fp(r))
    fp_exit = sum(1 for r in nulls if r["verdicts"]["SALIDA"].startswith("CORREGIBLE-ROBUSTO") or r["verdicts"]["SL"].startswith("CORREGIBLE-ROBUSTO"))
    fp_dir = sum(1 for r in nulls if r["verdicts"]["DIRECCION"].startswith("INVERTIDA-ROBUSTA"))
    ctrl = {}
    for kind, want in (("HINDSIGHT", "DIRECCION:CORRECTA"), ("ANTI", "DIRECCION:INVERTIDA-ROBUSTA"), ("GIVEBACK", "SALIDA:CORREGIBLE-ROBUSTO")):
        rs = [r for r in results if r["kind"] == kind]
        comp, label = want.split(":")
        hit = sum(1 for r in rs if r["verdicts"][comp].startswith(label))
        ctrl[kind] = {"populations": len(rs), "detected": hit, "expected": want}
    out = {"label": "Prueba de la máquina sobre velas reales de MA3; poblaciones sintéticas", "size": args.size,
           "n_null": len(nulls), "false_positive": {"any": fp, "exit_or_sl": fp_exit, "direction": fp_dir,
                                                    "rate_any": (fp / len(nulls)) if nulls else None,
                                                    "pass_threshold": 0.05},
           "positive_controls": ctrl, "elapsed_s": round(time.time() - t0, 1), "populations": results}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in ("n_null", "false_positive", "positive_controls", "elapsed_s")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
