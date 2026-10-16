"""Materializa FVG-15m de producción como candidato formal del Research Loop.

No consulta API ni servidor: ``BacktestEngine`` inyecta la caché SQLite en
``FvgAnalyzer`` y conserva el detector puro ``detect_fvgs``, selección global
Top-5, ``validate_pre_trade`` y el constructor FVG de producción.  Los exits
del replay sólo sirven para que el selector global respete una posición abierta
por símbolo; las filas formalizadas contienen exclusivamente la decisión de
entrada y SL/TP existentes al abrir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from backtest.engine import BacktestEngine
from backtest.lab_adapters.level_sweep import TOP_40_SYMBOLS
from backtest.research_loop import materialize_candidate, diagnose_revision, verify_revision

PROFILE = {
    "id": "93f8dbe7-5bbf-4810-99e6-a08145a6e93d", "name": "FVG - 15m",
    "strategyType": "FVG", "allowLong": True, "allowShort": True,
    "tpMultiplier": 3, "slMultiplier": 0.8, "minRR": 3,
    "marginPerTrade": 150, "maxOpenPositions": 3, "maxTradeDurationCandles": 60,
    "minConfluenceScore": 80, "minNexusConfidence": 50,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False,
                                      "minExhaustionSlopeDeg": 3}),
}

RULE = (
    "FVG 15m productivo: gap de tres velas detect_fvgs, zona activa IN_ZONE/APPROACHING "
    "y alineada EMA25/EMA50; corte global Top-5 por tp_distance_pct, validate_pre_trade "
    "y risk_manager productivos. Entrada al tick de scan de 5m aprobado; SL=zona ±15% "
    "del gap; TP=objetivo de liquidez estructural productivo."
)


def _entries(all_trades):
    # ``all_trades`` son sólo aperturas aceptadas por el replay productivo.
    dedup = {}
    for trade in all_trades:
        row = {key: trade[key] for key in ("open_time", "symbol", "entry", "side", "sl", "tp")}
        key = (row["open_time"], row["symbol"], row["side"])
        dedup[key] = {"open_ms": int(row.pop("open_time")), **row}
    return sorted(dedup.values(), key=lambda item: (item["open_ms"], item["symbol"], item["side"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(HERE / "research_loop"))
    parser.add_argument("--candidate-id", default="fvg15m-production-formal-20261009")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--universe", choices=("top40", "all"), default="top40")
    parser.add_argument("--scan-step-ticks", type=int, choices=(1, 3), default=3,
                        help="1=fidelidad 5m; 3=scan 15m documentado por engine.run_fvg_global")
    parser.add_argument("--db", default=os.environ.get("LAB_CANONICAL_DB", str(HERE.parent / "data" / "binance_vision_clean.db")))
    # El backfill y la validación documental aprobada viven en este store.
    # ``klines.db`` fue un nombre heredado: crea una base vacía y por eso el
    # gate no veía la validación ``binance_official_docs_example`` ya persistida.
    parser.add_argument("--funding-db", default=str(HERE.parent / "data" / "funding_history.db"))
    args = parser.parse_args()
    engine = BacktestEngine(args.db)
    symbols = engine.top40_symbols() if args.universe == "top40" else engine.available_symbols()
    # La DB de investigación es un snapshot, no un feed vivo. Anclar al último
    # 5m cubierto evita construir una ventana futura vacía cuando el snapshot
    # termina antes del reloj del sistema.
    end_row = engine.conn.execute("SELECT MAX(open_time) FROM klines_5m WHERE interval='5m'").fetchone()
    if not end_row or end_row[0] is None:
        raise SystemExit("sin cobertura 5m histórica para materializar FVG")
    end_ms = int(end_row[0]) + 5 * 60 * 1000
    start_ms = end_ms - args.days * 24 * 60 * 60 * 1000
    end_iso = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).date().isoformat()
    print(f"FVG formal: {len(symbols)} símbolos, {args.days} días hasta {end_iso}, selector global productivo", flush=True)
    result = engine.run_fvg_global(PROFILE, symbols, start_ms, end_ms, scan_step_ticks=args.scan_step_ticks,
                                   progress_cb=lambda done,total: print(f"scan {done}/{total}", flush=True) if done % 500 == 0 or done == total else None)
    entries = _entries(result["all_signals_raw"])
    if not entries:
        raise SystemExit("FVG no produjo entradas aceptadas; no se materializa candidato vacío.")
    root = Path(args.root)
    execution_time = ("tick productivo de 5m" if args.scan_step_ticks == 1 else
                      "scan histórico documentado cada 15m (scan_step_ticks=3)")
    condition = RULE + f" Materialización: {execution_time}."
    materialize_candidate(
        root, "fvg_production", args.candidate_id, entries, condition, "FVG 15m — producción formal",
        research_run={"run_id": "fvg-production-replay-global", "family": "structural_fvg",
                      "hypothesis": condition, "source_commit": os.environ.get("RESEARCH_SOURCE_COMMIT", "worktree"),
                      "scan_step_ticks": args.scan_step_ticks},
        entry_source="FvgAnalyzer/detect_fvgs puro con HistoricalFetcher SQLite; sin API ni servidor en vivo.",
    )
    revision = root / args.candidate_id / "1"
    _candidate, _rows, hashes = verify_revision(revision)
    print(json.dumps({"entries": len(entries), "replay": {k: result.get(k) for k in ("total_signals", "accepted_trades", "win_rate_pct", "total_pnl_usdt")}, "hashes": hashes}, ensure_ascii=False), flush=True)
    diagnosis = diagnose_revision(root, revision, funding_db=args.funding_db)
    print(json.dumps({"diagnosis": diagnosis["diagnosis"], "integrity": diagnosis["integrity"], "funding": diagnosis.get("funding")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
