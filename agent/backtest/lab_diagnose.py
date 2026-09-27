"""CLI de la máquina de diagnóstico de estrategias (Fase 3).

    python -m backtest.lab_diagnose --strategy ma3            # dentro del contenedor: /app/backtest
    python /app/backtest/lab_diagnose.py --strategy band_touch
    python /app/backtest/lab_diagnose.py --strategy ma3 --selftest

Corre la MISMA matriz fija sobre cualquier estrategia con adaptador: dirección invertida, TP corto,
giveback 10/25/50, break-even, trailing, salidas por tiempo, time-stop y SL por ATR, en 4 escenarios
(timeout incondicional/condicional × sesgo de fill TP ±2 pp), con splits TRAIN/VAL/OOS fijos,
prueba sin top-3 y chequeo de regresión. Escribe result.json + progress.json y muestra ≤40 líneas.
La salida por señal opuesta (B) todavía NO está en la matriz: figura como PENDIENTE.
Todo es HIPÓTESIS sobre la población del adaptador; no es la performance esperada en vivo.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_core as C  # noqa: E402
from lab_adapters import get_adapter  # noqa: E402

_ADAPTER = None
HERE = os.path.dirname(os.path.abspath(__file__))
FIDELITY_JSON = os.path.join(HERE, "lab_fidelity.json")


def _task(item):
    symbol, entries = item
    a = _ADAPTER
    rows = a.candles(symbol)
    out = {"symbol": symbol, "records": [], "paths": [], "skipped": 0, "nodata": 0, "done": len(entries)}
    if len(rows) < 2:
        out["skipped"] = len(entries)
        return out
    opens = [r[0] for r in rows]
    hours = C.hourly_series(rows)
    hstarts = [h[0] for h in hours]
    for t in entries:
        if getattr(a, "require_coverage", False) and not (opens[0] <= t["open_ms"] <= opens[-1] - 2 * a.bar_ms):
            out["skipped"] += 1
            continue
        split = a.split_of(t["open_ms"])
        atr = C.atr_before(hours, hstarts, t["open_ms"])
        pm = C.path_metrics(rows, opens, a.bar_ms, t)
        if pm:
            out["paths"].append((split, pm))
        for variant in C.ALL_VARIANTS:
            side = C.trade_side(t, variant)
            for (mode, bias), key in zip(C.SCENARIOS, C.SCEN_KEYS):
                px, reason = C.simulate(rows, opens, a.bar_ms, t, variant, mode, bias, atr)
                if reason == "nodata":
                    out["nodata"] += 1
                out["records"].append((split, key, variant, C.pct(side, t["entry"], px) - a.cost_pct))
    return out


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as h:
        json.dump(obj, h, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _traj_summary(paths, split_names):
    out = {}
    for sp in split_names:
        rows = [p for s, p in paths if s == sp]
        if not rows:
            out[sp] = {"n": 0}
            continue
        d = {"n": len(rows), "mfe_median": C.median([r["mfe"] for r in rows]), "mfe_mean": C.mean([r["mfe"] for r in rows]),
             "mae_median": C.median([r["mae"] for r in rows]), "giveback_median": C.median([r["giveback"] for r in rows]),
             "giveback_mean": C.mean([r["giveback"] for r in rows]), "t_mfe_median_h": C.median([r["t_mfe_h"] for r in rows]),
             "censored_pct": 100.0 * sum(1 for r in rows if r["censored"]) / len(rows)}
        for th in (2, 5):
            reached = [r for r in rows if r["mfe"] >= th]
            d[f"mfe>={th}%"] = {"n": len(reached), "gave_back_ge50pct": sum(1 for r in reached if r["giveback"] >= 0.5 * r["mfe"]),
                                "censored": sum(1 for r in reached if r["censored"])}
        out[sp] = d
    return out


def _print_summary(res):
    L = []
    a, meta, fid = res["adapter"], res["meta"], res["fidelity"]
    L.append(f"== DIAGNÓSTICO {a['name']} | población {a['population']} | N={meta['n_entries']} "
             f"(OOS={meta['n_oos']}) | {res['id']}")
    if fid:
        L.append(f"Fidelidad del motor: detección {fid['detection']}, motivo de salida {fid['exit_reason_match']}, "
                 f"retorno {fid['return_within_tol']}; selección/timeouts: {fid['selection']}")
    reg = res["regression"]
    L.append(f"Regresión baseline: {'OK' if reg['ok'] else ('NO APLICA' if reg['ok'] is None else 'FALLÓ -> CORRIDA INVÁLIDA')}")
    t = res["trajectory"].get("OOS") or {}
    if t.get("n"):
        L.append(f"Trayectoria OOS (48 h, n={t['n']}): MFE mediana {t['mfe_median']:.2f}% | giveback mediana {t['giveback_median']:.2f}% "
                 f"| MAE mediana {t['mae_median']:.2f}% | tiempo a MFE {t['t_mfe_median_h']:.1f} h | censurados {t['censored_pct']:.0f}%")
    L.append("Matriz  (ΔOOS vs baseline, pp; orden: incond-2 | incond+2 | cond-2 | cond+2)   pasa?")
    for v in C.NON_BASELINE:
        ds = [res["summary"][s][v]["delta_vs_baseline"].get("OOS") for s in C.SCEN_KEYS]
        cells = " ".join(f"{d:+.3f}" if d is not None else "  n/a " for d in ds)
        L.append(f"  {v:24s} {cells}   {'SI' if res['passes'][v] else 'no'}")
    L.append("  salida_por_senal_opuesta (B)  PENDIENTE (no implementada en la matriz)")
    L.append("Veredicto por componente:")
    for k, v in res["verdicts"].items():
        L.append(f"  {k:9s}: {v}")
    L.append(f"Hipótesis en esta corrida: {len(C.NON_BASELINE)} variantes (acumulado del proyecto: 30 + las de esta matriz repetidas). "
             "Todo es HIPÓTESIS.")
    print("\n".join(L[:40]))


def selftest(adapter, n=300):
    """Compara el simulador unificado contra las implementaciones de Fase 2/2b (solo MA3)."""
    import fase2_ma3_broad_matrix as m
    import fase2b_ma3_exit_variants as m2
    entries = adapter.entries()
    step = max(1, len(entries) // n)
    sample = entries[::step][:n]
    old_variants = ("baseline", "tp_short_50", "giveback_10", "giveback_25", "giveback_50", "break_even_1r", "trailing_2r")
    new_variants = C.SL_VARIANTS + ("time_exit_12h", "time_exit_24h", "time_exit_36h", "time_stop_24h_if_losing")
    total = bad = 0
    detail = {}
    for t in sample:
        rows = adapter.candles(t["symbol"])
        opens = [r[0] for r in rows]
        hours = C.hourly_series(rows)
        atr = C.atr_before(hours, [h[0] for h in hours], t["open_ms"])
        for (mode, bias) in C.SCENARIOS:
            checks = []
            for v in old_variants:
                ref = m.exit_trade(rows, t, v, mode, bias)
                checks.append((v, ref[0], ref[1]))
            for v in new_variants:
                ref = m2.exit_new(rows, opens, t, v, mode, bias, atr)
                checks.append((v, ref[0], ref[1]))
            mirror = {**t, "side": 1 - t["side"], "sl": 2 * t["entry"] - t["sl"], "tp": 2 * t["entry"] - t["tp"]}
            ref = m.exit_trade(rows, mirror, "baseline", mode, bias)
            checks.append(("inverted", ref[0], ref[1]))
            for v, px, reason in checks:
                got = C.simulate(rows, opens, adapter.bar_ms, t, v, mode, bias, atr)
                total += 1
                if abs(got[0] - px) > 1e-12 or got[1] != reason:
                    bad += 1
                    detail[v] = detail.get(v, 0) + 1
    print(json.dumps({"selftest_total": total, "selftest_mismatch": bad, "by_variant": detail}))
    return bad == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--limit", type=int, help="humo: usa ~N entradas repartidas (invalida el chequeo de regresión)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    global _ADAPTER
    _ADAPTER = adapter = get_adapter(args.strategy)
    if args.selftest:
        sys.exit(0 if selftest(adapter) else 3)

    run_id = f"{adapter.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = args.out_dir or f"/app/backtest/lab_artifacts/lab_diagnose/{run_id}"
    progress = {"id": run_id, "strategy": adapter.name, "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "done": 0, "total": 0, "exit_code": None}
    entries = adapter.entries()
    if args.limit:
        entries = entries[::max(1, len(entries) // args.limit)][:args.limit]
    by_symbol = {}
    for t in entries:
        by_symbol.setdefault(t["symbol"], []).append(t)
    items = sorted(by_symbol.items(), key=lambda kv: -len(kv[1]))
    progress["total"] = len(entries)
    _write_json(os.path.join(out_dir, "progress.json"), progress)

    records, paths, skipped, nodata, done = [], [], 0, 0, 0
    t0 = time.time()
    ctx = mp.get_context("fork")
    with ctx.Pool(args.workers) as pool:
        for res in pool.imap_unordered(_task, items, chunksize=1):
            records.extend(res["records"])
            paths.extend(res["paths"])
            skipped += res["skipped"]
            nodata += res["nodata"]
            done += res["done"]
            progress.update({"done": done, "updated_at_utc": datetime.now(timezone.utc).isoformat()})
            _write_json(os.path.join(out_dir, "progress.json"), progress)

    split_names = adapter.split_names
    summary = C.summarize_matrix(records, split_names, adapter.cost_pct)
    traj = _traj_summary(paths, split_names)
    n_oos = summary[C.SCEN_KEYS[0]]["baseline"]["n_oos"]
    passes = {v: C.passes_criterion(summary, v) for v in C.NON_BASELINE}
    verd = C.verdicts(summary, traj, n_oos)

    reg = {"ok": None, "checks": {}}
    if adapter.expected_baseline and not args.limit:
        ok = True
        for key, expected in adapter.expected_baseline.items():
            got = summary[key]["baseline"]["oos_mean"]
            good = got is not None and abs(got - expected) < adapter.baseline_scenario_tol
            reg["checks"][key] = {"expected": expected, "got": got, "ok": good}
            ok = ok and good
        reg["ok"] = ok
    fid = json.load(open(FIDELITY_JSON, encoding="utf-8")) if os.path.exists(FIDELITY_JSON) else None
    result = {"id": run_id, "adapter": adapter.describe(), "label": "HIPOTESIS: población del adaptador, no la performance esperada en vivo",
              "meta": {"n_entries": len(entries), "n_oos": n_oos, "skipped_uncovered": skipped, "nodata_sims": nodata,
                       "elapsed_s": round(time.time() - t0, 1), "limit": args.limit, "workers": args.workers,
                       "variants_tested": len(C.NON_BASELINE)},
              "fidelity": (fid or {}).get(adapter.name) or (fid or {}).get("default"),
              "regression": reg, "trajectory": traj, "summary": summary, "passes": passes, "verdicts": verd}
    invalid = reg["ok"] is False
    if invalid:
        result["verdicts"] = {"TODOS": "CORRIDA INVALIDADA: el baseline no reproduce el valor congelado"}
    _write_json(os.path.join(out_dir, "result.json"), result)
    progress.update({"status": "failed" if invalid else "completed", "exit_code": 3 if invalid else 0,
                     "finished_at_utc": datetime.now(timezone.utc).isoformat(), "result": os.path.join(out_dir, "result.json")})
    _write_json(os.path.join(out_dir, "progress.json"), progress)
    _print_summary(result)
    print(f"resultado: {os.path.join(out_dir, 'result.json')}")
    sys.exit(3 if invalid else 0)


if __name__ == "__main__":
    main()
