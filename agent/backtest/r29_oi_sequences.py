"""
ROUND 29 — OI EVENT SEQUENCES: Open Interest como disparador PRIMARIO
(no precio/volumen, esa es capitulacion R21-R23, ya cerrada).

Universo Feature-Complete (Fase 0): 43 simbolos con >=120,000 filas de
oi_metrics (~historia completa de 14.5 meses, ver auditoria en el informe).
No se usa forward-fill ni se inventa OI para simbolos sin cobertura.

8 formulaciones predeclaradas (A-H), causales, umbral fijo antes de mirar
resultados. Direccion (long/short) SIEMPRE decidida en TRAIN.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r12_smartmoney import pctile_causal
from r18_discovery import build_feats, ROLL, HOR
from r24_discovery_battery import freeze_direction_train, fwd, placebo
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
MIN_OI_ROWS = 120000
HZ = [("15m", 1), ("1h", 4), ("4h", 16), ("8h", 32), ("24h", 96), ("48h", 192)]


def feature_complete_universe(con):
    rows = con.execute("SELECT symbol, COUNT(*) n FROM oi_metrics GROUP BY symbol HAVING n >= ?", (MIN_OI_ROWS,)).fetchall()
    return sorted(s for s, n in rows)


def load_symbol_oi(con, s):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
    if len(k) < ROLL + 500:
        return None
    kt = np.array([r[0] for r in k], np.int64)
    o = np.array([r[1] for r in k], float); h = np.array([r[2] for r in k], float)
    lo = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
    v = np.array([r[5] for r in k], float)
    pos = {int(t): i for i, t in enumerate(kt)}
    oi = np.full(len(kt), np.nan)
    for ot, so in con.execute("SELECT open_time,sum_oi FROM oi_metrics WHERE symbol=? ORDER BY open_time", (s,)):
        if int(ot) % 900000 != 0:
            continue
        i = pos.get(int(ot))
        if i is not None:
            oi[i] = so
    return dict(t=kt, o=o, h=h, l=lo, c=c, v=v, oi=oi)


def causal_oi_feats(d):
    oi = d["oi"]; n = len(oi)
    valid = np.isfinite(oi)
    # dOI 1-barra (%), solo donde ambos extremos son validos
    dOI = np.full(n, np.nan)
    dOI[1:] = np.where(valid[1:] & valid[:-1] & (oi[:-1] > 0), (oi[1:] - oi[:-1]) / np.where(oi[:-1] > 0, oi[:-1], np.nan), np.nan)
    dOI_pct = pctile_causal(np.nan_to_num(dOI, nan=0.0), ROLL)
    dOI_pct[~np.isfinite(dOI)] = np.nan
    # aceleracion: 2da diferencia de dOI
    d2OI = np.full(n, np.nan)
    d2OI[1:] = dOI[1:] - dOI[:-1]
    d2OI_pct = pctile_causal(np.nan_to_num(d2OI, nan=0.0), ROLL)
    d2OI_pct[~np.isfinite(d2OI)] = np.nan
    return dict(dOI=dOI, dOI_pct=dOI_pct, d2OI_pct=d2OI_pct)


def build_events(P, OIF, F, kind, vol_confirm=None, price_side=None):
    events = []
    for s, d in P.items():
        oif = OIF[s]; f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        dOI_pct = oif["dOI_pct"]; d2OI_pct = oif["d2OI_pct"]; r1p = f["ret1_pct"]; volp = f["vol_pct"]; r1 = f["r1"]
        if kind == "expand":
            mask = np.isfinite(dOI_pct) & (dOI_pct >= 0.97)
        elif kind == "contract":
            mask = np.isfinite(dOI_pct) & (dOI_pct <= 0.03)
        elif kind == "accel":
            mask = np.isfinite(d2OI_pct) & (d2OI_pct >= 0.97)
        elif kind == "shock":
            mask = np.isfinite(dOI_pct) & ((dOI_pct >= 0.97) | (dOI_pct <= 0.03))
        else:
            raise ValueError(kind)
        if vol_confirm:
            mask = mask & np.isfinite(volp) & (volp >= 0.90)
        if price_side == "low":
            mask = mask & np.isfinite(r1p) & (r1p <= 0.30)
        elif price_side == "high":
            mask = mask & np.isfinite(r1p) & (r1p >= 0.70)
        last = -999
        idxs = np.where(mask)[0]
        for i in idxs:
            if i < ROLL or i - last < 4 or i + 1 + HZ[-1][1] >= n:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if (np.isfinite(r1[i]) and r1[i] > 0) else -1.0
            events.append((s, i, dy, ev_sign))
    return events


def eval_battery(P, events, seg, label, horizons=HZ):
    any_signal = False
    for h_lbl, hb in horizons:
        mode, Rc, Rr = freeze_direction_train(P, events, hb, seg)
        if mode is None:
            print(f"  [{label}] h={h_lbl:>3s}: cont={Rc.get('mean_bp')}bp rev={Rr.get('mean_bp')}bp -> sin señal")
            continue
        any_signal = True
        print(f"  [{label}] h={h_lbl:>3s}: cont={Rc.get('mean_bp')}bp(ci0={Rc.get('ci_excl_0')}) rev={Rr.get('mean_bp')}bp(ci0={Rr.get('ci_excl_0')}) -> {mode}")
        for sgv in ("train", "val", "oos"):
            pairs = []
            for (s, i, dy, ev_sign) in events:
                if seg(dy) != sgv:
                    continue
                side = ev_sign if mode == "cont" else -ev_sign
                r = fwd(P, s, i, hb, side)
                if r is not None:
                    pairs.append((s, r))
            if len(pairs) < 30:
                continue
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - COST) if R.get("mean_bp") is not None else None
            print(f"      {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} ci={R.get('ci_bp')} ci_excl0={R.get('ci_excl_0')}")
        ev_vo = [(s, i, dy) for (s, i, dy, ev_sign) in events if seg(dy) in ("val", "oos")]
        side_map = {(s, i): (ev_sign if mode == "cont" else -ev_sign) for (s, i, dy, ev_sign) in events}
        Rp = placebo(P, ev_vo, hb, lambda s, i: side_map.get((s, i), 1))
        if Rp.get("n", 0) >= 30:
            net_p = (Rp["mean_bp"] - COST) if Rp.get("mean_bp") is not None else None
            print(f"      PLACEBO(+25b) VAL+OOS: gross={Rp.get('mean_bp')}bp net={net_p}bp n={Rp.get('n')} ci_excl0={Rp.get('ci_excl_0')}")
    return any_signal


def main():
    print("=== ROUND 29 — OI EVENT SEQUENCES ===\n")
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    fc_syms = feature_complete_universe(con)
    print(f"FASE 0 — universo Feature-Complete (OI >= {MIN_OI_ROWS} filas, ~historia completa): {len(fc_syms)} simbolos")
    print(f"  {fc_syms}\n")

    P = {}; OIF = {}; F = {}
    for s in fc_syms:
        d = load_symbol_oi(con, s)
        if d is None:
            continue
        P[s] = d; OIF[s] = causal_oi_feats(d); F[s] = build_feats(d)
    con.close()
    print(f"cargados con OHLCV+OI alineado: {len(P)} simbolos")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    battery = [
        ("A-OI_expansion", dict(kind="expand")),
        ("B-OI_contraction", dict(kind="contract")),
        ("C-OI_acceleration", dict(kind="accel")),
        ("D-OI_shock(ambos)", dict(kind="shock")),
        ("E-expansion+volumen", dict(kind="expand", vol_confirm=True)),
        ("F-contraccion+volumen", dict(kind="contract", vol_confirm=True)),
        ("G-expansion+precio_no_confirma", dict(kind="expand", price_side="low")),
        ("H-contraccion+precio_sube(short_covering)", dict(kind="contract", price_side="high")),
    ]
    any_hit = {}
    for label, kwargs in battery:
        events = build_events(P, OIF, F, **kwargs)
        print("#" * 70 + f"\n {label} — eventos: {len(events)}\n" + "#" * 70)
        if len(events) < 200:
            print("  eventos insuficientes, se salta")
            continue
        any_hit[label] = eval_battery(P, events, seg, label)
        print()

    print("#" * 70 + "\n RESUMEN — que ramas mostraron señal (mode != None en algun horizonte)\n" + "#" * 70)
    for label, hit in any_hit.items():
        print(f"  {label}: {'SI hubo señal en algun horizonte' if hit else 'sin señal en ningun horizonte'}")

    print("\nfin R29 discovery — ver informe para Fase 3 (informacion incremental) y sim economica si corresponde")


if __name__ == "__main__":
    main()
