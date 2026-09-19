"""
LABORATORIO DE ESTRATEGIAS -- 2026-08-11, pedido explicito del usuario:
"un sistema altamente inteligente que nunca se canse de correr
estrategias" buscando algo que genere >=$150/mes con margen real ($150,
3 cupos O 1 de 450 -- da igual, el motor mide por $/mes con margen fijo
$150 igual que produccion).

Genera estrategias AL AZAR combinando piezas ya validadas esta sesion
(entrada por cruce de MAs, por barrido de nivel, por rebote de banda, por
RSI extremo; ATR SL/TP; lado LONG/SHORT/AMBOS; timeframe 15m/1h/4h) sobre
klines historicos reales (agent/data/binance_vision_clean.db, TOP_40 +
canasta ampliada), las prueba con el mismo rigor de toda la sesion:

  - sizing real ($150 margen fijo, comisiones reales, no "R" abstracto
    -- error real cometido antes en esta sesion, corregido acá desde el
    diseño)
  - split temporal (1ra mitad cronologica vs 2da, AMBAS tienen que ser
    positivas para no ser puro ruido -- descarto todo lo que no pasa esto)
  - minimo de trades (evita conclusiones de muestras chicas, mismo error
    que ya paso 3+ veces esta sesion)

Corre en loop infinito. Cada estrategia que pasa el umbral configurado
(BAR_MONTHLY_USD) se escribe en found_strategies.jsonl (nunca se pierde
un hallazgo). Progreso periodico en lab_progress.log. Pensado para correr
en background con nohup, sin supervision.

Uso: python -m backtest.strategy_lab   (desde agent/, dejar corriendo)
"""
import sys
import os
import sqlite3
import json
import random
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.engine import TOP_40_SYMBOLS  # noqa: E402
from setup_validator import validate_pre_trade  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")
FOUND_PATH = os.path.join(os.path.dirname(__file__), "found_strategies.jsonl")
PROGRESS_PATH = os.path.join(os.path.dirname(__file__), "lab_progress.log")
TESTED_LOG = os.path.join(os.path.dirname(__file__), "lab_tested_all.jsonl")
CURRENT_PATH = os.path.join(os.path.dirname(__file__), "lab_current.json")

FEE = 0.0004
MARGIN = 150.0
BAR_MONTHLY_USD = 150.0
MIN_TRADES_PER_HALF = 25
# 2026-08-17: REGLAS REALES, no negociables -- el usuario encontro que el
# lab corria con capital INFINITO (todos los simbolos que calificaban
# operaban en simultaneo, sin limite), inflando cada resultado. Produccion
# real jamas tiene mas de SLOTS posiciones de MARGIN abiertas al mismo
# tiempo POR ESTRATEGIA (MAX_OPEN_POSITIONS=3 en config.py) -- de aca en
# mas, TODO resultado del lab pasa por este limite antes de reportarse.
SLOTS = 3

# Mode flag real de setup_validator.py::_is_direct_injection_candidate()
# por entry_type -- level_sweep/band_touch SI tienen flag real en
# produccion (mismo patron que ya corre en vivo). ma_cross/rsi_extreme/
# 2026-08-18: rsi_extreme y ma_pullback SI tienen equivalente real ahora
# (rsi_extreme_mode, ma_pullback_mode agregados a produccion esta noche via
# _run_rsi_extreme_scan/_run_ma_pullback_scan en verge_agent.py) -- esto
# habia quedado sin actualizar, causando un bug real de no-reproducibilidad:
# sin el flag, esos dos entry_types caian en el veto disabled_signal_for_tier,
# que depende del watchlist EN VIVO (Tier1/2/3 se recalculan por volatilidad
# real cada vez que corre el script) -- mismo backtest, mismos parametros,
# daba numeros distintos corrida a corrida. ma_cross NO tiene equivalente
# real todavia, sigue sin eximirse (y por lo tanto sigue siendo no-
# reproducible en backtest por la misma razon -- pendiente).
MODE_FLAG_BY_ENTRY_TYPE = {
    "level_sweep": "level_sweep_1h_mode",
    "band_touch": "band_touch_mode",
    "rsi_extreme": "rsi_extreme_mode",
    "ma_pullback": "ma_pullback_mode",
}

