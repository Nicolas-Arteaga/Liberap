"""
2026-08-18: EXPLORATORIO -- señal nueva, nunca antes probada en este
proyecto (nada que ver con nivel/RSI/MA reciclados). Hipotesis: funding
rate extremo = posicionamiento saturado (todos long o todos short en ese
simbolo) -> probable reversion. Contrario a "seguir la tendencia", esto
apuesta a squeeze del lado saturado.

LIMITACION HONESTA: la tabla funding_rates solo tiene ~6 semanas reales de
historia (2026-07-07 a 2026-08-18, ver auditoria previa) -- mucho menos que
los 8 meses usados para calibrar FVG/MA Slope. Esto es una PRIMERA MIRADA
de baja confianza, no un backtest validado. Si el numero es prometedor,
hay que esperar a que se acumule mas historia antes de confiar en el.

Motor real: 3 cupos x $150 (capital sim), validate_pre_trade real.
"""
import sys
import os
import sqlite3
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import MARGIN, FEE  # noqa: E402


def atr_series_local(rows, period=14):
    """rows: (open_time, high, low, close) -- ATR simple (no Wilder) sobre esas 4 columnas."""
    n = len(rows)
    trs = [None] * n
    for i in range(1, n):
        h, l, pc = rows[i][1], rows[i][2], rows[i - 1][3]
        trs[i] = max(h - l, abs(h - pc), abs(l - pc))
    out = [None] * n
    for i in range(period, n):
        window = [t for t in trs[i - period + 1:i + 1] if t is not None]
        if len(window) == period:
            out[i] = sum(window) / period
    return out
from setup_validator import validate_pre_trade  # noqa: E402

KLINES_DB = os.path.join(os.path.dirname(__file__), "..", "data", "klines.db")
FUNDING_MIN_TS = 1783382400001  # 2026-07-07, ver auditoria (filtra la fila basura epoch=0)
SLOTS = 3
PCTL_EXTREME = 0.90  # top/bottom 10% de funding cross-sectional = "saturado"
ATR_SL_MULT = 2.5
RR_MULT = 3.0


def load_funding(conn):
    cur = conn.cursor()
    cur.execute("SELECT symbol, funding_time, funding_rate FROM funding_rates WHERE funding_time >= ? ORDER BY funding_time",
                (FUNDING_MIN_TS,))
    by_time = defaultdict(list)
    for symbol, ft, fr in cur.fetchall():
        by_time[ft].append((symbol, fr))
    return by_time


def load_15m_map(conn, symbols):
    cur = conn.cursor()
    data = {}
    for symbol in symbols:
        cur.execute("SELECT open_time, high, low, close FROM klines WHERE symbol=? AND interval='15m' "
                    "AND open_time >= ? ORDER BY open_time", (symbol, FUNDING_MIN_TS - 86400000))
        rows = cur.fetchall()
        if len(rows) < 100:
            continue
        data[symbol] = rows
    return data


def build_candidate(symbol, side, entry):
    return {
        "symbol": symbol, "confluence_score": 80.0, "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG", "side": side,
        "source": "funding_contrarian_mode", "price_at_signal": entry, "estimated_range_pct": 5.0,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }


def nearest_candle_idx(rows, ts):
    # rows ordenados por open_time -- busca la vela mas cercana <= ts, en ventana de 20min
    lo, hi = 0, len(rows) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if rows[mid][0] <= ts:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None or ts - rows[best][0] > 20 * 60 * 1000:
        return None
    return best


