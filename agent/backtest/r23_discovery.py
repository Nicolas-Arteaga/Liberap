"""
ROUND 23, PARTE B — DISCOVERY (solo, no validation/execution/audit todavia,
Parte 15 del brief: no mezclar etapas).

Mecanismo: VOLATILITY TRANSITION FOLLOW-THROUGH (familia 3 de la lista de
prioridad). Distinto de la Secuencia 1 de R18 (compresion->ruptura, FAILED,
midio la barra de ruptura MISMA). Aca: compresion sostenida -> primera
barra de expansion (la ruptura) -> se mide la SEGUNDA barra en adelante
(el follow-through), condicionando en que la ruptura ya paso. Direccion =
signo de la barra de ruptura (continuacion), congelada como hipotesis
economica, no fiteada.

Protocolo (Parte 16, anti-overfitting): definir evento y direccion ANTES
de mirar VAL/OOS. TRAIN/VAL/OOS 50/25/25 por fecha. Placebo: mismo evento
de compresion pero SIN el requisito de expansion posterior (control), y
shuffle temporal.
"""
import os, sys, math, numpy as np, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COMPRESSION_K = 8          # barras (2h) de compresion sostenida minima
COMPRESSION_PCTILE = 0.15  # rv_pct causal por debajo de este umbral
EXPANSION_PCTILE = 0.85    # |ret1| causal por encima de este umbral = ruptura
rng = np.random.default_rng(20261002)


def main():
    print("=== ROUND 23B — DISCOVERY: VOLATILITY TRANSITION FOLLOW-THROUGH ===\n")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    print(f"universo: {len(P)} simbolos")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    # ---- evento: compresion sostenida (K barras seguidas rv_pct causal bajo) seguida
    #      de 1 barra de ruptura (|ret1_pct causal| alto) -> direccion = signo de esa barra ----
    events = []      # (sym, i_break, dy, side)
    ctrl_events = []  # control: misma ruptura, SIN compresion previa (para aislar el efecto de la compresion)
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        rvp = f["rv_pct"]; r1p = f["ret1_pct"]; r1 = f["r1"]
        compressed = np.isfinite(rvp) & (rvp <= COMPRESSION_PCTILE)
        breakout = np.isfinite(r1p) & (r1p >= EXPANSION_PCTILE)
        for i in range(ROLL + COMPRESSION_K, n - max(HOR.values()) - 2):
            if not breakout[i]:
                continue
            side = 1.0 if r1[i] > 0 else -1.0
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            was_compressed = compressed[i - COMPRESSION_K:i].all()
            if was_compressed:
                events.append((s, i, dy, side))
            else:
                ctrl_events.append((s, i, dy, side))

    print(f"eventos (compresion -> ruptura): {len(events)}")
    print(f"control (ruptura SIN compresion previa): {len(ctrl_events)}\n")

    def fwd(s, i, hbars, side, skip_first=True):
        """retorno desde open[i+2] (SEGUNDA barra, el follow-through -- salta
        la barra de ruptura misma, que R18 ya midio y cerro FAILED) hasta
        open[i+2+hbars]."""
        d = P[s]; o = d["o"]
        e = i + 2 if skip_first else i + 1
        if e + hbars >= len(o):
            return None
        return side * math.log(o[e + hbars] / o[e])

    print("#" * 70 + "\n FOLLOW-THROUGH (2da barra en adelante) — TRAIN/VAL/OOS, direccion=continuacion\n" + "#" * 70)
    for h_lbl, hb in HOR.items():
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd(s, i, hb, side)) for (s, i, dy, side) in events if seg(dy) == sgv and fwd(s, i, hb, side) is not None]
            if len(pairs) < 30:
                continue
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - 24.0) if R.get("mean_bp") is not None else None
            print(f"  h={h_lbl:>4s} {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} "
                  f"ci={R.get('ci_bp')} ci_excl0={R.get('ci_excl_0')}")

    print("\n" + "#" * 70 + "\n CONTROL — misma ruptura SIN compresion previa (¿la compresion aporta algo?)\n" + "#" * 70)
    for h_lbl, hb in HOR.items():
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd(s, i, hb, side)) for (s, i, dy, side) in ctrl_events if seg(dy) == sgv and fwd(s, i, hb, side) is not None]
            if len(pairs) < 30:
                continue
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - 24.0) if R.get("mean_bp") is not None else None
            print(f"  h={h_lbl:>4s} {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} ci_excl0={R.get('ci_excl_0')}")

    print("\n" + "#" * 70 + "\n PLACEBO TEMPORAL — mismo evento, ventana desplazada +25 barras (sin relacion causal)\n" + "#" * 70)
    for h_lbl, hb in (("4h", HOR["4h"]), ("24h", HOR["24h"])):
        pairs = []
        for (s, i, dy, side) in events:
            if seg(dy) not in ("val", "oos"):
                continue
            d = P[s]; o = d["o"]
            e = i + 2 + 25
            if e + hb >= len(o):
                continue
            pairs.append((s, side * math.log(o[e + hb] / o[e])))
        if len(pairs) >= 30:
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - 24.0) if R.get("mean_bp") is not None else None
            print(f"  h={h_lbl:>4s} VAL+OOS (shift+25): gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} ci_excl0={R.get('ci_excl_0')}")

    print("\n(Solo DISCOVERY -- si TRAIN+VAL+OOS coinciden en signo, superan costo, y el placebo")
    print(" es claramente inferior, pasa a VALIDATION/EXECUTION en la proxima ronda. No se corre")
    print(" sim economica todavia -- separar etapas, Parte 15 del brief.)")


if __name__ == "__main__":
    main()
