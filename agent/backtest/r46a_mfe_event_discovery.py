"""
ROUND 46a -- descubrimiento event-driven: agrega MFE/MAE real (path
completo del trade, no solo el resultado final tp/sl) + features de
TRANSICION (aceleracion, compresion previa, sorpresa de volumen) al
dataset de R45, y bucketiza trades por el TAMANO del movimiento que
produjeron, no solo por si ganaron o perdieron.

Reutiliza el dataset ya reconstruido en R45 (mismo universo, mismo
metodo causal) -- no vuelve a bajar nada, solo re-abre las klines para
calcular MFE/MAE y las features de transicion adicionales.
"""
import os, sys, json, sqlite3
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
DATA = os.path.join(HERE, "..", "..", "scratch_r45_dataset.json")
OUT = os.path.join(HERE, "..", "..", "scratch_r46_dataset.json")


def load_symbol_klines(con, symbol):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)).fetchall()
    if len(k) < 200:
        return None
    t = np.array([r[0] for r in k], np.int64)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float)
    c = np.array([r[4] for r in k], float); v = np.array([r[5] for r in k], float)
    return dict(t=t, h=h, l=l, c=c, v=v)


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def mfe_mae_path(d, i_entry, ts_close_ms, side, entry_px):
    """MFE/MAE del PATH REAL del trade (entrada->cierre real), en bp.
    Tambien devuelve el bar-index del maximo MFE (para timing)."""
    t, h, l = d["t"], d["h"], d["l"]
    j_end = np.searchsorted(t, ts_close_ms, side="right")
    j_start = i_entry + 1
    if j_end <= j_start or j_end > len(h):
        return None
    if side == 1:
        favorable = h[j_start:j_end] - entry_px
        adverse = l[j_start:j_end] - entry_px
    else:
        favorable = entry_px - l[j_start:j_end]
        adverse = entry_px - h[j_start:j_end]
    if len(favorable) == 0:
        return None
    mfe_idx = int(np.argmax(favorable))
    mfe = favorable[mfe_idx] / entry_px * 1e4
    mae = adverse.min() / entry_px * 1e4
    bars_to_mfe = mfe_idx + 1
    return mfe, mae, bars_to_mfe


def transition_feats(d, i):
    """Features de TRANSICION (no solo nivel): aceleracion, compresion
    previa a la entrada, sorpresa de volumen -- todas causales (bar i
    inclusive, la ultima cerrada antes de la entrada)."""
    c, h, l, v = d["c"], d["h"], d["l"], d["v"]
    if i < 105:
        return None
    def ret(n):
        return (c[i] - c[i - n]) / c[i - n] if i >= n and c[i - n] != 0 else np.nan
    ret3, ret10, ret20 = ret(3), ret(10), ret(20)
    accel_3_10 = ret3 - ret10 / (10 / 3) if np.isfinite(ret3) and np.isfinite(ret10) else np.nan  # momentum reciente vs promedio del tramo largo, normalizado por escala temporal

    # compresion: ATR relativo de las ultimas 10 barras vs las 30 previas
    trs_now = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(i - 9, i + 1)]
    trs_prev = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(i - 39, i - 9)]
    atr_now = np.mean(trs_now) / c[i]; atr_prev = np.mean(trs_prev) / c[i] if c[i] > 0 else np.nan
    compression_ratio = atr_now / atr_prev if atr_prev and atr_prev > 0 else np.nan  # <1 = se comprimio, >1 = se expandio justo antes

    # sorpresa de volumen: vol de las ultimas 3 barras vs las 20 previas
    vol_recent = np.mean(v[i - 2:i + 1]); vol_base = np.mean(v[i - 22:i - 2])
    vol_surge = vol_recent / vol_base if vol_base and vol_base > 0 else np.nan

    # distancia a extremo de 50 barras (para detectar "rechazo de extremo")
    hi50 = h[max(0, i - 50):i + 1].max(); lo50 = l[max(0, i - 50):i + 1].min()
    rng50 = hi50 - lo50
    pos_in_range50 = (c[i] - lo50) / rng50 if rng50 > 0 else np.nan  # 0=en el minimo, 1=en el maximo

    # velocidad del retroceso/pullback: signo de ret_3 vs signo de ret_20 (contra-tendencia de corto plazo)
    pullback_vs_trend = np.nan
    if np.isfinite(ret3) and np.isfinite(ret20) and ret20 != 0:
        pullback_vs_trend = 1.0 if (np.sign(ret3) != np.sign(ret20) and abs(ret20) > 0.01) else 0.0

    return dict(accel_3_10=accel_3_10, compression_ratio=compression_ratio, vol_surge=vol_surge,
                pos_in_range50=pos_in_range50, pullback_vs_trend=pullback_vs_trend,
                ret3=ret3, ret10=ret10, ret20=ret20)


def main():
    with open(DATA) as f:
        rows = json.load(f)
    print(f"Trades base (de R45): {len(rows)}")

    syms = sorted(set(r["symbol"] for r in rows))
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    kdata = {}
    for s in syms:
        d = load_symbol_klines(con, s)
        if d is not None:
            kdata[s] = d
    con.close()
    print(f"Simbolos con klines: {len(kdata)}/{len(syms)}")

    enriched = []
    skipped = 0
    for r in rows:
        d = kdata.get(r["symbol"])
        if d is None:
            skipped += 1
            continue
        i = find_bar_index(d["t"], r["ts"])
        if i is None:
            skipped += 1
            continue
        ts_close = int(np.datetime64(r["closed"]).astype("datetime64[ms]").astype(np.int64))
        mm = mfe_mae_path(d, i, ts_close, r["side"], r["entry_px"])
        tf = transition_feats(d, i)
        if mm is None or tf is None:
            skipped += 1
            continue
        mfe, mae, bars_to_mfe = mm
        rr = dict(r)
        rr.update(mfe=mfe, mae=mae, bars_to_mfe=bars_to_mfe, **tf)
        enriched.append(rr)

    print(f"Trades enriquecidos con MFE/MAE + transicion: {len(enriched)}  (descartados: {skipped})")
    with open(OUT, "w") as fo:
        json.dump(enriched, fo, default=str)
    print(f"Guardado: {OUT}")

    # ---- reporte rapido de bucketizacion por MFE ----
    mfe = np.array([r["mfe"] for r in enriched])
    win = np.array([r["win"] for r in enriched])
    print("\n=== BUCKETIZACION POR EXCURSION (no solo win/loss) ===")
    big_win = [r for r in enriched if r["win"] and r["mfe"] >= 300]
    normal_win = [r for r in enriched if r["win"] and r["mfe"] < 300]
    reversal_loss = [r for r in enriched if not r["win"] and r["mfe"] >= 100]
    immediate_loss = [r for r in enriched if not r["win"] and r["mfe"] < 30]
    small_mfe_loss = [r for r in enriched if not r["win"] and 30 <= r["mfe"] < 100]
    print(f"  Grandes ganadores (win, MFE>=300bp): {len(big_win)}")
    print(f"  Ganadores normales (win, MFE<300bp): {len(normal_win)}")
    print(f"  Perdidas con reversion (loss, MFE>=100bp antes de caer): {len(reversal_loss)}")
    print(f"  Perdidas con MFE chico (loss, 30<=MFE<100bp): {len(small_mfe_loss)}")
    print(f"  Perdidas inmediatas (loss, MFE<30bp): {len(immediate_loss)}")


if __name__ == "__main__":
    main()
