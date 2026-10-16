"""Backfill REST reanudable de settlements históricos de Binance USDⓈ-M."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from funding_history import BINANCE_USDM, FundingStore

ENDPOINT = "https://fapi.binance.com/fapi/v1/fundingRate"
PAGE_LIMIT = 1000
REQUEST_INTERVAL_S = 0.7  # < 500 requests / 5 min compartidos


def fetch_page(symbol: str, start_ms: int, end_ms: int, timeout_s: float = 20.0) -> list[dict]:
    query = urlencode({"symbol": symbol, "startTime": start_ms, "endTime": end_ms, "limit": PAGE_LIMIT})
    with urlopen(f"{ENDPOINT}?{query}", timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def backfill_symbol(store: FundingStore, symbol: str, start_ms: int, end_ms: int,
                    fetch=fetch_page, sleep=time.sleep, refresh: bool = False) -> dict:
    cursor = start_ms if refresh else store.begin(BINANCE_USDM, symbol, start_ms, end_ms)
    if refresh:
        store.begin(BINANCE_USDM, symbol, start_ms, end_ms)
    pages = inserted = 0
    # Puede haberse persistido la última página justo antes de un corte del
    # proceso. En ese caso el cursor ya está al final: cerrar el estado sin
    # volver a consultar ni reinsertar nada.
    if cursor > end_ms:
        store.complete(BINANCE_USDM, symbol)
        return {"symbol": symbol, "pages": 0, "events_persisted": 0,
                "coverage": store.coverage_report(BINANCE_USDM, [symbol])[symbol]}
    while cursor <= end_ms:
        try:
            page = fetch(symbol, cursor, end_ms)
        except Exception as exc:
            store.record_error(BINANCE_USDM, symbol, f"{type(exc).__name__}: {exc}")
            raise
        if not page:
            store.complete(BINANCE_USDM, symbol)
            break
        last = int(page[-1]["fundingTime"])
        if last < cursor:
            raise RuntimeError(f"Binance devolvió cursor no creciente para {symbol}: {last} < {cursor}")
        cursor = last + 1
        inserted += store.persist_page(BINANCE_USDM, symbol, page, cursor)
        pages += 1
        sleep(REQUEST_INTERVAL_S)
    return {"symbol": symbol, "pages": pages, "events_persisted": inserted,
            "coverage": store.coverage_report(BINANCE_USDM, [symbol])[symbol]}


def ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    parser.add_argument("--symbols", required=True, nargs="+", help="BTCUSDT ETHUSDT ... (también acepta CSV)")
    parser.add_argument("--start", required=True, help="ISO UTC, e.g. 2025-01-01T00:00:00Z")
    parser.add_argument("--end", default=datetime.now(timezone.utc).isoformat(), help="ISO UTC")
    parser.add_argument("--coverage-output", required=True)
    parser.add_argument("--refresh", action="store_true", help="reconsulta páginas para completar campos nuevos; UPSERT sin duplicados")
    args = parser.parse_args()
    store = FundingStore(args.db) if args.db else FundingStore()
    start, end = ms(args.start), ms(args.end)
    report = {"venue": BINANCE_USDM, "start_ms": start, "end_ms": end, "symbols": {}, "failed": {}}
    symbols = [token.strip().upper() for arg in args.symbols for token in arg.split(",") if token.strip()]
    for symbol in symbols:
        try:
            report["symbols"][symbol] = backfill_symbol(store, symbol, start, end, refresh=args.refresh)
        except Exception as exc:
            report["failed"][symbol] = f"{type(exc).__name__}: {exc}"
    with open(args.coverage_output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    # Windows consoles commonly default to cp1252; retain the UTF-8 JSON file
    # while making the terminal summary safe for every exchange symbol.
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