# ── Canasta ampliada: TOP_40 + lo que haya en klines_clean con suficiente historia ──
def load_basket(conn):
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval='15m'")
    all_syms = [r[0] for r in cur.fetchall()]
    basket = list(dict.fromkeys(TOP_40_SYMBOLS + all_syms))
    return basket


# ── Datos ──
_cache_15m = {}


def load_15m(conn, symbol):
    if symbol in _cache_15m:
        return _cache_15m[symbol]
    cur = conn.cursor()
    cur.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines_clean "
        "WHERE symbol=? AND interval='15m' ORDER BY open_time ASC",
        (symbol,),
    )
    rows = cur.fetchall()
    _cache_15m[symbol] = rows
    return rows


def resample(rows, tf_minutes):
    bucket_ms = tf_minutes * 60_000
    buckets = {}
    for r in rows:
        b = r[0] - (r[0] % bucket_ms)
        buckets.setdefault(b, []).append(r)
    min_bars = max(1, tf_minutes // 15)
    out = []
    for b in sorted(buckets.keys()):
        g = sorted(buckets[b], key=lambda x: x[0])
        if len(g) < min_bars:
            continue
        out.append((b, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)))
    return out


def sma(vals, period, idx):
    if idx + 1 < period:
        return None
    return sum(vals[idx + 1 - period:idx + 1]) / period


def rsi_at(closes, period, idx):
    if idx + 1 < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(idx - period + 1, idx + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_g, avg_l = gains / period, losses / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))