def main():
    conn = sqlite3.connect(KLINES_DB)
    funding_by_time = load_funding(conn)
    print(f"Timestamps de funding: {len(funding_by_time)}")
    all_symbols = sorted({s for lst in funding_by_time.values() for s, _ in lst})
    print(f"Simbolos con funding: {len(all_symbols)}")

    klines = load_15m_map(conn, all_symbols)
    print(f"Simbolos con klines 15m suficientes: {len(klines)}")

    atr_cache = {s: atr_series_local(rows, 14) for s, rows in klines.items()}

    ts_list = sorted(funding_by_time.keys())
    open_trades = {}
    all_trades = []

    for ts in ts_list:
        # cerrar posiciones abiertas: chequear TP/SL en velas 15m entre el ultimo chequeo y ahora
        for symbol in list(open_trades.keys()):
            rows = klines.get(symbol)
            if not rows:
                continue
            ot = open_trades[symbol]
            idx = nearest_candle_idx(rows, ts)
            if idx is None:
                continue
            for j in range(ot["last_idx"] + 1, idx + 1):
                h, l = rows[j][1], rows[j][2]
                side = ot["side"]
                hit_tp = (l <= ot["tp"]) if side == 1 else (h >= ot["tp"])
                hit_sl = (h >= ot["sl"]) if side == 1 else (l <= ot["sl"])
                if hit_tp or hit_sl:
                    close_px = ot["tp"] if hit_tp else ot["sl"]
                    qty = MARGIN / ot["entry"]
                    gross = qty * (ot["entry"] - close_px) if side == 1 else qty * (close_px - ot["entry"])
                    fees = (qty * ot["entry"] + qty * close_px) * FEE
                    all_trades.append({"symbol": symbol, "pnl": gross - fees, "open_ts": ot["open_ts"], "close_ts": rows[j][0]})
                    del open_trades[symbol]
                    break
            else:
                ot["last_idx"] = idx

        available = SLOTS - len(open_trades)
        if available <= 0:
            continue

        rows_ft = funding_by_time[ts]
        rates = sorted(r for _, r in rows_ft)
        if len(rates) < 10:
            continue
        n = len(rates)
        hi_cut = rates[int(n * PCTL_EXTREME)]
        lo_cut = rates[int(n * (1 - PCTL_EXTREME))]

        candidates = []
        for symbol, fr in rows_ft:
            if symbol in open_trades or symbol not in klines:
                continue
            extreme_long = fr >= hi_cut and fr > 0.0003
            extreme_short = fr <= lo_cut and fr < -0.0003
            if not (extreme_long or extreme_short):
                continue
            rows = klines[symbol]
            idx = nearest_candle_idx(rows, ts)
            if idx is None or idx < 20:
                continue
            # v3: funding extremo + FALLA de confirmacion de precio (la
            # posicion saturada dejo de hacer nuevos maximos/minimos en las
            # ultimas 8 velas de 15m = 2h -- "trapped longs/shorts" real,
            # no solo funding crudo). Insight de la investigacion: "funding
            # plus failed price action can flag crowded longs."
            lookback_hi = max(r[1] for r in rows[idx - 8:idx])
            lookback_lo = min(r[2] for r in rows[idx - 8:idx])
            price_now = rows[idx][3]
            if extreme_long and price_now < lookback_hi:
                side = 1  # crowded longs, precio ya no hace maximos -> SHORT
            elif extreme_short and price_now > lookback_lo:
                side = 0  # crowded shorts, precio ya no hace minimos -> LONG
            else:
                continue
            atr = atr_cache[symbol][idx]
            if atr is None or atr <= 0:
                continue
            entry = rows[idx][3]
            sl_dist = ATR_SL_MULT * atr
            tp_dist = sl_dist * RR_MULT
            sl = entry + sl_dist if side == 1 else entry - sl_dist
            tp = entry - tp_dist if side == 1 else entry + tp_dist
            candidates.append((abs(fr), symbol, side, entry, sl, tp, idx))

        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, symbol, side, entry, sl, tp, idx in candidates[:available]:
            cand = build_candidate(symbol, side, entry)
            try:
                v_ok, _, _ = validate_pre_trade(cand, entry, profile=None, btc_filter=None, btc_corr=None)
            except Exception:
                v_ok = True
            if not v_ok:
                continue
            open_trades[symbol] = {"side": side, "entry": entry, "sl": sl, "tp": tp,
                                    "open_ts": ts, "last_idx": idx}

    n = len(all_trades)
    if n == 0:
        print("Sin trades.")
        return
    total = sum(t["pnl"] for t in all_trades)
    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    days = (ts_list[-1] - ts_list[0]) / 86400000
    monthly = total / (days / 30.44) if days > 0 else 0
    half = n // 2
    pnl_h1 = sum(t["pnl"] for t in all_trades[:half])
    pnl_h2 = sum(t["pnl"] for t in all_trades[half:])
    print(f"\n=== FUNDING CONTRARIAN (exploratorio, {days:.0f} dias reales de historia) ===")
    print(f"Trades: {n} | WR: {wins/n*100:.1f}% | PnL total: ${total:.2f} | ${monthly:.2f}/mes")
    print(f"Mitad 1: {half} trades, ${pnl_h1:.2f} | Mitad 2: {n-half} trades, ${pnl_h2:.2f}")
    print(f"AVISO: solo {days:.0f} dias de historia real de funding -- baja confianza, no comparable 1:1 con los 8 meses de FVG/MA Slope.")


if __name__ == "__main__":
    main()
