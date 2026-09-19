"""
Identifica las rachas de perdedores consecutivos reales de FVG-15m
original (316 trades, AgentDecisionJson) y busca que las distingue de
los tramos ganadores -- side, btc_context, entry_status, simbolo
repetido, hora del dia -- para encontrar un corte que rompa esas rachas
sin destruir el resto de la estrategia (que ya sabemos, es la ganadora
real y no hay que tocarla a lo bruto).
"""
import json
import sys
import io
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PATH = r"C:\Users\Nicolas\fvg_orig_all.jsonl"


def load():
    rows = []
    with open(PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            opened_at = parts[-1]
            pnl = parts[-2]
            js = "|".join(parts[:-2])
            try:
                pnl = float(pnl)
                d = json.loads(js)
            except Exception:
                continue
            cand = d.get("candidate", {})
            fvg = cand.get("agent_audit_context", {}).get("fvg", {})
            btc = d.get("btc_context", {})
            temporal = d.get("temporal_context", {})
            snap = d.get("compression_snapshot_at_entry", {})
            rows.append({
                "pnl": pnl, "win": pnl > 0, "opened_at": opened_at,
                "symbol": cand.get("symbol"), "side": cand.get("side"),
                "gap_pct": fvg.get("gap_pct"), "tp_distance_pct": fvg.get("tp_distance_pct"),
                "entry_status": fvg.get("entry_status"),
                "btc_regime": btc.get("regime"), "btc_pct_1h": btc.get("pct_1h"),
                "btc_pct_15m": btc.get("pct_15m"),
                "session": temporal.get("session"), "hour_utc": temporal.get("hour_utc"),
                "u_shape_count": snap.get("u_shape_count"),
                "slope_ema50": snap.get("slope_ema50_deg"),
            })
    rows.sort(key=lambda r: r["opened_at"])
    return rows


def main():
    rows = load()
    print(f"Total: {len(rows)} trades\n")

    # Identificar rachas de perdedores consecutivos
    streaks = []
    cur = []
    for r in rows:
        if not r["win"]:
            cur.append(r)
        else:
            if len(cur) >= 5:
                streaks.append(list(cur))
            cur = []
    if len(cur) >= 5:
        streaks.append(cur)

    print(f"Rachas de >=5 perdedores seguidos: {len(streaks)}\n")
    all_streak_trades = []
    for i, s in enumerate(streaks, 1):
        pnl_sum = sum(t["pnl"] for t in s)
        print(f"--- Racha #{i}: {len(s)} perdedores | {s[0]['opened_at'][:10]} -> {s[-1]['opened_at'][:10]} | PnL=${pnl_sum:.2f} ---")
        sides = [t["side"] for t in s]
        regimes = [t["btc_regime"] for t in s]
        statuses = [t["entry_status"] for t in s]
        symbols = [t["symbol"] for t in s]
        print(f"    side(0=LONG,1=SHORT): {sides}")
        print(f"    btc_regime: {regimes}")
        print(f"    entry_status: {statuses}")
        print(f"    simbolos: {symbols}")
        print(f"    btc_pct_1h: {[round(t['btc_pct_1h'],3) if t['btc_pct_1h'] is not None else None for t in s]}")
        all_streak_trades.extend(s)

    # Comparacion agregada: trades DENTRO de rachas largas vs el resto
    rest = [r for r in rows if r not in all_streak_trades]
    print(f"\n=== Comparacion: dentro de rachas largas (n={len(all_streak_trades)}) vs resto (n={len(rest)}) ===")
    for key in ("side", "btc_regime", "entry_status"):
        print(f"\n-- {key} --")
        for pool_name, pool in (("EN RACHA", all_streak_trades), ("RESTO", rest)):
            vals = {}
            for t in pool:
                v = t[key]
                vals[v] = vals.get(v, 0) + 1
            total = len(pool)
            dist = {k: f"{v}/{total} ({100*v/total:.0f}%)" for k, v in vals.items()}
            print(f"   {pool_name:10s}: {dist}")

    def avg(pool, key):
        vals = [p[key] for p in pool if p[key] is not None]
        return sum(vals) / len(vals) if vals else None

    for key in ("btc_pct_1h", "btc_pct_15m", "u_shape_count", "slope_ema50", "gap_pct", "tp_distance_pct"):
        a = avg(all_streak_trades, key)
        b = avg(rest, key)
        print(f"   avg {key:16s}: EN RACHA={a} | RESTO={b}")


if __name__ == "__main__":
    main()