def atr_series(candles, period=14):
    """2026-08-19: bug real encontrado verificando señal por señal contra
    trades reales (APRUSDT: TP desalineado 32%) -- esta funcion usaba ATR
    suavizado de Wilder (memoria de toda la historia previa), pero
    produccion real (_run_level_sweep_1h_scan y las demas en
    verge_agent.py) usa un promedio simple de las ultimas 14 TR, ventana
    fija sin memoria. Formulas distintas = SL/TP distintos = clasificacion
    ganador/perdedor distinta para CADA trade. Arreglado para matchear
    produccion exacto: promedio simple rolling de period barras."""
    trs = [0.0]
    for i in range(1, len(candles)):
        h, l, pc = candles[i][2], candles[i][3], candles[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = [None] * len(candles)
    for i in range(period, len(candles)):
        window = trs[max(1, i - period + 1):i + 1]
        atr[i] = sum(window) / len(window) if window else None
    return atr


# ── Espacio de generacion (piezas ya validadas esta sesion) ──
# 2026-08-16: se agrega "ma_pullback" -- pedido explicito del usuario tras
# notar que el lab solo encuentra SHORT (real, confirmado con datos: el
# periodo historico cargado fue mayormente bajista/de rango descendente
# para las alts). El lab nunca tuvo un patron que se parezca a lo que
# hacia MA Cross Momentum / MA Clone / Standard Scalping en produccion
# real (generaron $220+ en dias, antes de romperse) -- "pullback a zona de
# valor" en tendencia: MA7 con pendiente definida (arriba=LONG,
# abajo=SHORT) + el precio vuelve a meterse entre MA25 y MA99 desde
# afuera (entrada de continuacion, no de reversion como los otros 4
# tipos). Calculable 100% desde velas crudas, sin depender de Nexus-15
# (que no tiene wrapper offline en este motor). Asi el lab tambien cubre
# esta familia de ahora en mas, listo para cuando el regimen del mercado
# gire alcista otra vez.
ENTRY_TYPES = ["ma_cross", "level_sweep", "band_touch", "rsi_extreme", "ma_pullback"]
TIMEFRAMES_MIN = [15, 60, 240]
MA_PAIRS = [(7, 25), (25, 99), (50, 200), (9, 21), (20, 50)]
SIDES = ["LONG", "SHORT", "BOTH"]
ATR_SL_MULTS = [1.0, 1.5, 2.0, 3.0]
RR_MULTS = [1.5, 2.0, 3.0, 4.0, 6.0]
LOOKBACKS = [10, 20, 50]
RSI_THRESH = [(70, 30), (75, 25), (80, 20)]
# Pendiente minima de MA7 (en % sobre `lookback` velas) para considerar que
# hay tendencia real -- sin este piso, "pullback en tendencia" podia
# dispararse en mercado plano (MA7 con pendiente ~0, ruido puro).
MA_PULLBACK_SLOPE_MIN_PCT = [0.3, 0.6, 1.0, 1.5]
# Confirmacion de volumen opcional -- 1.0 = sin filtro (siempre pasa).
VOLUME_MULTS = [1.0, 1.2, 1.5]


def random_strategy():
    """
    2026-08-16: antes randomizaba ma_pair y rsi_thresh SIEMPRE, aunque
    detect_signal() solo los usa para entry_type=="ma_cross" y
    "rsi_extreme" respectivamente -- level_sweep/band_touch no los miran
    para nada. Resultado real encontrado por el usuario: la misma
    estrategia (misma señal, mismo backtest) se probaba hasta 15x con
    distinto ma_pair/rsi_thresh "de mentira", inflando testedCount y
    llenando el Top 10 de filas idénticas. Ahora solo se randomiza el
    parametro que el tipo de entrada realmente usa; el resto queda fijo
    en el primer valor del espacio (nunca None, para no romper el
    schema que ya consume el frontend).
    """
    et = random.choice(ENTRY_TYPES)
    return {
        "entry_type": et,
        "tf_min": random.choice(TIMEFRAMES_MIN),
        "ma_pair": random.choice(MA_PAIRS) if et == "ma_cross" else MA_PAIRS[0],
        "side": random.choice(SIDES),
        "atr_sl_mult": random.choice(ATR_SL_MULTS),
        "rr_mult": random.choice(RR_MULTS),
        "lookback": random.choice(LOOKBACKS) if et in ("level_sweep", "ma_pullback") else LOOKBACKS[0],
        "rsi_thresh": random.choice(RSI_THRESH) if et == "rsi_extreme" else RSI_THRESH[0],
        "slope_min_pct": random.choice(MA_PULLBACK_SLOPE_MIN_PCT) if et == "ma_pullback" else MA_PULLBACK_SLOPE_MIN_PCT[0],
        "volume_mult": random.choice(VOLUME_MULTS) if et == "ma_pullback" else VOLUME_MULTS[0],
    }


def detect_signal(strat, closes, highs, lows, i, level_high=None, level_low=None, volumes=None):
    """Devuelve 0 (LONG), 1 (SHORT) o None. i = indice actual (vela ya cerrada)."""
    et = strat["entry_type"]
    if et == "ma_pullback":
        # "Pullback a zona de valor" (MA Cross Momentum/MA Clone real): MA7
        # con pendiente definida marca la tendencia; LONG dispara cuando el
        # precio, tras estar arriba de la zona MA25-MA99, vuelve a meterse
        # adentro (continuacion tras respirar, no reversion). SHORT es el
        # espejo bajista. Volumen opcional: exige que la vela de entrada
        # tenga volumen >= promedio(20) * volume_mult (1.0 = sin filtro).
        ma7_now, ma25_now, ma99_now = sma(closes, 7, i), sma(closes, 25, i), sma(closes, 99, i)
        lb = strat["lookback"]
        ma7_prev = sma(closes, 7, i - lb) if i - lb >= 0 else None
        c_now, c_prev = closes[i], closes[i - 1] if i >= 1 else None
        if None in (ma7_now, ma25_now, ma99_now, ma7_prev, c_prev):
            return None
        slope_pct = (ma7_now - ma7_prev) / ma7_prev * 100 if ma7_prev else 0
        min_slope = strat.get("slope_min_pct", 0.3)

        vol_mult = strat.get("volume_mult", 1.0)
        if vol_mult > 1.0 and volumes is not None:
            vol_avg = sma(volumes, 20, i)
            if vol_avg is None or volumes[i] < vol_avg * vol_mult:
                return None

        zone_lo, zone_hi = min(ma25_now, ma99_now), max(ma25_now, ma99_now)
        was_inside = zone_lo <= c_prev <= zone_hi
        now_inside = zone_lo <= c_now <= zone_hi
        if was_inside or not now_inside:
            return None  # solo dispara al RE-ENTRAR a la zona, no si ya estaba adentro

        if slope_pct >= min_slope and c_prev > zone_hi:
            return 0  # LONG: tendencia alcista, pullback desde arriba de la zona
        if slope_pct <= -min_slope and c_prev < zone_lo:
            return 1  # SHORT: tendencia bajista, pullback desde abajo de la zona
        return None
    if et == "ma_cross":
        fast_p, slow_p = strat["ma_pair"]
        f_now, s_now = sma(closes, fast_p, i), sma(closes, slow_p, i)
        f_prev, s_prev = sma(closes, fast_p, i - 1), sma(closes, slow_p, i - 1)
        if None in (f_now, s_now, f_prev, s_prev):
            return None
        d_now, d_prev = f_now - s_now, f_prev - s_prev
        if d_prev <= 0 and d_now > 0:
            return 0
        if d_prev >= 0 and d_now < 0:
            return 1
        return None
    if et == "level_sweep":
        lb = strat["lookback"]
        if i < lb + 1 or level_high is None:
            return None
        h, l, c = highs[i], lows[i], closes[i]
        if h > level_high and c < level_high:
            return 1
        if l < level_low and c > level_low:
            return 0
        return None
    if et == "band_touch":
        p = 20
        m = sma(closes, p, i)
        if m is None or i + 1 < p:
            return None
        window = closes[i + 1 - p:i + 1]
        std = (sum((x - m) ** 2 for x in window) / p) ** 0.5
        upper, lower = m + 2 * std, m - 2 * std
        c = closes[i]
        if c > upper:
            return 1
        if c < lower:
            return 0
        return None
    if et == "rsi_extreme":
        hi_th, lo_th = strat["rsi_thresh"]
        r_now = rsi_at(closes, 14, i)
        r_prev = rsi_at(closes, 14, i - 1)
        if r_now is None or r_prev is None:
            return None
        if r_prev >= hi_th and r_now < hi_th:
            return 1
        if r_prev <= lo_th and r_now > lo_th:
            return 0
        return None
    return None


def _build_validate_candidate(strat, symbol, side, entry, sl_dist, historical_daily_change_pct=None):
    """Candidato con la forma minima que validate_pre_trade() necesita.
    level_sweep/band_touch usan su mode flag REAL (eximidos de
    range_too_small/disabled_signal_for_tier, igual que en produccion via
    _run_level_sweep_1h_scan/_run_band_touch_scan -- ambos mandan
    nexus15:{} vacio tambien). Los demas entry_types no tienen flag real
    todavia, asi que reciben un estimated_range_pct calculado del SL real
    para que el veto range_too_small los evalue con datos genuinos, no
    con el default 0 que los rechazaria siempre."""
    et = strat["entry_type"]
    mode_flag = MODE_FLAG_BY_ENTRY_TYPE.get(et)
    cand = {
        "symbol": symbol,
        "confluence_score": 80.0,
        "nexus_confidence": 80.0,
        "trade_direction": "SHORT" if side == 1 else "LONG",
        "side": side,
        "source": f"lab:{et}",
        "price_at_signal": entry,
        "agent_audit_context": {"scar": {}, "nexus15": {}},
    }
    if mode_flag:
        cand[mode_flag] = True
    else:
        cand["estimated_range_pct"] = round(sl_dist / entry * 100 * strat["rr_mult"], 4)
    if historical_daily_change_pct is not None:
        cand["historical_daily_change_pct"] = historical_daily_change_pct
    return cand


BE_LOCK_ENABLED = False  # se activa por llamada via backtest_strategy(..., be_lock=True)
BE_LOCK_TP_PCT = 75


def backtest_strategy(conn, basket, strat, apply_vetos=True, be_lock=False):
    global BE_LOCK_ENABLED
    BE_LOCK_ENABLED = be_lock
    all_trades = []
    for symbol in basket:
        rows = load_15m(conn, symbol)
        if len(rows) < 3000:
            continue
        candles = resample(rows, strat["tf_min"]) if strat["tf_min"] != 15 else rows
        if len(candles) < 250:
            continue
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        volumes = [c[5] for c in candles]
        atr = atr_series(candles, 14)

        lb = strat["lookback"]
        open_trade = None
        for i in range(210, len(candles)):
            ts, o, h, l, c, v = candles[i]
            a = atr[i]
            if a is None or a <= 0:
                continue
            if open_trade:
                side = open_trade["side"]

                # 2026-08-18: lock a breakeven, candle-a-candle (no post-hoc) --
                # replica exacta de la regla de SimulationMarkPriceWorker.cs
                # (desactivada en produccion hasta validar esto). Una sola vez
                # por trade: si el precio mas favorable de ESTA vela llego a
                # BE_LOCK_TP_PCT% del camino al TP, sube el SL a breakeven+fee.
                # Ambiguedad de vela unica: usa el extremo favorable de la MISMA
                # vela que despues chequea TP/SL -- mismo sesgo que ya existe en
                # hit_tp/hit_sl (evaluados con OR, sin orden intra-vela real),
                # asi que el resultado puede ser levemente optimista.
                if BE_LOCK_ENABLED and not open_trade.get("be_locked"):
                    entry = open_trade["entry"]
                    tp = open_trade["tp"]
                    tp_range = (tp - entry) if side == 0 else (entry - tp)
                    if tp_range > 0:
                        favorable_price = h if side == 0 else l
                        progress_pct = ((favorable_price - entry) if side == 0 else (entry - favorable_price)) / tp_range * 100
                        if progress_pct >= BE_LOCK_TP_PCT:
                            buffer = entry * 0.0015
                            new_sl = entry + buffer if side == 0 else entry - buffer
                            improves = (new_sl > open_trade["sl"]) if side == 0 else (new_sl < open_trade["sl"])
                            if improves:
                                open_trade["sl"] = new_sl
                            open_trade["be_locked"] = True

                hit_tp = (l <= open_trade["tp"]) if side == 1 else (h >= open_trade["tp"])
                hit_sl = (h >= open_trade["sl"]) if side == 1 else (l <= open_trade["sl"])
                if hit_tp or hit_sl:
                    close_px = open_trade["tp"] if hit_tp else open_trade["sl"]
                    qty = MARGIN / open_trade["entry"]
                    gross = qty * (open_trade["entry"] - close_px) if side == 1 else qty * (close_px - open_trade["entry"])
                    fees = (qty * open_trade["entry"] + qty * close_px) * FEE
                    all_trades.append({
                        "symbol": symbol, "pnl": gross - fees,
                        "open_time": open_trade["open_time"], "close_time": ts,
                    })
                    open_trade = None
                continue

            level_high = max(highs[i - lb:i]) if i >= lb else None
            level_low = min(lows[i - lb:i]) if i >= lb else None
            sig = detect_signal(strat, closes, highs, lows, i, level_high, level_low, volumes)
            if sig is None:
                continue
            if strat["side"] == "LONG" and sig != 0:
                continue
            if strat["side"] == "SHORT" and sig != 1:
                continue

            entry = c
            sl_dist = strat["atr_sl_mult"] * a
            tp_dist = sl_dist * strat["rr_mult"]
            if sig == 0:
                sl, tp = entry - sl_dist, entry + tp_dist
            else:
                sl, tp = entry + sl_dist, entry - tp_dist

            if apply_vetos:
                # Cambio real de 24h HISTORICO (velas atras = 1440min/tf_min),
                # no el de Binance en vivo -- ver fix 2026-08-18 en setup_validator.py.
                candles_per_day = max(1, int(1440 / strat["tf_min"]))
                if i >= candles_per_day and closes[i - candles_per_day]:
                    hist_daily_pct = (entry - closes[i - candles_per_day]) / closes[i - candles_per_day] * 100
                else:
                    hist_daily_pct = 0.0
                candidate = _build_validate_candidate(strat, symbol, sig, entry, sl_dist, hist_daily_pct)
                try:
                    v_ok, _v_code, _ = validate_pre_trade(candidate, entry, profile=None, btc_filter=None, btc_corr=None)
                except Exception:
                    v_ok = True  # fail-open si algo no se puede evaluar offline
                if not v_ok:
                    continue

            open_trade = {"side": sig, "entry": entry, "sl": sl, "tp": tp, "open_time": ts}

    return _apply_capital_sim(all_trades)


def _apply_capital_sim(trades):
    """Limite REAL de SLOTS posiciones simultaneas -- mismo algoritmo
    greedy que _capital_sim en engine.py. Se aplica SIEMPRE, no es
    opcional: es la regla mas basica del sistema real (config.py
    MAX_OPEN_POSITIONS=3) y el bug mas grave que tenia el lab."""
    trades = sorted(trades, key=lambda t: (t["open_time"], t["symbol"]))
    open_slots, accepted = [], []
    for t in trades:
        open_slots = [ct for ct in open_slots if ct > t["open_time"]]
        if len(open_slots) >= SLOTS:
            continue
        open_slots.append(t["close_time"])
        accepted.append(t)
    return accepted


def evaluate(all_trades, days_covered):
    """
    SIEMPRE devuelve el detalle completo (n, WR, PnL, $/mes, por mitad) de
    CUALQUIER estrategia con datos suficientes -- pedido explicito del
    usuario 2026-08-11: "TODO debemos saber de cada una", no solo las que
    pasan el filtro. `passes_bar` marca si además cumple los criterios
    duros (positiva en ambas mitades, mitades parejas -- evita el mismo
    problema de decadencia que ya vimos con MA Slope Caso 3, donde el
    edge se desinflaba con el tiempo en vez de sostenerse) y el umbral de
    $/mes. La lista completa, pase o no, queda en lab_tested_all.jsonl.
    """
    n = len(all_trades)
    if n < MIN_TRADES_PER_HALF * 2:
        return {"n": n, "insufficient_data": True}

    all_trades.sort(key=lambda t: t["open_time"])
    half = n // 2
    h1, h2 = all_trades[:half], all_trades[half:]

    wr = sum(1 for t in all_trades if t["pnl"] > 0) / n * 100
    pnl1, pnl2 = sum(t["pnl"] for t in h1), sum(t["pnl"] for t in h2)
    wr1 = sum(1 for t in h1 if t["pnl"] > 0) / len(h1) * 100 if h1 else 0
    wr2 = sum(1 for t in h2 if t["pnl"] > 0) / len(h2) * 100 if h2 else 0
    total = pnl1 + pnl2
    monthly = total / (days_covered / 30.44) if days_covered > 0 else 0
    avg_pnl_trade = total / n if n else 0

    lo, hi = min(pnl1, pnl2), max(pnl1, pnl2)
    stable = hi > 0 and lo >= hi * 0.4
    both_positive = pnl1 > 0 and pnl2 > 0
    enough_per_half = len(h1) >= MIN_TRADES_PER_HALF and len(h2) >= MIN_TRADES_PER_HALF
    passes_bar = both_positive and stable and enough_per_half and monthly >= BAR_MONTHLY_USD

    return {
        "n": n, "wr_pct": round(wr, 2), "pnl_total": round(total, 2),
        "monthly": round(monthly, 2), "avg_pnl_per_trade": round(avg_pnl_trade, 4),
        "n_h1": len(h1), "n_h2": len(h2),
        "pnl_h1": round(pnl1, 2), "pnl_h2": round(pnl2, 2),
        "wr_h1": round(wr1, 2), "wr_h2": round(wr2, 2),
        "stable_between_halves": stable, "both_halves_positive": both_positive,
        "passes_bar": passes_bar,
    }


def strat_label(strat):
    et = strat["entry_type"]
    tf = f'{strat["tf_min"]}m'
    side = strat["side"]
    if et == "ma_cross":
        f, s = strat["ma_pair"]
        core = f"MA Cross {f}/{s}"
    elif et == "level_sweep":
        core = f"Level Sweep lb{strat['lookback']}"
    elif et == "band_touch":
        core = "Band Touch"
    elif et == "rsi_extreme":
        hi, lo = strat["rsi_thresh"]
        core = f"RSI Extreme {hi}/{lo}"
    elif et == "ma_pullback":
        vol_tag = f" vol{strat['volume_mult']}x" if strat.get("volume_mult", 1.0) > 1.0 else ""
        core = f"MA Pullback lb{strat['lookback']} slope{strat['slope_min_pct']}%{vol_tag}"
    else:
        core = et
    return f"{core} {tf} {side} SL{strat['atr_sl_mult']}x RR{strat['rr_mult']}"


def write_current(tried, found, strat=None, t_start=None, days_covered=None):
    """
    2026-08-16: causa real de que el lab se "colgara" de la nada mas de
    una vez -- os.replace() en Windows tira PermissionError si otro
    proceso (el container Docker, por el bind mount de /app/backtest)
    tiene el archivo destino abierto en ese instante. Antes esto no
    estaba en un try/except y tumbaba TODO el loop principal sin dejar
    traceback visible salvo en lab_stdout.log. El heartbeat es
    best-effort: si esta escritura falla, se salta esta iteracion y
    listo -- nunca debe poder matar el proceso.
    """
    payload = {
        "heartbeat": datetime.now(timezone.utc).isoformat(),
        "tried": tried,
        "found": found,
        "current_label": strat_label(strat) if strat else None,
        "current_strat": strat,
        "elapsed_sec": round(time.time() - t_start, 1) if t_start else None,
        "days_covered": round(days_covered, 1) if days_covered else None,
    }
    tmp_path = CURRENT_PATH + f".tmp{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, CURRENT_PATH)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def main():
    conn = sqlite3.connect(DB_PATH)
    basket_full = load_basket(conn)
    # 2026-08-16: antes truncaba a los primeros 150 (35% de los 422 con
    # historia suficiente) sin ninguna razon rigurosa -- quedo de la
    # primera corrida overnight y nunca se revisó. Ahora usa la canasta
    # completa (backtest_strategy ya filtra sola los que no llegan a 3000
    # velas de 15m); cada estrategia tarda ~2.8x mas pero cubre TODO el
    # universo de simbolos con historia util, no solo un subconjunto
    # arbitrario.
    basket = basket_full

    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days_covered = (t1 - t0) / (1000 * 60 * 60 * 24) if t0 and t1 else 240

    tried = 0
    found = 0
    t_start = time.time()
    while True:
        # 2026-08-16: el loop entero va envuelto en try/except -- el
        # proceso murio en silencio mas de una vez (una vez sin traceback
        # visible, otra por el PermissionError de write_current en
        # Windows) y esta pensado para correr sin supervision indefinida.
        # Cualquier excepcion de UNA iteracion se loguea y se sigue con la
        # proxima estrategia en vez de tirar abajo todo el proceso.
        try:
            strat = random_strategy()
            write_current(tried, found, strat, t_start, days_covered)
            trades = backtest_strategy(conn, basket, strat)
            result = evaluate(trades, days_covered)
            tried += 1

            # SIEMPRE se guarda el detalle completo, pase o no el filtro --
            # "TODO debemos saber de cada una" (pedido explicito 2026-08-11).
            row = {"strat": strat, "result": result, "ts": datetime.now(timezone.utc).isoformat()}
            with open(TESTED_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

            if result.get("passes_bar"):
                found += 1
                with open(FOUND_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
                print(
                    f"[LAB] *** ENCONTRADA #{found} *** {strat} -> ${result['monthly']}/mes | "
                    f"WR={result['wr_pct']}% | n={result['n']} | mitades: ${result['pnl_h1']}/${result['pnl_h2']}",
                    flush=True,
                )

            if tried % 10 == 0:
                elapsed = time.time() - t_start
                with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now(timezone.utc).isoformat()} | probadas={tried} | encontradas={found} | "
                            f"basket={len(basket)} simbolos | {elapsed/tried:.1f}s/estrategia\n")
        except Exception as e:
            print(f"[LAB] *** ERROR en iteracion (tried={tried}), continuando *** {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
