"""
ROUND 34 — 13 setups de price action / medias moviles, 1H, reglas 100%
mecanicas (ver SETUPS_ROUND34_SPEC.md para la especificacion completa en
lenguaje natural). Este script las traduce a codigo, corre TRAIN screen,
VAL confirma, OOS valida, con costo real y stop/TP mecanico via barrido
intrabar (igual metodo que R33: first_touch).

Convenciones compartidas:
  - Barras horarias agregadas de klines_clean 15m (causal: o=primera,
    h=max, l=min, c=ultima de cada hora).
  - MA7/25/50/99 = SMA de cierre horario.
  - slope(MA,i,k) = MA[i]-MA[i-k].
  - ATR14 = SMA(TrueRange,14).
  - Entrada = open de la hora siguiente al evento+confirmacion.
  - Stop = 1.5*ATR14 (en la barra de señal), TP = 2R, horizonte de
    tiempo-limite = 72h. Barrido intrabar con precision horaria (no 15m)
    -- limitacion declarada explicitamente, ver informe.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r15_wide_discovery import universe
from r7_common import agg_pairs
from r12_smartmoney import pctile_causal
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST_RT_BP = 24.0
TIME_LIMIT_H = 72
ROLL_H = 720   # 30 dias en horas, para percentiles causales


def load_hourly(con, s):
    k = con.execute("SELECT open_time,open,high,low,close FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
    if len(k) < 5000:
        return None
    t = np.array([r[0] for r in k], np.int64); o = np.array([r[1] for r in k], float)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
    hour = t // 3600000
    uniq, idx_start = np.unique(hour, return_index=True)
    if len(uniq) < ROLL_H + 200:
        return None
    n = len(uniq)
    ho = np.empty(n); hh = np.empty(n); hl = np.empty(n); hc = np.empty(n); ht = np.empty(n, np.int64)
    bounds = list(idx_start) + [len(hour)]
    for j in range(n):
        a, b = bounds[j], bounds[j + 1]
        ho[j] = o[a]; hh[j] = h[a:b].max(); hl[j] = l[a:b].min(); hc[j] = c[b - 1]; ht[j] = hour[a] * 3600000
    return dict(t=ht, o=ho, h=hh, l=hl, c=hc)


def sma(arr, w):
    n = len(arr); out = np.full(n, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(arr)])
    for i in range(w - 1, n):
        out[i] = (cs[i + 1] - cs[i + 1 - w]) / w
    return out


def compute_feats(d):
    c = d["c"]; h = d["h"]; l = d["l"]; o = d["o"]; n = len(c)
    ma7 = sma(c, 7); ma25 = sma(c, 25); ma50 = sma(c, 50); ma99 = sma(c, 99)
    prevc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prevc), np.abs(l - prevc)))
    atr14 = sma(tr, 14)
    return dict(ma7=ma7, ma25=ma25, ma50=ma50, ma99=ma99, atr14=atr14)


def slope(ma, i, k):
    if i - k < 0 or not (np.isfinite(ma[i]) and np.isfinite(ma[i - k])):
        return np.nan
    return ma[i] - ma[i - k]


def first_touch_h(hi, lo, tp_px, sl_px, side):
    if side > 0:
        tp_hits = hi >= tp_px; sl_hits = lo <= sl_px
    else:
        tp_hits = lo <= tp_px; sl_hits = hi >= sl_px
    tp_i = np.argmax(tp_hits) if tp_hits.any() else None
    sl_i = np.argmax(sl_hits) if sl_hits.any() else None
    if tp_i is None and sl_i is None:
        return "time", None
    if tp_i is None:
        return "sl", sl_i
    if sl_i is None:
        return "tp", tp_i
    if tp_i < sl_i:
        return "tp", tp_i
    if sl_i < tp_i:
        return "sl", sl_i
    return "tie", tp_i


def simulate(d, i, side):
    """entrada en open[i+1], stop=1.5*ATR14[i], TP=2R, limite=72h. Devuelve r_bp neto de costo, o None si no simulable."""
    f = d["_feats"]; atr = f["atr14"][i]
    if not np.isfinite(atr) or atr <= 0:
        return None
    o = d["o"]; h = d["h"]; l = d["l"]; n = len(o)
    e = i + 1
    if e + TIME_LIMIT_H >= n:
        return None
    entry = o[e]
    R = 1.5 * atr
    sl_px = entry - side * R
    tp_px = entry + side * 2 * R
    hi_w = h[e:e + TIME_LIMIT_H]; lo_w = l[e:e + TIME_LIMIT_H]
    res, idx = first_touch_h(hi_w, lo_w, tp_px, sl_px, side)
    if res == "tp":
        r_bp = side * math.log(tp_px / entry) * 1e4
    elif res == "sl":
        r_bp = side * math.log(sl_px / entry) * 1e4
    elif res == "tie":
        r_bp = 0.0
    else:
        exit_px = o[e + TIME_LIMIT_H]
        r_bp = side * math.log(exit_px / entry) * 1e4
    return r_bp - COST_RT_BP


# ---------------------------------------------------------------------
# 13 detectores de eventos. Cada uno devuelve (i, side) para las barras
# donde el setup dispara (evento+confirmacion ya cumplidos en la barra i).
# ---------------------------------------------------------------------

def detect_setup1(d, f, i, slope_pctile):
    ma7, ma25, ma99 = f["ma7"], f["ma25"], f["ma99"]
    if i < 15 or not all(np.isfinite(x[i]) for x in (ma7, ma25, ma99)):
        return False
    if not (ma7[i] < ma25[i] and ma7[i] < ma99[i]):
        return False
    if not (slope(ma25, i, 10) is not None and np.isfinite(slope(ma25, i, 10)) and slope(ma25, i, 10) < 0):
        return False
    s3 = slope(ma7, i, 3)
    if not (np.isfinite(s3) and s3 > 0):
        return False
    for k in range(0, 3):
        j = i - k
        if j < 1:
            continue
        if d["h"][j] >= ma25[j] and d["c"][j] < ma25[j]:
            return True
    return False


def detect_setup2(d, f, i, slope_pctile):
    ma7, ma25, ma50, ma99 = f["ma7"], f["ma25"], f["ma50"], f["ma99"]
    if i < 5 or not all(np.isfinite(x[i]) for x in (ma7, ma25, ma50, ma99)):
        return False
    if not (ma7[i] > ma99[i] and ma7[i] < ma25[i] and ma7[i] < ma50[i]):
        return False
    s2 = slope(ma7, i, 2)
    if not (np.isfinite(s2) and s2 < 0):
        return False
    if not (d["l"][i] <= ma99[i] <= d["h"][i]):
        return False
    return d["c"][i] > ma99[i]


def detect_setup3(d, f, i, slope_pctile):
    ma7, ma25, ma50, ma99 = f["ma7"], f["ma25"], f["ma50"], f["ma99"]
    if i < 8 or not all(np.isfinite(x[i]) for x in (ma7, ma25, ma50, ma99)):
        return False
    if not (ma7[i - 2] > ma25[i - 2] > ma50[i - 2] > ma99[i - 2]):
        return False
    window = ma7[i - 6:i - 1]
    if len(window) < 4 or not np.isfinite(window).all():
        return False
    if ma7[i - 2] < window.max():
        return False
    s2 = slope(ma7, i, 2)
    if not np.isfinite(s2) or i not in range(len(slope_pctile)):
        return False
    thr = slope_pctile[i]
    if not (np.isfinite(thr) and s2 < -thr):
        return False
    return d["c"][i] < d["o"][i]


def detect_setup4(d, f, i, slope_pctile):
    ma7, ma25, ma50, ma99 = f["ma7"], f["ma25"], f["ma50"], f["ma99"]
    if i < 30 or not all(np.isfinite(x[i]) for x in (ma7, ma25, ma50, ma99)):
        return False
    if not (ma7[i] > ma25[i] > ma50[i] > ma99[i]):
        return False
    if not (slope(ma7, i, 5) > 0 and slope(ma25, i, 5) > 0):
        return False
    if not (d["l"][i] <= ma25[i] <= d["h"][i] and d["c"][i] > ma25[i]):
        return False
    prev8_touch = any(d["l"][i - k] <= ma25[i - k] for k in range(1, 9))
    return not prev8_touch


def detect_setup6(d, f, i, slope_pctile):
    ma25 = f["ma25"]
    if i < 6 or not np.isfinite(ma25[i]):
        return False
    if not (d["c"][i] < ma25[i]):
        return False
    broke_idx = None
    for k in range(1, 5):
        j = i - k
        if j < 1:
            continue
        if d["c"][j] < ma25[j] and d["c"][j - 1] >= ma25[j - 1]:
            broke_idx = j; break
    if broke_idx is None or broke_idx == i:
        return False
    retest_high = d["h"][broke_idx + 1:i + 1]
    if len(retest_high) == 0 or retest_high.max() < ma25[broke_idx]:
        return False
    return d["c"][i] < d["o"][i] and d["l"][i] < d["l"][broke_idx]


def detect_setup7(d, f, i, slope_pctile):
    ma7, ma25, ma50 = f["ma7"], f["ma25"], f["ma50"]
    if i < 2 or not all(np.isfinite(x[i]) for x in (ma7, ma25, ma50)):
        return False
    if not (ma7[i] > ma25[i] > ma50[i]):
        return False
    j = i - 1
    if not (np.isfinite(ma25[j]) and d["c"][j] < ma25[j]):
        return False
    if not (d["c"][i] > ma25[i]):
        return False
    rng_break = d["h"][j] - d["l"][j]
    rng_rec = d["h"][i] - d["l"][i]
    return rng_break > 0 and rng_rec >= 0.7 * rng_break


def detect_setup8(d, f, i, dist_pctile, range_pctile):
    ma7, ma25, ma50 = f["ma7"], f["ma25"], f["ma50"]
    if i < 6 or not all(np.isfinite(x[i]) for x in (ma7, ma25, ma50)):
        return None
    dpct = dist_pctile[i]
    if not (np.isfinite(dpct) and dpct <= 0.15):
        return None
    for k in range(6):
        j = i - k
        if j < 0 or not np.isfinite(dist_pctile[j]) or dist_pctile[j] > 0.20:
            return None
    rpct = range_pctile[i]
    if not (np.isfinite(rpct) and rpct >= 0.90):
        return None
    rng = d["h"][i] - d["l"][i]
    if rng <= 0:
        return None
    close_pos = (d["c"][i] - d["l"][i]) / rng
    if close_pos >= 0.75:
        return 1
    if close_pos <= 0.25:
        return -1
    return None


def detect_setup10(d, f, i, slope_pctile):
    ma7, ma25 = f["ma7"], f["ma25"]
    if i < 6:
        return False
    j = i - 1
    if not (np.isfinite(ma7[j]) and np.isfinite(ma25[j]) and np.isfinite(ma7[j - 1]) and np.isfinite(ma25[j - 1])):
        return False
    crossed = ma7[j] > ma25[j] and ma7[j - 1] <= ma25[j - 1]
    if not crossed:
        return False
    prevhigh = d["h"][max(0, j - 5):j].max()
    newhigh_after = max(d["h"][j], d["h"][i])
    if newhigh_after > prevhigh:
        return False
    return d["c"][i] < d["o"][i]


def detect_setup11(d, f, i, slope_pctile):
    ma25, ma50, ma99 = f["ma25"], f["ma50"], f["ma99"]
    if i < 20 or not all(np.isfinite(x[i]) for x in (ma25, ma50, ma99)):
        return False
    if not (ma25[i] > ma50[i] > ma99[i]):
        return False
    for k in range(15):
        j = i - k
        if j < 15 or slope(ma25, j, 3) is None or not np.isfinite(slope(ma25, j, 3)) or slope(ma25, j, 3) <= 0:
            return False
        if slope(ma50, j, 3) is None or not np.isfinite(slope(ma50, j, 3)) or slope(ma50, j, 3) <= 0:
            return False
    cross_idx = None
    for k in range(1, 4):
        j = i - k
        if j < 1:
            continue
        if d["c"][j] < ma25[j] and d["c"][j - 1] >= ma25[j - 1]:
            cross_idx = j; break
    if cross_idx is None:
        return False
    return d["c"][i] > ma25[i]


def detect_setup12(d, f, i, slope_pctile):
    ma7, ma50, ma99 = f["ma7"], f["ma50"], f["ma99"]
    if i < 22:
        return False
    for k in range(20):
        j = i - k
        if j < 1:
            return False
        s = slope(ma50, j, 3); s2 = slope(ma99, j, 3)
        if s is None or not np.isfinite(s) or s <= 0 or s2 is None or not np.isfinite(s2) or s2 <= 0:
            return False
    had_neg = any(np.isfinite(slope(ma7, i - k, 2)) and slope(ma7, i - k, 2) < 0 for k in range(1, 6))
    if not had_neg:
        return False
    s_now = slope(ma7, i, 2)
    if not (np.isfinite(s_now) and s_now > 0):
        return False
    if not np.isfinite(ma50[i]) or d["c"][i] <= ma50[i]:
        return False
    for k in range(6):
        j = i - k
        if j < 0 or d["c"][j] <= ma50[j]:
            return True
    return True


def detect_setup13(d, f, i, dist2_pctile):
    ma25, ma50, ma99 = f["ma25"], f["ma50"], f["ma99"]
    if i < 15 or not all(np.isfinite(x[i]) for x in (ma25, ma50, ma99)):
        return False
    if not (slope(ma99, i, 10) > 0):
        return False
    dp = dist2_pctile[i]
    if not (np.isfinite(dp) and dp <= 0.20):
        return False
    lo_ma = min(ma25[i], ma50[i]); hi_ma = max(ma25[i], ma50[i])
    if not (d["l"][i] <= hi_ma and d["h"][i] >= lo_ma):
        return False
    return d["c"][i] > hi_ma


def main():
    print("=== ROUND 34 — 13 SETUPS DE MEDIAS MOVILES (1H) ===\n")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}
    for s in syms:
        d = load_hourly(con, s)
        if d is None:
            continue
        d["_feats"] = compute_feats(d)
        P[s] = d
    con.close()
    print(f"universo: {len(P)} simbolos con >= {ROLL_H+200} horas de historia\n")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")

    # slope percentile causal de MA7 (para setup3), distancia MA7-25-50 (setup8/9), distancia MA25-MA50 (setup13)
    for s, d in P.items():
        f = d["_feats"]; ma7 = f["ma7"]
        s2 = np.full(len(ma7), np.nan)
        for i in range(2, len(ma7)):
            v = slope(ma7, i, 2)
            s2[i] = abs(v) if np.isfinite(v) else np.nan
        f["ma7_slope_abs_pct"] = pctile_causal(np.nan_to_num(s2, nan=0.0), ROLL_H)
        f["ma7_slope_abs_pct"][~np.isfinite(s2)] = np.nan
        f["slope_thr"] = np.full(len(ma7), np.nan)  # se resuelve via percentil directo abajo (se usa distinto approach)

        c = d["c"]
        dist379 = np.where(np.isfinite(f["ma7"]) & np.isfinite(f["ma25"]) & np.isfinite(f["ma50"]) & (c > 0),
                            (np.maximum.reduce([f["ma7"], f["ma25"], f["ma50"]]) - np.minimum.reduce([f["ma7"], f["ma25"], f["ma50"]])) / c, np.nan)
        f["dist_ma_pct"] = pctile_causal(np.nan_to_num(dist379, nan=0.0), ROLL_H)
        f["dist_ma_pct"][~np.isfinite(dist379)] = np.nan

        rng = d["h"] - d["l"]
        rngp = np.where(c > 0, rng / c, np.nan)
        f["range_pct"] = pctile_causal(np.nan_to_num(rngp, nan=0.0), ROLL_H)
        f["range_pct"][~np.isfinite(rngp)] = np.nan

        dist2 = np.where(np.isfinite(f["ma25"]) & np.isfinite(f["ma50"]) & (c > 0),
                          np.abs(f["ma25"] - f["ma50"]) / c, np.nan)
        f["dist25_50_pct"] = pctile_causal(np.nan_to_num(dist2, nan=0.0), ROLL_H)
        f["dist25_50_pct"][~np.isfinite(dist2)] = np.nan

    # umbral de "pendiente rapida" (setup3): valor absoluto en precio real, no percentil de por si -- usar la
    # magnitud misma del percentil 80 rolling de |slope| como threshold dinamico
    def slope_thr_arr(d):
        f = d["_feats"]; ma7 = f["ma7"]; n = len(ma7)
        raw = np.full(n, np.nan)
        for i in range(2, n):
            v = slope(ma7, i, 2)
            raw[i] = abs(v) if np.isfinite(v) else np.nan
        thr = np.full(n, np.nan)
        for i in range(ROLL_H, n):
            window = raw[i - ROLL_H:i]
            window = window[np.isfinite(window)]
            if len(window) > 100:
                thr[i] = np.percentile(window, 80)
        return thr

    detectors_simple = {
        "1-giro_MA7_pullback_MA25": (detect_setup1, 1),
        "2-MA7_toca_MA99_soporte": (detect_setup2, 1),
        "4-pullback_MA25_rechazo": (detect_setup4, 1),
        "6-ruptura_MA25_retest_fallido": (detect_setup6, -1),
        "7-falsa_ruptura_MA25_recupera": (detect_setup7, 1),
        "10-cruce_MA7_sin_confirmacion_fade": (detect_setup10, -1),
        "11-precio_cruza_MA25_estructura_aguanta": (detect_setup11, 1),
        "12-giro_MA7_2da_vez_tendencia_fondo": (detect_setup12, 1),
    }

    print("Calculando thresholds de pendiente rapida (setup 3)...")
    thr_by_sym = {s: slope_thr_arr(d) for s, d in P.items()}

    results = []

    def run_detector(label, fn, side_fixed, extra=None):
        events = []
        for s, d in P.items():
            f = d["_feats"]; n = len(d["c"])
            thr = thr_by_sym[s] if extra == "slope" else None
            for i in range(ROLL_H, n - 1):
                dy = datetime.utcfromtimestamp(int(d["t"][i]) / 1000).date()
                try:
                    if extra == "slope":
                        ok = fn(d, f, i, thr)
                    elif extra == "dist2":
                        ok = fn(d, f, i, f["dist25_50_pct"])
                    else:
                        ok = fn(d, f, i, None)
                except Exception:
                    ok = False
                if ok:
                    events.append((s, i, dy))
        print(f"  {label}: eventos={len(events)}")
        if len(events) < 100:
            print("    insuficiente, se salta")
            return
        train_r = []
        for (s, i, dy) in events:
            if seg(dy) != "train":
                continue
            r = simulate(P[s], i, side_fixed)
            if r is not None:
                train_r.append((s, r))
        if len(train_r) < 30:
            print("    TRAIN insuficiente")
            return
        Rt = agg_pairs([(s, r / 1e4) for (s, r) in train_r])
        print(f"    TRAIN: n={Rt.get('n')} mean_net={Rt.get('mean_bp')}bp ci={Rt.get('ci_bp')} ci_excl0={Rt.get('ci_excl_0')}")
        if not Rt.get("ci_excl_0") or (Rt.get("mean_bp") or -1) <= 0:
            print("    TRAIN no confirma -> descartado")
            return
        val_r = [(s, simulate(P[s], i, side_fixed)) for (s, i, dy) in events if seg(dy) == "val"]
        val_r = [(s, r / 1e4) for (s, r) in val_r if r is not None]
        if len(val_r) < 20:
            print("    VAL insuficiente")
            return
        Rv = agg_pairs(val_r)
        print(f"    VAL: n={Rv.get('n')} mean_net={Rv.get('mean_bp')}bp")
        if (Rv.get("mean_bp") or -1) <= 0:
            print("    VAL no confirma -> descartado")
            return
        oos_r = [(s, simulate(P[s], i, side_fixed)) for (s, i, dy) in events if seg(dy) == "oos"]
        oos_r = [(s, r / 1e4) for (s, r) in oos_r if r is not None]
        if len(oos_r) < 20:
            print("    OOS insuficiente")
            return
        Ro = agg_pairs(oos_r)
        print(f"    OOS: n={Ro.get('n')} mean_net={Ro.get('mean_bp')}bp ci_excl0={Ro.get('ci_excl_0')}")
        results.append(dict(label=label, train=Rt, val=Rv, oos=Ro, n_events=len(events)))

    for label, (fn, side) in detectors_simple.items():
        run_detector(label, fn, side)
    run_detector("3-quiebre_rapido_MA7_pico", detect_setup3, -1, extra="slope")
    run_detector("13-rechazo_zona_MA25_50", detect_setup13, 1, extra="dist2")

    # setup 8 (direccion depende del evento, se maneja aparte)
    print("  8-compresion_expansion: eventos=", end="")
    events8 = []
    for s, d in P.items():
        f = d["_feats"]; n = len(d["c"])
        for i in range(ROLL_H, n - 1):
            side = detect_setup8(d, f, i, f["dist_ma_pct"], f["range_pct"])
            if side is not None:
                dy = datetime.utcfromtimestamp(int(d["t"][i]) / 1000).date()
                events8.append((s, i, dy, side))
    print(len(events8))
    if len(events8) >= 100:
        train_r = [(s, simulate(P[s], i, side)) for (s, i, dy, side) in events8 if seg(dy) == "train"]
        train_r = [(s, r / 1e4) for (s, r) in train_r if r is not None]
        if len(train_r) >= 30:
            Rt = agg_pairs(train_r)
            print(f"    TRAIN: n={Rt.get('n')} mean_net={Rt.get('mean_bp')}bp ci_excl0={Rt.get('ci_excl_0')}")
            if Rt.get("ci_excl_0") and (Rt.get("mean_bp") or -1) > 0:
                val_r = [(s, r / 1e4) for (s, r) in [(s, simulate(P[s], i, side)) for (s, i, dy, side) in events8 if seg(dy) == "val"] if r is not None]
                if len(val_r) >= 20:
                    Rv = agg_pairs(val_r)
                    print(f"    VAL: n={Rv.get('n')} mean_net={Rv.get('mean_bp')}bp")
                    if (Rv.get("mean_bp") or -1) > 0:
                        oos_r = [(s, r / 1e4) for (s, r) in [(s, simulate(P[s], i, side)) for (s, i, dy, side) in events8 if seg(dy) == "oos"] if r is not None]
                        if len(oos_r) >= 20:
                            Ro = agg_pairs(oos_r)
                            print(f"    OOS: n={Ro.get('n')} mean_net={Ro.get('mean_bp')}bp ci_excl0={Ro.get('ci_excl_0')}")
                            results.append(dict(label="8-compresion_expansion", train=Rt, val=Rv, oos=Ro, n_events=len(events8)))
                    else:
                        print("    VAL no confirma -> descartado")
            else:
                print("    TRAIN no confirma -> descartado")

    print("\n" + "#" * 70 + "\n RESUMEN FINAL\n" + "#" * 70)
    if not results:
        print("  NINGUN setup sobrevivio TRAIN->VAL->OOS.")
    else:
        for r in results:
            print(f"  {r['label']}: TRAIN={r['train'].get('mean_bp')}bp VAL={r['val'].get('mean_bp')}bp "
                  f"OOS={r['oos'].get('mean_bp')}bp (n_oos={r['oos'].get('n')}) n_eventos_total={r['n_events']}")

    print("\nfin R34")


if __name__ == "__main__":
    main()
