"""Create the immutable ex-ante Binance USD-M universe snapshot for roadmap V1."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


OUT = Path(__file__).with_name("microstructure_universe_v1.json")
EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKERS = "https://fapi.binance.com/fapi/v1/ticker/24hr"


def fetch(url: str):
    with urlopen(url, timeout=30) as response:  # nosec B310: fixed public exchange endpoints
        return json.load(response)


def main() -> int:
    if OUT.exists():
        print(f"Refusing to overwrite immutable snapshot: {OUT}", file=sys.stderr)
        return 2
    info = fetch(EXCHANGE_INFO)
    tickers = {row["symbol"]: row for row in fetch(TICKERS)}
    candidates = []
    for item in info["symbols"]:
        symbol = item["symbol"]
        if not (
            item.get("contractType") == "PERPETUAL"
            and item.get("status") == "TRADING"
            and item.get("quoteAsset") == "USDT"
            and symbol in tickers
        ):
            continue
        base = item.get("baseAsset", "")
        if base in {"USDC", "BUSD", "USDT", "FDUSD", "TUSD", "USDP", "DAI"}:
            continue
        candidates.append((float(tickers[symbol].get("quoteVolume", 0.0)), symbol))
    candidates.sort(key=lambda row: (-row[0], row[1]))
    symbols = [symbol for _, symbol in candidates[:200]]
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "venue": "binance_usdm",
            "contract_type": "PERPETUAL",
            "status": "TRADING",
            "quote_asset": "USDT",
            "rank": "24h_quote_volume_descending",
            "limit": 200,
            "excluded_base_assets": ["USDC", "BUSD", "USDT", "FDUSD", "TUSD", "USDP", "DAI"],
        },
        "symbols": symbols,
        "source_sha256": hashlib.sha256(
            json.dumps({"exchangeInfo": info, "ticker24hr": tickers}, sort_keys=True).encode()
        ).hexdigest(),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"symbols": len(symbols), "out": str(OUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
