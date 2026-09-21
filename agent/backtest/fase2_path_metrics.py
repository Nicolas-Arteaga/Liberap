"""Fase 2 condicional: métricas de trayectoria, sin modelo de salida ni PnL USD.

Calcula sólo desde velas locales: MFE, MAE, giveback, tiempo al MFE y retornos
a horizontes fijos.  No decide trades, no aplica TP/SL/timeout y no usa PnL.
"""
import argparse, csv, json, os, random, sqlite3
from collections import defaultdict
from datetime import datetime
from statistics import mean, median

BASE = 300_000
HORIZONS = (6, 12, 24, 48)


def epoch_ms(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def ret(entry, price, side):
    return ((entry - price) / entry if side == "short" else (price - entry) / entry) * 100.0


def bootstrap_ci(values, seed=20260920, draws=2000):
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(draws))
    return [samples[int(draws * .025)], samples[int(draws * .975) - 1]]


def load_ma(path):
    out = []
    for item in json.load(open(path, encoding="utf-8")):
        out.append({"strategy": "MA Slope Caso 3", "symbol": item["sym"],
                    "opened_at": item["open_utc"], "entry": float(item["entry"]),
                    "side": "short" if float(item["sl"]) > float(item["entry"]) else "long"})
    return out


def load_band(path):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        if row["Name"] != "Band Touch 15m" or not row["ClosedAt"] or not row["EntryPrice"]:
            continue
        try:
            decision = json.loads(row["AgentDecisionJson"] or "{}")
            side = (decision.get("candidate") or {}).get("side")
            side = "short" if int(side) == 1 else "long" if int(side) == 0 else None
            if side is None:
                continue
            out.append({"strategy": "Band Touch 15m", "symbol": row["Symbol"],
                        "opened_at": row["OpenedAt"], "entry": float(row["EntryPrice"]), "side": side})
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return out


def metric(conn, trade):
    opened = epoch_ms(trade["opened_at"])
    rows = conn.execute(
        "SELECT open_time,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' "
        "AND open_time>=? AND open_time<=? ORDER BY open_time",
        (trade["symbol"], opened, opened + 48 * 3_600_000 + BASE),
    ).fetchall()
    if not rows:
        return None
    highs = [(t + BASE - opened, ret(trade["entry"], h, trade["side"])) for t, h, _, _ in rows]
    lows = [(t + BASE - opened, ret(trade["entry"], l, trade["side"])) for t, _, l, _ in rows]
    favorable = lows if trade["side"] == "short" else highs
    adverse = highs if trade["side"] == "short" else lows
    mfe_t, mfe = max(favorable, key=lambda x: x[1])
    _, mae = min(adverse, key=lambda x: x[1])
    horizon_returns = {}
    for hours in HORIZONS:
        target = hours * 3_600_000
        eligible = [row for row in rows if row[0] + BASE - opened <= target]
        if eligible:
            horizon_returns[str(hours)] = ret(trade["entry"], eligible[-1][3], trade["side"])
        else:
            horizon_returns[str(hours)] = None
    last_48 = horizon_returns["48"]
    return {**trade, "mfe_pct": mfe, "mae_pct": mae, "giveback_pct": None if last_48 is None else mfe - last_48,
            "time_to_mfe_hours": mfe_t / 3_600_000, "returns_pct": horizon_returns}


def summarize(rows):
    output = []
    for key in sorted({(r["strategy"], r["side"]) for r in rows}):
        group = [r for r in rows if (r["strategy"], r["side"]) == key]
        item = {"strategy": key[0], "side": key[1], "n": len(group), "metrics": {}}
        for field in ("mfe_pct", "mae_pct", "giveback_pct", "time_to_mfe_hours"):
            vals = [r[field] for r in group if r[field] is not None]
            item["metrics"][field] = {"mean": mean(vals), "median": median(vals), "bootstrap_95_ci_mean": bootstrap_ci(vals)} if vals else None
        item["returns_pct"] = {}
        for h in map(str, HORIZONS):
            vals = [r["returns_pct"][h] for r in group if r["returns_pct"][h] is not None]
            item["returns_pct"][h] = {"mean": mean(vals), "median": median(vals), "bootstrap_95_ci_mean": bootstrap_ci(vals)} if vals else None
        item["symbols"] = {s: sum(1 for r in group if r["symbol"] == s) for s in sorted({r["symbol"] for r in group})}
        output.append(item)
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ma-scratch", required=True)
    p.add_argument("--band-postgres-csv", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--db", default="/app/data/binance_vision_clean.db")
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    inputs = load_ma(a.ma_scratch) + load_band(a.band_postgres_csv)
    if a.smoke:
        inputs = inputs[:1]
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rows, missing = [], []
    for trade in inputs:
        result = metric(conn, trade)
        (rows if result else missing).append(result or trade)
    conn.close()
    payload = {"method": "velas 5m; sin TP/SL/timeout/PnL USD", "input_count": len(inputs),
               "with_klines": len(rows), "missing_klines": len(missing), "trades": rows,
               "missing": missing, "summary_by_strategy_side": summarize(rows)}
    os.makedirs(os.path.dirname(a.output), exist_ok=True)
    json.dump(payload, open(a.output, "w", encoding="utf-8"), indent=2)
    print(json.dumps({k: payload[k] for k in ("input_count", "with_klines", "missing_klines")}))


if __name__ == "__main__":
    main()
