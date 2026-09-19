"""
ROUND 28 — LIQUIDITY TRANSITION.

Transicion (no estado estatico, leccion de R27): momento en que un simbolo
SALE de un regimen de iliquidez sostenida (vol_pct causal <=10% durante
>=4 barras, 1h) y su volumen vuelve a subir. 3 variantes predeclaradas,
economicamente distintas, ANTES de mirar resultados:

  D) SALIDA simple: vol_pct cruza de <=10% a >10% tras >=4 barras de
     regimen sostenido.
  E) SALIDA + MOVIMIENTO EXTREMO: igual que D, pero la barra de salida
     tiene ademas |ret1_pct| extremo (>=95% o <=5%).
  F) SALIDA + RECUPERACION FUERTE: igual que D, pero el volumen no solo
     sale del decil bajo, salta directo a un decil ALTO (vol_pct>=90%
     en la misma barra) -- aceleracion de actividad, no una simple vuelta
     a la normalidad.

Direccion (LONG/SHORT) SIEMPRE decidida en TRAIN, nunca asumida.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from r24_discovery_battery import freeze_direction_train, fwd, placebo
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
MAJOR_SET = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
             "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT",
             "MATICUSDT", "BCHUSDT", "NEARUSDT", "ATOMUSDT", "UNIUSDT", "ETCUSDT",
             "APTUSDT", "FILUSDT"}
ILLIQ_PCTILE = 0.10
MIN_ILLIQ_BARS = 4    # >=1h de regimen sostenido antes de contar como "salida"
HZ = [("15m", 1), ("1h", 4), ("4h", 16), ("8h", 32), ("24h", 96), ("48h", 192)]


def load_all():
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    return P, F


def build_exit_events(P, F, require_extreme=False, require_surge=False):
    events = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        volp = f["vol_pct"]; r1p = f["ret1_pct"]; r1 = f["r1"]
        ok = np.isfinite(volp)
        illiq = ok & (volp <= ILLIQ_PCTILE)
        last = -999
        for i in range(ROLL + MIN_ILLIQ_BARS + 1, n - HZ[-1][1] - 2):
            if not (ok[i] and volp[i] > ILLIQ_PCTILE):
                continue
            # exigir regimen sostenido: las MIN_ILLIQ_BARS barras previas todas iliquidas
            if not illiq[i - MIN_ILLIQ_BARS:i].all():
                continue
            if i - last < MIN_ILLIQ_BARS:
                continue
            if require_extreme:
                if not (np.isfinite(r1p[i]) and (r1p[i] >= 0.95 or r1p[i] <= 0.05)):
                    continue
            if require_surge:
                if not (volp[i] >= 0.90):
                    continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if (np.isfinite(r1[i]) and r1[i] > 0) else -1.0
            events.append((s, i, dy, ev_sign))
    return events


def eval_all(P, events, seg, label):
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events, hb, seg)
        tag = f"cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})"
        if mode is None:
            print(f"  [{label}] h={h_lbl:>3s}: {tag}  -> sin señal, descartado")
            continue
        print(f"  [{label}] h={h_lbl:>3s}: {tag}  -> elegido: {mode}")
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
            print(f"      {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} "
                  f"ci={R.get('ci_bp')} ci_excl0={R.get('ci_excl_0')}")
        # placebo temporal, val+oos
        ev_vo = [(s, i, dy) for (s, i, dy, ev_sign) in events if seg(dy) in ("val", "oos")]
        side_map = {(s, i): (ev_sign if mode == "cont" else -ev_sign) for (s, i, dy, ev_sign) in events}
        Rp = placebo(P, ev_vo, hb, lambda s, i: side_map.get((s, i), 1))
        if Rp.get("n", 0) >= 30:
            net_p = (Rp["mean_bp"] - COST) if Rp.get("mean_bp") is not None else None
            print(f"      PLACEBO(+25 barras) VAL+OOS: gross={Rp.get('mean_bp')}bp net={net_p}bp "
                  f"n={Rp.get('n')} ci_excl0={Rp.get('ci_excl_0')}")
    return None


def main():
    print("=== ROUND 28 — LIQUIDITY TRANSITION ===\n")
    P, F = load_all()
    print(f"universo: {len(P)} simbolos")
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    print("#" * 70 + "\n D) SALIDA SIMPLE de iliquidez (>=4 barras sostenidas, luego vol_pct>10%)\n" + "#" * 70)
    evD = build_exit_events(P, F)
    print(f"eventos: {len(evD)}")
    eval_all(P, evD, seg, "D-salida-simple")

    print("\n" + "#" * 70 + "\n E) SALIDA + MOVIMIENTO EXTREMO en la barra de salida\n" + "#" * 70)
    evE = build_exit_events(P, F, require_extreme=True)
    print(f"eventos: {len(evE)}")
    eval_all(P, evE, seg, "E-salida+extremo")

    print("\n" + "#" * 70 + "\n F) SALIDA + RECUPERACION FUERTE (vol_pct salta directo a decil>=90%)\n" + "#" * 70)
    evF = build_exit_events(P, F, require_surge=True)
    print(f"eventos: {len(evF)}")
    eval_all(P, evF, seg, "F-salida+surge")

    print("\nfin R28 discovery")


if __name__ == "__main__":
    main()
