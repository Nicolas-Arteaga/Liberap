"""Fase 1: normaliza fuentes de trades sin confiar en PnL legado.

Uso (dentro del contenedor backtest):
  python /app/backtest/fase1_ground_truth.py --output /app/backtest/lab_artifacts/f1-ground-truth.json

No escribe PostgreSQL ni perfiles. Para cada fila PostgreSQL cerrada calcula:
  qty = Size
  gross = qty * (close - entry) [LONG] o qty * (entry - close) [SHORT]
  net = gross - EntryFee - ExitFee - TotalFundingPaid

`scratch_caso3_gt.json` no contiene lado, tamaño ni fees. Se conserva como
ground truth de señal/entrada/salida; cualquier PnL derivado de esa fuente se
etiqueta `modelled`, nunca `exact`.
"""
import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import psycopg2


NAMES = ("MA Slope Caso 3", "Band Touch 15m")
START = "2026-09-13 00:00:00+00"
END = "2026-09-21 00:00:00+00"


def number(value):
    return float(value) if value is not None else None


def normalized_side(value):
    # El esquema actual usa 1 para short y 0 para long; no inferir por PnL.
    if str(value).strip().lower() in {"1", "short", "sell"}:
        return "SHORT"
    if str(value).strip().lower() in {"0", "long", "buy"}:
        return "LONG"
    return None


def recalc_pnl(row):
    entry, close, size = row["entry_price"], row["close_price"], row["size"]
    side = row["side"]
    if None in (entry, close, size, side):
        return None
    gross = size * (close - entry) if side == "LONG" else size * (entry - close)
    fees = (row["entry_fee"] or 0.0) + (row["exit_fee"] or 0.0)
    funding = row["funding"] or 0.0
    return gross - fees - funding


def fetch_postgres():
    conn = psycopg2.connect(
        host=os.getenv("VERGE_DB_HOST", "db"),
        port=int(os.getenv("VERGE_DB_PORT", "5432")),
        user=os.getenv("VERGE_DB_USER", "postgres"),
        password=os.getenv("VERGE_DB_PASSWORD", "postgres"),
        dbname=os.getenv("VERGE_DB_NAME", "Verge"),
    )
    sql = '''
        SELECT sp."Name", st."Id", st."Symbol", st."Side", st."Size",
               st."EntryPrice", st."ClosePrice", st."EntryFee", st."ExitFee",
               st."TotalFundingPaid", st."OpenedAt", st."ClosedAt", st."ExitReason"
        FROM "SimulatedTrades" st
        JOIN "StrategyProfiles" sp ON sp."Id" = st."StrategyProfileId"
        WHERE sp."Name" = ANY(%s)
          AND st."OpenedAt" >= %s::timestamptz
          AND st."OpenedAt" < %s::timestamptz
        ORDER BY sp."Name", st."OpenedAt", st."Id"
    '''
    with conn, conn.cursor() as cur:
        cur.execute(sql, (list(NAMES), START, END))
        data = cur.fetchall()
    conn.close()
    out = []
    for values in data:
        (strategy, identifier, symbol, side, size, entry, close, entry_fee, exit_fee,
         funding, opened, closed, reason) = values
        row = {
            "strategy": strategy, "id": str(identifier), "symbol": symbol,
            "side": normalized_side(side), "size": number(size),
            "entry_price": number(entry), "close_price": number(close),
            "entry_fee": number(entry_fee), "exit_fee": number(exit_fee),
            "funding": number(funding), "opened_at": opened.isoformat() if opened else None,
            "closed_at": closed.isoformat() if closed else None, "exit_reason": reason,
        }
        row["pnl_recalculated"] = recalc_pnl(row)
        row["pnl_provenance"] = "exact_from_prices_size_fees_funding" if row["pnl_recalculated"] is not None else "not_usable"
        out.append(row)
    return out


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["strategy"]].append(row)
    result = {}
    for name in NAMES:
        group = grouped[name]
        usable = [row for row in group if row["pnl_recalculated"] is not None]
        result[name] = {
            "rows": len(group),
            "signal_entry_usable": sum(row["side"] is not None and row["entry_price"] is not None for row in group),
            "pnl_recalculation_usable": len(usable),
            "missing_close": sum(row["close_price"] is None for row in group),
            "net_pnl_recalculated": round(sum(row["pnl_recalculated"] for row in usable), 8),
            "exit_reasons": dict(Counter(row["exit_reason"] or "NULL" for row in usable)),
        }
    return result


def scratch_caso3(path):
    with open(path, encoding="utf-8") as handle:
        trades = json.load(handle)
    usable_signal_entry_exit = sum(
        all(item.get(key) is not None for key in ("sym", "open_utc", "close_utc", "entry", "exit_px"))
        for item in trades
    )
    return {
        "rows": len(trades),
        "signal_entry_exit_usable": usable_signal_entry_exit,
        "exact_pnl_recalculation_usable": 0,
        "reason_exact_pnl_unusable": "source lacks side, size and fees; legacy pnl/result_csv intentionally excluded",
        "source_fields": sorted(trades[0].keys()) if trades else [],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--scratch", required=True,
                        help="Ruta al scratch_caso3_gt.json dentro del entorno ejecutor.")
    args = parser.parse_args()
    rows = fetch_postgres()
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_utc": {"start": START, "end_exclusive": END},
        "formula": {
            "long_gross": "Size * (ClosePrice - EntryPrice)",
            "short_gross": "Size * (EntryPrice - ClosePrice)",
            "net": "gross - EntryFee - ExitFee - TotalFundingPaid",
        },
        "scratch_caso3": scratch_caso3(args.scratch),
        "postgres": {"summary": summarize(rows), "trades": rows},
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "scratch": output["scratch_caso3"], "postgres": output["postgres"]["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
