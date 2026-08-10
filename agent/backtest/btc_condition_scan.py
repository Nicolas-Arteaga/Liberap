"""
Escaneo sistematico de condiciones tecnicas contra retorno futuro en
BTCUSDT, sobre TODA la historia disponible (dic 2025 - jul 2026, ~23000
velas de 15m) -- pedido explicito del usuario 2026-08-02: no testear un
patron ya elegido de antemano, sino escanear de forma "viva" que
condiciones tienen ventaja real.

Filtro anti data-snooping: cada condicion se evalua por separado en la
PRIMERA mitad y la SEGUNDA mitad del periodo -- solo se reporta como
"robusta" si el signo del retorno promedio se sostiene en AMBAS mitades
(si solo funciona en una mitad, es ruido de esa mitad, no una ventaja
real y repetible).

Uso: python -m backtest.btc_condition_scan   (desde agent/)
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")
SYMBOL = "BTCUSDT"
FORWARD_HORIZON = 16  # velas de 15m adelante = 4 horas
RSI_PERIOD = 14
ATR_PERIOD = 14


def load_klines(conn, symbol: str) -> list:
    cur = conn.cursor()
    cur.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines_clean WHERE symbol=? ORDER BY open_time ASC",
        (symbol,)
    )
    return [(r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in cur.fetchall()]


def sma_series(closes: list, period: int) -> list:
    out = [None] * len(closes)
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= period:
            s -= closes[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rsi_series(closes: list, period: int) -> list:
    out = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss)) if avg_loss > 0 else 100.0
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain, loss = max(d, 0.0), max(-d, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss)) if avg_loss > 0 else 100.0
    return out


def atr_series(candles: list, period: int) -> list:
    n = len(candles)
    out = [None] * n
    trs = [None] * n
    for i in range(1, n):
        h, l, prev_c = candles[i][2], candles[i][3], candles[i - 1][4]
        trs[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))
    if n <= period:
        return out
    s = sum(t for t in trs[1:period + 1] if t is not None)
    out[period] = s / period
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    return out


def main():
    conn = sqlite3.connect(DB_PATH)
    candles = load_klines(conn, SYMBOL)
    n = len(candles)
    closes = [c[4] for c in candles]
    volumes = [c[5] for c in candles]
    print(f"{SYMBOL}: {n} velas de 15m cargadas ({os.path.basename(DB_PATH)})", flush=True)

    ma7 = sma_series(closes, 7)
    ma25 = sma_series(closes, 25)
    ma50 = sma_series(closes, 50)
    ma99 = sma_series(closes, 99)
    rsi = rsi_series(closes, RSI_PERIOD)
    atr = atr_series(candles, ATR_PERIOD)
    vol_avg20 = sma_series(volumes, 20)

    # ── Definicion de condiciones (cada una: funcion(i) -> bool) ──
    def compressed(i):
        vals = [ma7[i], ma25[i], ma50[i], ma99[i]]
        if any(v is None for v in vals):
            return False
        spread = (max(vals) - min(vals)) / closes[i]
        return spread < 0.004

    def cross_up_99(i):
        if i < 1 or ma99[i] is None or ma99[i - 1] is None:
            return False
        return closes[i - 1] <= ma99[i - 1] and closes[i] > ma99[i]

    def cross_down_99(i):
        if i < 1 or ma99[i] is None or ma99[i - 1] is None:
            return False
        return closes[i - 1] >= ma99[i - 1] and closes[i] < ma99[i]

    def compressed_then_cross_up(i):
        return cross_up_99(i) and any(compressed(k) for k in range(max(0, i - 6), i))

    def compressed_then_cross_down(i):
        return cross_down_99(i) and any(compressed(k) for k in range(max(0, i - 6), i))

    def rsi_oversold(i):
        return rsi[i] is not None and rsi[i] < 30

    def rsi_overbought(i):
        return rsi[i] is not None and rsi[i] > 70

    def vol_spike(i):
        return vol_avg20[i] is not None and vol_avg20[i] > 0 and volumes[i] >= 2.0 * vol_avg20[i]

    def trend_up_stack(i):
        vals = [ma7[i], ma25[i], ma50[i], ma99[i]]
        if any(v is None for v in vals):
            return False
        return closes[i] > ma7[i] > ma25[i] > ma50[i] > ma99[i]

    def trend_down_stack(i):
        vals = [ma7[i], ma25[i], ma50[i], ma99[i]]
        if any(v is None for v in vals):
            return False
        return closes[i] < ma7[i] < ma25[i] < ma50[i] < ma99[i]

    def golden_cross_7_25(i):
        if i < 1 or ma7[i] is None or ma25[i] is None or ma7[i - 1] is None or ma25[i - 1] is None:
            return False
        return ma7[i - 1] <= ma25[i - 1] and ma7[i] > ma25[i]

    def death_cross_7_25(i):
        if i < 1 or ma7[i] is None or ma25[i] is None or ma7[i - 1] is None or ma25[i - 1] is None:
            return False
        return ma7[i - 1] >= ma25[i - 1] and ma7[i] < ma25[i]

    def atr_pct(i):
        return (atr[i] / closes[i]) if atr[i] is not None else None

    conditions = {
        "RSI<30 (sobreventa)": rsi_oversold,
        "RSI>70 (sobrecompra)": rsi_overbought,
        "MAs comprimidas (<0.4%)": compressed,
        "Cruce violento arriba MA99": cross_up_99,
        "Cruce violento abajo MA99": cross_down_99,
        "Compresion + cruce arriba (patron del usuario)": compressed_then_cross_up,
        "Compresion + cruce abajo (patron del usuario)": compressed_then_cross_down,
        "Volumen >= 2x promedio": vol_spike,
        "Stack alcista (MA7>25>50>99, precio arriba)": trend_up_stack,
        "Stack bajista (MA7<25<50<99, precio abajo)": trend_down_stack,
        "Golden cross MA7/MA25": golden_cross_7_25,
        "Death cross MA7/MA25": death_cross_7_25,
    }

    valid_start = 100  # margen para que todas las MAs/RSI/ATR ya tengan valor
    valid_end = n - FORWARD_HORIZON
    mid = valid_start + (valid_end - valid_start) // 2

    def forward_return(i):
        return (closes[i + FORWARD_HORIZON] - closes[i]) / closes[i]

    # Baseline incondicional (para comparar cada condicion contra "no hacer nada especial")
    all_returns = [forward_return(i) for i in range(valid_start, valid_end)]
    baseline_mean = sum(all_returns) / len(all_returns)
    baseline_wr = sum(1 for r in all_returns if r > 0) / len(all_returns) * 100

    print(f"Horizonte: {FORWARD_HORIZON} velas (4h) | Baseline incondicional: retorno medio={baseline_mean*100:.3f}% | WR={baseline_wr:.1f}%", flush=True)
    print("=" * 115, flush=True)
    print(f"{'Condicion':48s} | {'n1':>5s} {'ret1%':>7s} {'wr1%':>6s} | {'n2':>5s} {'ret2%':>7s} {'wr2%':>6s} | robusto?", flush=True)

    rows = []
    for name, fn in conditions.items():
        idx1 = [i for i in range(valid_start, mid) if fn(i)]
        idx2 = [i for i in range(mid, valid_end) if fn(i)]
        if len(idx1) < 20 or len(idx2) < 20:
            rows.append((name, len(idx1), None, None, len(idx2), None, None, "muestra insuficiente"))
            continue
        ret1 = [forward_return(i) for i in idx1]
        ret2 = [forward_return(i) for i in idx2]
        m1, m2 = sum(ret1) / len(ret1), sum(ret2) / len(ret2)
        wr1 = sum(1 for r in ret1 if r > 0) / len(ret1) * 100
        wr2 = sum(1 for r in ret2 if r > 0) / len(ret2) * 100
        same_sign = (m1 > 0 and m2 > 0) or (m1 < 0 and m2 < 0)
        meaningful = abs(m1) > abs(baseline_mean) * 1.3 and abs(m2) > abs(baseline_mean) * 1.3
        robust = same_sign and meaningful
        rows.append((name, len(idx1), m1, wr1, len(idx2), m2, wr2, "SI" if robust else "no"))

    rows.sort(key=lambda r: (r[7] != "SI", -(abs(r[2]) + abs(r[5])) if r[2] is not None else 0))
    for name, n1, m1, wr1, n2, m2, wr2, robust in rows:
        if m1 is None:
            print(f"{name:48s} | {n1:5d} {'--':>7s} {'--':>6s} | {n2:5d} {'--':>7s} {'--':>6s} | {robust}")
        else:
            print(f"{name:48s} | {n1:5d} {m1*100:7.3f} {wr1:6.1f} | {n2:5d} {m2*100:7.3f} {wr2:6.1f} | {robust}")

    print("=" * 115)
    robust_conditions = [r for r in rows if r[7] == "SI"]
    print(f"Condiciones robustas (edge consistente en ambas mitades del historico): {len(robust_conditions)}")
    for r in robust_conditions:
        print(f"  - {r[0]}: retorno medio {r[2]*100:.3f}% (1ra mitad) / {r[5]*100:.3f}% (2da mitad), horizonte {FORWARD_HORIZON} velas (4h)")


if __name__ == "__main__":
    main()
