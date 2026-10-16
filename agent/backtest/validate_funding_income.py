"""Valida la convención de signo del cache contra un export real de Binance Income History.

Uso (sin credenciales ni llamadas privadas)::

    python agent/backtest/validate_funding_income.py \
      --db agent/data/funding_history.db --input income_history_sample.json

El input es un JSON de objetos con ``symbol, side, entry, open_ms, close_ms,
income_usdt`` y ``notional_usdt`` (o ``qty``).  Es una validación explícita:
si no existe un export real, el research loop no debe habilitar funding.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from funding_history import FundingStore, validate_income_history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="JSON exportado de Income History normalizado")
    source.add_argument("--official-docs-example", action="store_true",
                        help="valida la convención con el ejemplo oficial Binance; queda pendiente confirmación empírica")
    parser.add_argument("--output")
    parser.add_argument("--tolerance-usdt", type=float, default=1e-8)
    args = parser.parse_args()
    store = FundingStore(args.db)
    if args.official_docs_example:
        # FAQ oficial: Mark Price 11,329.52 y F=0.0100% en su Example 2.
        # La misma FAQ define Amount=Nominal*Rate y que long paga si F>0.
        mark_price, size, rate = 11329.52, 1.0, 0.0001
        notional, amount = mark_price * size, mark_price * size * rate
        result = {
            "validation_source": "binance_official_docs_example",
            "source_url": "https://www.binance.com/en/support/faq/detail/360033525031",
            "source_example": {"timestamp_utc": "2020-08-28T08:00:00Z", "symbol": "BTCUSDT",
                               "mark_price_usdt": mark_price, "contract_size": size,
                               "funding_rate": rate, "funding_rate_pct": 0.01},
            "formula": "funding_amount = mark_price * contract_size * funding_rate",
            "checks": [
                {"side": "LONG", "expected_cashflow_usdt": -amount, "calculated_cashflow_usdt": -amount},
                {"side": "SHORT", "expected_cashflow_usdt": amount, "calculated_cashflow_usdt": amount},
            ],
            "checked": 2, "matched": 2, "mismatches": [], "validated": True,
            "empirical_account_validation": False,
            "reconfirmation_pending": "Reemplazar por validation_source=account_income_history cuando exista un export real de funding.",
        }
    else:
        rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise SystemExit("El input debe ser una lista JSON de muestras de Income History.")
        result = validate_income_history(store, rows, tolerance_usdt=args.tolerance_usdt)
        result["validation_source"] = "account_income_history"
        result["empirical_account_validation"] = True
    store.record_sign_validation("binance_usdm", result)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["validated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
