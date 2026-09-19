"""
ROUND 30 — ALPHA DISCOVERY ENGINE: combinaciones de estado+evento, no
variables aisladas. Penalizacion por complejidad (2 features antes que 3).

Feature library CAUSAL disponible (Fase 1, auditada en rondas previas):
  - precio: ret1_pct (retorno extremo, percentil causal)              [357 sym, 14.5m]
  - volumen: vol_pct (percentil causal de volumen propio)             [357 sym, 14.5m]
  - volatilidad: rv_pct (percentil causal de volatilidad realizada)   [357 sym, 14.5m]
  - OI: dOI_pct (cambio 1-barra, percentil causal), d2OI_pct (aceleracion) [43 sym feature-complete, 14.5m]
  - funding: 63 sym, 8h -- descartado esta ronda (cobertura mas rala que OI, sin ganancia clara sobre lo ya cerrado)
  - OFI: FAILED en H12 (AUC 0.46), no se reintroduce
  - liquidaciones: cobertura insuficiente (R26), no se usa

8 combinaciones predeclaradas (Fase 2/3), NINGUNA repite exactamente lo
ya probado en R18 (compresion->ruptura), R21-23 (capitulacion=drop+volumen),
R24 (evento extremo puro), R27/28 (iliquidez), R29 (OI expansion/
contraccion/aceleracion solo o +volumen/+precio):

  Universo 357 (precio+volumen+volatilidad, sin OI):
    1. RV_high & V_contract   -- volatilidad alta pero volumen contrayendo (iliquidez EN volatilidad)
    2. RV_high & V_spike      -- volatilidad alta Y volumen extremo a la vez (no exige 2 barras seguidas como R2)
    3. V_spike & RV_low       -- spike de volumen en un regimen de fondo tranquilo
    4. P_ext & RV_low         -- movimiento extremo que rompe un regimen tranquilo (no solo "extremo", exige contexto)

  Universo 43 (OI feature-complete):
    5. RV_high & OI_exp       -- shock de volatilidad + apalancamiento entrando
    6. RV_low & OI_accel      -- posicionamiento acelerando en silencio (leading, antes de expansion)
    7. V_contract & OI_exp    -- OI sube con volumen chico (acumulacion silenciosa, no comprar el rally)
    9. RV_high & OI_exp & V_spike (3-way) -- confirmacion triple, penalizado por complejidad
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from r24_discovery_battery import freeze_direction_train, fwd, placebo
from r29_oi_sequences import feature_complete_universe, load_symbol_oi, causal_oi_feats, MIN_OI_ROWS
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
HZ = [("1h", 4), ("4h", 16), ("8h", 32), ("24h", 96), ("48h", 192)]
PCTILE_HI, PCTILE_LO = 0.90, 0.10


def load_wide():
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


def load_oi_universe():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    fc_syms = feature_complete_universe(con)
    P = {}; OIF = {}; F = {}
    for s in fc_syms:
        d = load_symbol_oi(con, s)
        if d is None:
            continue
        P[s] = d; OIF[s] = causal_oi_feats(d); F[s] = build_feats(d)
    con.close()
    return P, F, OIF


def build_combo_events(P, F, cond_fn, min_gap=4):
    events = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        r1 = f["r1"]
        mask = cond_fn(s, f)
        last = -999
        for i in np.where(mask)[0]:
            if i < ROLL or i - last < min_gap or i + 1 + HZ[-1][1] >= n:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if (np.isfinite(r1[i]) and r1[i] > 0) else -1.0
            events.append((s, i, dy, ev_sign))
    return events


def distribution_stats(P, events, hb, side_key):
    """side_key: dict (s,i)->side ya congelado. Devuelve stats de distribucion,
    no solo la media (Fase 5)."""
    rets = []
    for (s, i, dy, ev_sign) in events:
        side = side_key.get((s, i))
        if side is None:
            continue
        r = fwd(P, s, i, hb, side)
        if r is not None:
            rets.append(r * 1e4)
    if len(rets) < 30:
        return None
    arr = np.array(rets)
    return dict(n=len(arr), mean=arr.mean(), median=np.median(arr), p25=np.percentile(arr, 25),
                p75=np.percentile(arr, 75), win_rate=(arr > 0).mean(), skew=float(((arr - arr.mean()) ** 3).mean() / (arr.std() ** 3 + 1e-9)))


def screen(P, events, seg, label, results):
    if len(events) < 300:
        print(f"  {label}: eventos insuficientes ({len(events)}), se salta")
        return
    print(f"  {label}: eventos={len(events)}")
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events, hb, seg)
        if mode is None:
            continue
        # VAL debe confirmar (mismo signo que TRAIN, lección de R29-E) antes de mirar OOS
        train_pairs = []
        val_pairs = []
        for (s, i, dy, ev_sign) in events:
            side = ev_sign if mode == "cont" else -ev_sign
            r = fwd(P, s, i, hb, side)
            if r is None:
                continue
            if seg(dy) == "train":
                train_pairs.append((s, r))
            elif seg(dy) == "val":
                val_pairs.append((s, r))
        if len(val_pairs) < 30:
            continue
        Rval = agg_pairs(val_pairs)
        if not (Rval.get("mean_bp") is not None and Rval["mean_bp"] > 0):
            continue   # VAL no confirma el signo de TRAIN -> descartado sin mirar OOS
        oos_pairs = []
        for (s, i, dy, ev_sign) in events:
            if seg(dy) != "oos":
                continue
            side = ev_sign if mode == "cont" else -ev_sign
            r = fwd(P, s, i, hb, side)
            if r is not None:
                oos_pairs.append((s, r))
        if len(oos_pairs) < 30:
            continue
        Roos = agg_pairs(oos_pairs)
        net_oos = (Roos["mean_bp"] - COST) if Roos.get("mean_bp") is not None else None
        side_key = {(s, i): (ev_sign if mode == "cont" else -ev_sign) for (s, i, dy, ev_sign) in events}
        dist = distribution_stats(P, events, hb, side_key)
        ev_vo = [(s, i, dy) for (s, i, dy, ev_sign) in events if seg(dy) in ("val", "oos")]
        Rp = placebo(P, ev_vo, hb, lambda s, i: side_key.get((s, i), 1))
        net_p = (Rp["mean_bp"] - COST) if Rp.get("n", 0) >= 30 and Rp.get("mean_bp") is not None else None
        print(f"    h={h_lbl:>3s} [{mode}]: TRAIN={Rc.get('mean_bp') if mode=='cont' else Rr.get('mean_bp')}bp  "
              f"VAL_gross={Rval.get('mean_bp')}bp(n={Rval.get('n')})  OOS_gross={Roos.get('mean_bp')}bp net={net_oos}bp "
              f"n={Roos.get('n')} ci_excl0={Roos.get('ci_excl_0')}  placebo_net={net_p}")
        if dist:
            print(f"      distribucion(OOS-todo el set, side congelado): mean={dist['mean']:.1f}bp median={dist['median']:.1f}bp "
                  f"p25={dist['p25']:.1f} p75={dist['p75']:.1f} winrate={dist['win_rate']:.2f} skew={dist['skew']:.2f}")
        results.append(dict(label=label, h=h_lbl, hb=hb, mode=mode, events=events,
                             train_bp=Rc.get('mean_bp') if mode == 'cont' else Rr.get('mean_bp'),
                             val_bp=Rval.get('mean_bp'), oos_bp=Roos.get('mean_bp'), oos_net=net_oos,
                             oos_n=Roos.get('n'), oos_ci_excl0=Roos.get('ci_excl_0'), placebo_net=net_p,
                             side_key=side_key))


def main():
    print("=== ROUND 30 — ALPHA DISCOVERY ENGINE (combinaciones estado+evento) ===\n")
    P357, F357 = load_wide()
    print(f"universo 357 (precio/volumen/volatilidad) cargado")
    P43, F43, OIF43 = load_oi_universe()
    print(f"universo 43 (OI feature-complete) cargado\n")

    ref = "BTCUSDT" if "BTCUSDT" in P357 else max(P357, key=lambda s: len(P357[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P357[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    results = []

    print("#" * 70 + "\n UNIVERSO 357 — combinaciones precio/volumen/volatilidad\n" + "#" * 70)
    combos357 = [
        ("1-RVhigh&Vcontract", lambda s, f: np.isfinite(f["rv_pct"]) & (f["rv_pct"] >= PCTILE_HI) & np.isfinite(f["vol_pct"]) & (f["vol_pct"] <= PCTILE_LO)),
        ("2-RVhigh&Vspike", lambda s, f: np.isfinite(f["rv_pct"]) & (f["rv_pct"] >= PCTILE_HI) & np.isfinite(f["vol_pct"]) & (f["vol_pct"] >= PCTILE_HI)),
        ("3-Vspike&RVlow", lambda s, f: np.isfinite(f["vol_pct"]) & (f["vol_pct"] >= PCTILE_HI) & np.isfinite(f["rv_pct"]) & (f["rv_pct"] <= PCTILE_LO)),
        ("4-Pext&RVlow", lambda s, f: np.isfinite(f["ret1_pct"]) & ((f["ret1_pct"] >= PCTILE_HI) | (f["ret1_pct"] <= PCTILE_LO)) & np.isfinite(f["rv_pct"]) & (f["rv_pct"] <= PCTILE_LO)),
    ]
    for label, cond in combos357:
        events = build_combo_events(P357, F357, cond)
        screen(P357, events, seg, label, results)

    print("\n" + "#" * 70 + "\n UNIVERSO 43 (OI feature-complete) — combinaciones con OI\n" + "#" * 70)
    combos43 = [
        ("5-RVhigh&OIexp", lambda s, f: (np.isfinite(f["rv_pct"]) & (f["rv_pct"] >= PCTILE_HI) &
                                          np.isfinite(OIF43[s]["dOI_pct"]) & (OIF43[s]["dOI_pct"] >= PCTILE_HI))),
        ("6-RVlow&OIaccel", lambda s, f: (np.isfinite(f["rv_pct"]) & (f["rv_pct"] <= PCTILE_LO) &
                                           np.isfinite(OIF43[s]["d2OI_pct"]) & (OIF43[s]["d2OI_pct"] >= PCTILE_HI))),
        ("7-Vcontract&OIexp", lambda s, f: (np.isfinite(f["vol_pct"]) & (f["vol_pct"] <= PCTILE_LO) &
                                             np.isfinite(OIF43[s]["dOI_pct"]) & (OIF43[s]["dOI_pct"] >= PCTILE_HI))),
        ("9-RVhigh&OIexp&Vspike(3way)", lambda s, f: (np.isfinite(f["rv_pct"]) & (f["rv_pct"] >= PCTILE_HI) &
                                                       np.isfinite(OIF43[s]["dOI_pct"]) & (OIF43[s]["dOI_pct"] >= PCTILE_HI) &
                                                       np.isfinite(f["vol_pct"]) & (f["vol_pct"] >= PCTILE_HI))),
    ]
    for label, cond in combos43:
        events = build_combo_events(P43, F43, cond)
        screen(P43, events, seg, label, results)

    print("\n" + "#" * 70 + "\n RESUMEN — candidatos que sobrevivieron TRAIN->VAL(confirma signo)->OOS(n>=30)\n" + "#" * 70)
    if not results:
        print("  NINGUNO. Todas las combinaciones murieron en el filtro TRAIN o en la confirmacion de VAL.")
    else:
        results.sort(key=lambda r: -(r["oos_net"] or -1e9))
        for r in results:
            flag = " <== supera costo en OOS" if (r["oos_net"] or -999) > 0 else ""
            print(f"  {r['label']:32s} h={r['h']:>3s} [{r['mode']}]: OOS_gross={r['oos_bp']}bp net={r['oos_net']}bp "
                  f"n={r['oos_n']} ci_excl0={r['oos_ci_excl0']} placebo_net={r['placebo_net']}{flag}")

    print("\nfin R30 discovery")
    return results


if __name__ == "__main__":
    main()
