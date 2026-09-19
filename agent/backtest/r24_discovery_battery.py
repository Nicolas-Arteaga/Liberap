"""
ROUND 24 — ALPHA DISCOVERY: bateria amplia de hipotesis, direccion SIEMPRE
decidida en TRAIN y congelada antes de mirar VAL/OOS. Placebo temporal
(+25 barras) para cada una. Universo ancho (357 simbolos), motor de datos
identico a R18-R23 (klines_clean, causal).

Familias probadas (evitando todo lo ya cerrado en ALPHA_HYPOTHESIS_LEDGER):
  H1 — evento extremo puro (una sola barra, |ret1| extremo), direccion
       TRAIN-decidida (long o short), separado para el lado UP y el lado
       DOWN (pueden ser asimetricos).
  H2 — doble shock consecutivo de volatilidad (2 barras seguidas con rv_pct
       causal alto) -> reaccion posterior.
  H3 — caida extrema + recuperacion PARCIAL (20-60% del drop, NO capitulacion
       de una sola barra) -> continuacion desde el punto de recuperacion.
  H4 — ruptura fallida (breakout que se revierte en la barra siguiente)
       CON control de magnitud emparejada (mismo decil de |ret1|, sin
       exigir el fallo) -- corrige el hueco que dejo R23.
  H5 — comportamiento relativo cross-sectional de corto plazo: un simbolo
       cuyo retorno trailing de 4h se aleja fuerte de la MEDIANA del
       universo en esa misma ventana (no beta, no BTC, no semanal).
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
rng = np.random.default_rng(20261010)


def load_universe():
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


def fwd(P, s, i_entry, hbars, side):
    d = P[s]; o = d["o"]
    e = i_entry + 1
    if e + hbars >= len(o):
        return None
    return side * math.log(o[e + hbars] / o[e])


def placebo(P, events_iewithdy, hbars, side_fn, shift=25):
    pairs = []
    for (s, i, dy) in events_iewithdy:
        d = P[s]; o = d["o"]
        e = i + 1 + shift
        if e + hbars >= len(o):
            continue
        side = side_fn(s, i)
        pairs.append((s, side * math.log(o[e + hbars] / o[e])))
    return agg_pairs(pairs) if len(pairs) >= 30 else {"n": len(pairs)}


def freeze_direction_train(P, events, hbars, seg):
    """Decide side (+1/-1) mirando SOLO TRAIN: compara continuacion vs
    reversion del signo de la barra de evento, elige la de mayor |mean_bp|
    con CI que excluye 0 en TRAIN. Devuelve (side_mode, R_train) donde
    side_mode in {'cont','rev',None}."""
    def pairs_for(mode):
        out = []
        for (s, i, dy, ev_sign) in events:
            if seg(dy) != "train":
                continue
            side = ev_sign if mode == "cont" else -ev_sign
            r = fwd(P, s, i, hbars, side)
            if r is not None:
                out.append((s, r))
        return out
    Rc = agg_pairs(pairs_for("cont"))
    Rr = agg_pairs(pairs_for("rev"))
    # cont y rev son espejos exactos (mismo |pares|, signo invertido) -> la
    # decision correcta es el signo POSITIVO de mean_bp, no la magnitud
    # absoluta (comparar |x| es una tautologia entre espejos y siempre
    # empata -- el bug real de la primera corrida de esta ronda).
    mc = Rc.get("mean_bp"); mr = Rr.get("mean_bp")
    if mc is None or mr is None:
        return None, Rc, Rr
    if mc > 0 and Rc.get("ci_excl_0"):
        return "cont", Rc, Rr
    if mr > 0 and Rr.get("ci_excl_0"):
        return "rev", Rc, Rr
    return None, Rc, Rr


def eval_frozen(P, events, hbars, mode, seg, label):
    if mode is None:
        print(f"    {label} h={hbars*15}min: TRAIN no da CI excl 0 en ninguna direccion -> sin señal, se descarta")
        return
    for sgv in ("train", "val", "oos"):
        pairs = []
        for (s, i, dy, ev_sign) in events:
            if seg(dy) != sgv:
                continue
            side = ev_sign if mode == "cont" else -ev_sign
            r = fwd(P, s, i, hbars, side)
            if r is not None:
                pairs.append((s, r))
        if len(pairs) < 30:
            continue
        R = agg_pairs(pairs)
        net = (R["mean_bp"] - COST) if R.get("mean_bp") is not None else None
        print(f"    {label} h={hbars*15:4d}min [{mode}] {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp "
              f"n={R.get('n')} ci={R.get('ci_bp')} ci_excl0={R.get('ci_excl_0')}")
    # placebo (val+oos combinado, shift+25 barras) con el side congelado
    ev_vo = [(s, i, dy) for (s, i, dy, ev_sign) in events if seg(dy) in ("val", "oos")]
    side_fn = {}
    for (s, i, dy, ev_sign) in events:
        side_fn[(s, i)] = ev_sign if mode == "cont" else -ev_sign
    Rp = placebo(P, ev_vo, hbars, lambda s, i: side_fn.get((s, i), 1))
    if Rp.get("n", 0) >= 30:
        net_p = (Rp["mean_bp"] - COST) if Rp.get("mean_bp") is not None else None
        print(f"    {label} h={hbars*15:4d}min [{mode}] PLACEBO(+25 barras) VAL+OOS: gross={Rp.get('mean_bp')}bp net={net_p}bp "
              f"n={Rp.get('n')} ci_excl0={Rp.get('ci_excl_0')}")


def main():
    print("=== ROUND 24 — ALPHA DISCOVERY BATTERY ===\n")
    P, F = load_universe()
    print(f"universo: {len(P)} simbolos")
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")
    HZ = [("1h", HOR["1h"]), ("4h", HOR["4h"]), ("12h", HOR["12h"]), ("24h", HOR["24h"])]

    # =====================================================================
    print("#" * 70 + "\n H1 — EVENTO EXTREMO PURO (1 barra), direccion TRAIN-decidida, UP vs DOWN por separado\n" + "#" * 70)
    for label, lo, hi in (("UP extremo", 0.97, 1.01), ("DOWN extremo", -0.01, 0.03)):
        events = []
        for s, d in P.items():
            f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
            r1p = f["ret1_pct"]; r1 = f["r1"]
            mask = np.isfinite(r1p) & (r1p >= lo) & (r1p <= hi) if lo <= hi else (np.isfinite(r1p) & (r1p <= hi))
            if lo > 0:
                mask = np.isfinite(r1p) & (r1p >= lo)
            else:
                mask = np.isfinite(r1p) & (r1p <= hi)
            last = -999
            for i in np.where(mask)[0]:
                if i < ROLL or i - last < 4 or i + 1 + HOR["24h"] >= n:
                    continue
                last = i
                dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                ev_sign = 1.0 if r1[i] > 0 else -1.0
                events.append((s, i, dy, ev_sign))
        print(f"\n  -- {label} -- eventos: {len(events)}")
        for h_lbl, hb in HZ:
            mode, Rc, Rr = freeze_direction_train(P, events, hb, seg)
            print(f"    [TRAIN screen] cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
                  f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
            eval_frozen(P, events, hb, mode, seg, f"H1-{label}")

    # =====================================================================
    print("\n" + "#" * 70 + "\n H2 — DOBLE SHOCK DE VOLATILIDAD CONSECUTIVO\n" + "#" * 70)
    events2 = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        rvp = f["rv_pct"]; r1 = f["r1"]
        shock = np.isfinite(rvp) & (rvp >= 0.95)
        last = -999
        for i in range(ROLL + 1, n - HOR["24h"] - 2):
            if shock[i] and shock[i - 1] and i - last >= 4:
                last = i
                dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                ev_sign = 1.0 if r1[i] > 0 else -1.0
                events2.append((s, i, dy, ev_sign))
    print(f"eventos: {len(events2)}")
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events2, hb, seg)
        print(f"  [TRAIN screen h={h_lbl}] cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
              f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
        eval_frozen(P, events2, hb, mode, seg, "H2-doble-shock")

    # =====================================================================
    print("\n" + "#" * 70 + "\n H3 — CAIDA EXTREMA + RECUPERACION PARCIAL (20-60% del drop)\n" + "#" * 70)
    events3 = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; h_ = d["h"]; t = d["t"]; n = len(c)
        r1p = f["ret1_pct"]
        drop = np.isfinite(r1p) & (r1p <= 0.03)
        last = -999
        for i in np.where(drop)[0]:
            if i < ROLL or i - last < 8 or i + 6 + HOR["24h"] >= n:
                continue
            drop_mag = c[i - 1] - c[i]
            if drop_mag <= 0:
                continue
            # buscar el punto de recuperacion 20-60% del drop dentro de las siguientes 4 barras
            found = None
            for k in range(1, 5):
                j = i + k
                recov = (h_[j] - c[i]) / drop_mag
                if 0.20 <= recov <= 0.60:
                    found = j; break
            if found is None:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[found]) / 1000).date()
            events3.append((s, found, dy, -1.0))   # hipotesis: continuacion bajista tras rebote parcial fallido
    print(f"eventos: {len(events3)}")
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events3, hb, seg)
        print(f"  [TRAIN screen h={h_lbl}] cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
              f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
        eval_frozen(P, events3, hb, mode, seg, "H3-drop+recuperacion-parcial")

    # =====================================================================
    print("\n" + "#" * 70 + "\n H4 — RUPTURA FALLIDA vs CONTROL DE MAGNITUD EMPAREJADA\n" + "#" * 70)
    events4_fail = []; events4_ctrl = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        r1p = f["ret1_pct"]; r1 = f["r1"]
        extreme = np.isfinite(r1p) & ((r1p >= 0.90) | (r1p <= 0.10))
        last = -999
        for i in np.where(extreme)[0]:
            if i < ROLL or i - last < 4 or i + 2 + HOR["24h"] >= n:
                continue
            last = i
            ev_sign = 1.0 if r1[i] > 0 else -1.0
            next_ret = c[i + 1] - c[i]
            failed = (ev_sign > 0 and next_ret < 0) or (ev_sign < 0 and next_ret > 0)
            dy = datetime.utcfromtimestamp(int(t[i + 1]) / 1000).date()
            if failed:
                events4_fail.append((s, i + 1, dy, -ev_sign))   # fade del movimiento original
            else:
                events4_ctrl.append((s, i + 1, dy, -ev_sign))   # mismo decil de magnitud, SIN fallo -- control emparejado
    print(f"eventos ruptura-fallida: {len(events4_fail)}   control (mismo decil, sin fallo): {len(events4_ctrl)}")
    for label, evs in (("FALLIDA", events4_fail), ("CONTROL(sin fallo)", events4_ctrl)):
        print(f"\n  -- {label} --")
        for h_lbl, hb in (("4h", HOR["4h"]), ("24h", HOR["24h"])):
            pairs = {"train": [], "val": [], "oos": []}
            for (s, i, dy, side) in evs:
                r = fwd(P, s, i, hb, side)
                if r is not None:
                    pairs[seg(dy)].append((s, r))
            for sgv in ("train", "val", "oos"):
                if len(pairs[sgv]) < 30:
                    continue
                R = agg_pairs(pairs[sgv])
                net = (R["mean_bp"] - COST) if R.get("mean_bp") is not None else None
                print(f"    h={h_lbl:>3s} {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} ci_excl0={R.get('ci_excl_0')}")

    # =====================================================================
    print("\n" + "#" * 70 + "\n H5 — RELATIVO CROSS-SECTIONAL DE CORTO PLAZO (4h vs mediana del universo, NO beta/BTC)\n" + "#" * 70)
    # retorno trailing de 4h causal por simbolo, comparado contra la mediana cross-sectional EN EL MISMO instante
    HB4 = HOR["4h"]
    time_to_syms = collections.defaultdict(list)
    r4_by_sym = {}
    for s, d in P.items():
        c = d["c"]; t = d["t"]; n = len(c)
        r4 = np.full(n, np.nan)
        r4[HB4:] = np.log(c[HB4:] / c[:-HB4])
        r4_by_sym[s] = r4
        for idx, tv in enumerate(t):
            if np.isfinite(r4[idx]):
                time_to_syms[int(tv)].append((s, idx, r4[idx]))
    print(f"timestamps con >=30 simbolos activos: {sum(1 for v in time_to_syms.values() if len(v)>=30)}")
    events5 = []
    for tv, lst in time_to_syms.items():
        if len(lst) < 30:
            continue
        vals = np.array([x[2] for x in lst])
        med = np.median(vals)
        madv = np.median(np.abs(vals - med)) or 1e-9
        for (s, idx, r4v) in lst:
            z = (r4v - med) / madv
            if abs(z) >= 4.0:   # outlier relativo extremo, robusto (MAD, no std)
                d = P[s]
                if idx < ROLL or idx + 1 + HOR["24h"] >= len(d["c"]):
                    continue
                dy = datetime.utcfromtimestamp(tv / 1000).date()
                events5.append((s, idx, dy, 1.0 if z > 0 else -1.0))   # ev_sign = direccion del outlier
    print(f"eventos (outlier relativo |z_mad|>=4 vs mediana cross-sectional, 4h trailing): {len(events5)}")
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events5, hb, seg)
        print(f"  [TRAIN screen h={h_lbl}] cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
              f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
        eval_frozen(P, events5, hb, mode, seg, "H5-outlier-relativo-cross-sectional")

    print("\nfin R24 — bateria de discovery. Ver informe para interpretacion y siguiente paso.")


if __name__ == "__main__":
    main()
