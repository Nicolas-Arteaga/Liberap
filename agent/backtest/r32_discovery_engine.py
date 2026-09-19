"""
ROUND 32 — DISCOVERY ENGINE AUTOMATIZADO (no hipotesis nombradas de
antemano). Barre automaticamente TODAS las combinaciones simples y de a
pares de un banco de 8 features causales -- incluyendo, por primera vez
con el rigor TRAIN->VAL->OOS->placebo de R23 en adelante, toptrader_ls_pos
y global_ls_acct (solo tocadas superficialmente en R12, FAILED sin este
rigor).

Banco de 8 features causales (todas percentil-causal, ROLL=2880 barras):
  1. ret1_pct     -- retorno extremo de precio
  2. rv_pct       -- volatilidad realizada
  3. vol_pct      -- volumen propio
  4. dOI_pct      -- cambio de Open Interest
  5. d2OI_pct     -- aceleracion de OI
  6. lspos_pct    -- nivel de toptrader_ls_pos (posicionamiento long/short
                     de las cuentas grandes, ratio bruto)
  7. lsacct_pct   -- nivel de global_ls_acct (long/short de TODAS las
                     cuentas, proxy retail)
  8. divergence_pct -- percentil causal de (toptrader_ls_pos - global_ls_acct)
                     normalizado -- divergencia smart-money vs retail

Cada feature se binariza en HIGH (percentil>=0.95) y LOW (percentil<=0.05).
Grid: 16 condiciones simples + 4*C(8,2)=112 combinaciones de a pares (AND
de 2 condiciones de features DISTINTAS) = 128 mascaras. Deliberadamente
NO se prueban trios (penalizacion por complejidad, Fase 4 del brief).

Fase 3 (discovery sin mirar OOS): pantalla de TRAIN en 3 horizontes
(4h/24h/72h) sobre las 128 mascaras x direccion(TRAIN-decidida) -- ~768
pruebas. Se advierte explicitamente el problema de comparaciones multiples
(a fair de 768 pruebas, se esperan ~38 "significativas" al 95% por puro
azar) -- por eso el TRAIN screen es solo una CRIBA, nunca una conclusion:
solo los candidatos que ademas confirman en VAL (Fase 3 exige eso) y
sobreviven placebo se toman en serio.
"""
import os, sys, math, numpy as np, sqlite3, collections, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r12_smartmoney import pctile_causal
from r18_discovery import build_feats, ROLL, HOR
from r24_discovery_battery import fwd, placebo
from r29_oi_sequences import feature_complete_universe, causal_oi_feats
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
HZ_SCREEN = [("4h", 16), ("24h", 96), ("72h", 288)]
HZ_FULL = [("1h", 4), ("4h", 16), ("12h", 48), ("24h", 96), ("48h", 192), ("72h", 288), ("7d", 672)]
HI, LO = 0.95, 0.05
MIN_EVENTS = 300


def load_symbol_full(con, s):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
    if len(k) < ROLL + 800:
        return None
    kt = np.array([r[0] for r in k], np.int64)
    o = np.array([r[1] for r in k], float); h = np.array([r[2] for r in k], float)
    lo = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
    v = np.array([r[5] for r in k], float)
    pos = {int(t): i for i, t in enumerate(kt)}
    oi = np.full(len(kt), np.nan); lspos = np.full(len(kt), np.nan); lsacct = np.full(len(kt), np.nan)
    for ot, so, tt, gl in con.execute("SELECT open_time,sum_oi,toptrader_ls_pos,global_ls_acct FROM oi_metrics WHERE symbol=? ORDER BY open_time", (s,)):
        if int(ot) % 900000 != 0:
            continue
        i = pos.get(int(ot))
        if i is not None:
            oi[i] = so; lspos[i] = tt; lsacct[i] = gl
    return dict(t=kt, o=o, h=h, l=lo, c=c, v=v, oi=oi, lspos=lspos, lsacct=lsacct)


def causal_feats_full(d):
    f = build_feats(d)   # r1, rv, rv_pct, ret1_pct, volz, vol_pct
    oif = causal_oi_feats(d)   # dOI, dOI_pct, d2OI_pct
    lspos_pct = pctile_causal(np.nan_to_num(d["lspos"], nan=0.0), ROLL)
    lspos_pct[~np.isfinite(d["lspos"])] = np.nan
    lsacct_pct = pctile_causal(np.nan_to_num(d["lsacct"], nan=0.0), ROLL)
    lsacct_pct[~np.isfinite(d["lsacct"])] = np.nan
    div_raw = d["lspos"] - d["lsacct"]
    div_pct = pctile_causal(np.nan_to_num(div_raw, nan=0.0), ROLL)
    div_pct[~(np.isfinite(d["lspos"]) & np.isfinite(d["lsacct"]))] = np.nan
    return dict(**f, dOI_pct=oif["dOI_pct"], d2OI_pct=oif["d2OI_pct"],
                lspos_pct=lspos_pct, lsacct_pct=lsacct_pct, divergence_pct=div_pct)


FEATS = ["ret1_pct", "rv_pct", "vol_pct", "dOI_pct", "d2OI_pct", "lspos_pct", "lsacct_pct", "divergence_pct"]


def build_masks():
    """genera (label, feat_list, dir_list) para condiciones simples y pares."""
    masks = []
    for f in FEATS:
        masks.append((f"{f}=HIGH", [(f, "hi")]))
        masks.append((f"{f}=LOW", [(f, "lo")]))
    for f1, f2 in itertools.combinations(FEATS, 2):
        for d1, d2 in (("hi", "hi"), ("hi", "lo"), ("lo", "hi"), ("lo", "lo")):
            masks.append((f"{f1}={d1.upper()}&{f2}={d2.upper()}", [(f1, d1), (f2, d2)]))
    return masks


def eval_mask(F, cond):
    """cond: list of (feat, 'hi'|'lo'). Devuelve dict simbolo->bool array."""
    out = {}
    for s, f in F.items():
        m = None
        for (feat, dr) in cond:
            arr = f[feat]
            cur = np.isfinite(arr) & ((arr >= HI) if dr == "hi" else (arr <= LO))
            m = cur if m is None else (m & cur)
        out[s] = m
    return out


def build_events_from_mask(P, F, mask_by_sym, min_gap=8):
    events = []
    for s, d in P.items():
        m = mask_by_sym[s]; c = d["c"]; t = d["t"]; n = len(c)
        r1 = F[s]["r1"]
        last = -999
        for i in np.where(m)[0]:
            if i < ROLL or i - last < min_gap or i + 1 + HZ_FULL[-1][1] >= n:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if (np.isfinite(r1[i]) and r1[i] > 0) else -1.0
            events.append((s, i, dy, ev_sign))
    return events


def freeze_dir(P, events, hb, seg):
    def pairs_for(mode):
        out = []
        for (s, i, dy, ev_sign) in events:
            if seg(dy) != "train":
                continue
            side = ev_sign if mode == "cont" else -ev_sign
            r = fwd(P, s, i, hb, side)
            if r is not None:
                out.append((s, r))
        return out
    Rc = agg_pairs(pairs_for("cont")); Rr = agg_pairs(pairs_for("rev"))
    mc, mr = Rc.get("mean_bp"), Rr.get("mean_bp")
    if mc is None or mr is None:
        return None, Rc, Rr
    if mc > 0 and Rc.get("ci_excl_0"):
        return "cont", Rc, Rr
    if mr > 0 and Rr.get("ci_excl_0"):
        return "rev", Rc, Rr
    return None, Rc, Rr


def mfe_mae_stats(P, events, hb, side_key):
    vals = []
    for (s, i, dy, ev_sign) in events:
        side = side_key.get((s, i))
        if side is None:
            continue
        d = P[s]; o = d["o"]; h_ = d["h"]; l = d["l"]
        e = i + 1
        j = e + hb
        if j >= len(o):
            continue
        entry = o[e]
        hi = h_[e:j + 1].max(); lo = l[e:j + 1].min()
        final = side * math.log(o[j] / entry) * 1e4
        if side > 0:
            mfe = math.log(hi / entry) * 1e4; mae = math.log(lo / entry) * 1e4
        else:
            mfe = -math.log(lo / entry) * 1e4; mae = -math.log(hi / entry) * 1e4
        vals.append((final, mfe, mae))
    if len(vals) < 30:
        return None
    arr = np.array(vals)
    return dict(n=len(arr), final_mean=arr[:, 0].mean(), mfe_mean=arr[:, 1].mean(), mae_mean=arr[:, 2].mean(),
                win_rate=(arr[:, 0] > 0).mean())


def main():
    print("=== ROUND 32 — DISCOVERY ENGINE AUTOMATIZADO ===\n")
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    fc_syms = feature_complete_universe(con)
    print(f"FASE 1 — universo feature-complete (OI+ls_pos+ls_acct, >=120k filas OI): {len(fc_syms)} simbolos")
    P = {}; F = {}
    for s in fc_syms:
        d = load_symbol_full(con, s)
        if d is None:
            continue
        cov_ls = np.isfinite(d["lspos"]).mean()
        P[s] = d; F[s] = causal_feats_full(d)
    con.close()
    cov_lspos = np.mean([np.isfinite(P[s]["lspos"]).mean() for s in P])
    cov_lsacct = np.mean([np.isfinite(P[s]["lsacct"]).mean() for s in P])
    print(f"cargados: {len(P)} simbolos. Cobertura media toptrader_ls_pos={cov_lspos:.1%}  global_ls_acct={cov_lsacct:.1%}\n")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    masks = build_masks()
    print(f"FASE 2/3 — grid automatico: {len(masks)} mascaras (16 simples + 112 pares) x {len(HZ_SCREEN)} horizontes de criba "
          f"= {len(masks)*len(HZ_SCREEN)} pruebas en TRAIN (advertencia: con este N se esperan ~{int(len(masks)*len(HZ_SCREEN)*0.05)} "
          f"'significativas' al 95% solo por azar -- esto es una CRIBA, no una conclusion)\n")

    screened = []
    for label, cond in masks:
        mbs = eval_mask(F, cond)
        events = build_events_from_mask(P, F, mbs)
        if len(events) < MIN_EVENTS:
            continue
        for h_lbl, hb in HZ_SCREEN:
            mode, Rc, Rr = freeze_dir(P, events, hb, seg)
            if mode is None:
                continue
            mean_bp = Rc["mean_bp"] if mode == "cont" else Rr["mean_bp"]
            screened.append(dict(label=label, cond=cond, h_lbl=h_lbl, hb=hb, mode=mode,
                                  train_bp=mean_bp, n_events=len(events), events=events))

    print(f"candidatos que pasan la criba de TRAIN (CI excl 0, n>={MIN_EVENTS}): {len(screened)}")
    screened.sort(key=lambda r: -abs(r["train_bp"]) * math.log(r["n_events"]))
    top = screened[:15]
    print("\ntop-15 por |efecto|*log(n) (para no premiar solo N gigante ni solo bp gigante con pocos eventos):")
    for r in top:
        print(f"  {r['label']:40s} h={r['h_lbl']:>3s} [{r['mode']}] TRAIN={r['train_bp']:+.1f}bp n={r['n_events']}")

    print("\n" + "#" * 70 + "\n FASE 3 (cont.) — VAL debe confirmar signo antes de tocar OOS\n" + "#" * 70)
    survivors = []
    seen_labels = set()
    for r in top:
        if r["label"] in seen_labels:
            continue   # evitar contar la misma mascara 2 veces en distintos horizontes de la lista top
        seen_labels.add(r["label"])
        events = r["events"]; hb = r["hb"]; mode = r["mode"]
        val_pairs = [(s, fwd(P, s, i, hb, ev_sign if mode == "cont" else -ev_sign))
                     for (s, i, dy, ev_sign) in events if seg(dy) == "val"]
        val_pairs = [(s, x) for (s, x) in val_pairs if x is not None]
        if len(val_pairs) < 30:
            print(f"  {r['label']:40s} h={r['h_lbl']}: VAL insuficiente (n={len(val_pairs)}) -> descartado")
            continue
        Rv = agg_pairs(val_pairs)
        if not (Rv.get("mean_bp") is not None and Rv["mean_bp"] > 0):
            print(f"  {r['label']:40s} h={r['h_lbl']}: VAL no confirma signo (val={Rv.get('mean_bp')}bp) -> descartado")
            continue
        print(f"  {r['label']:40s} h={r['h_lbl']}: VAL CONFIRMA ({Rv['mean_bp']:+.1f}bp, n={Rv['n']}) -> pasa a OOS")
        survivors.append(dict(r, val_bp=Rv["mean_bp"]))

    print("\n" + "#" * 70 + "\n FASE 3 (fin) + FASE 4 — OOS + placebo + controles, solo para los que confirmaron VAL\n" + "#" * 70)
    finalists = []
    for r in survivors:
        events = r["events"]; hb = r["hb"]; mode = r["mode"]; label = r["label"]
        oos_pairs = [(s, fwd(P, s, i, hb, ev_sign if mode == "cont" else -ev_sign))
                     for (s, i, dy, ev_sign) in events if seg(dy) == "oos"]
        oos_pairs = [(s, x) for (s, x) in oos_pairs if x is not None]
        if len(oos_pairs) < 30:
            print(f"  {label}: OOS insuficiente -> descartado")
            continue
        Ro = agg_pairs(oos_pairs)
        net_oos = (Ro["mean_bp"] - COST) if Ro.get("mean_bp") is not None else None
        side_key = {(s, i): (ev_sign if mode == "cont" else -ev_sign) for (s, i, dy, ev_sign) in events}
        ev_vo = [(s, i, dy) for (s, i, dy, ev_sign) in events if seg(dy) in ("val", "oos")]
        Rp = placebo(P, ev_vo, hb, lambda s, i: side_key.get((s, i), 1))
        net_p = (Rp["mean_bp"] - COST) if Rp.get("n", 0) >= 30 and Rp.get("mean_bp") is not None else None
        dist = mfe_mae_stats(P, events, hb, side_key)
        print(f"  {label} h={r['h_lbl']} [{mode}]: OOS gross={Ro.get('mean_bp')}bp net={net_oos}bp n={Ro.get('n')} "
              f"ci_excl0={Ro.get('ci_excl_0')}  placebo_net={net_p}")
        if dist:
            print(f"      MFE/MAE (side congelado): final_mean={dist['final_mean']:.1f}bp mfe_mean={dist['mfe_mean']:.1f}bp "
                  f"mae_mean={dist['mae_mean']:.1f}bp win_rate={dist['win_rate']:.2f} n={dist['n']}")
        placebo_kills = (net_p is not None and net_oos is not None and abs(net_p) >= abs(net_oos) * 0.5)
        verdict = "FAILED (placebo comparable)" if placebo_kills else (
            "FAILED (no supera costo)" if (net_oos is None or net_oos <= 0) else
            ("PASS candidato" if net_oos >= 150 * 1e4 / 450 else "PARK candidato"))
        # nota: el umbral de 150usd/mes se traduce a sim economica en la siguiente fase, esta linea es solo orientativa a nivel bp
        print(f"      veredicto preliminar (a nivel bp, antes de sim economica con capital): {verdict}")
        finalists.append(dict(r, oos_bp=Ro.get("mean_bp"), oos_net=net_oos, oos_n=Ro.get("n"),
                               oos_ci_excl0=Ro.get("ci_excl_0"), placebo_net=net_p, dist=dist, verdict=verdict))

    print("\n" + "#" * 70 + "\n RESUMEN FINAL\n" + "#" * 70)
    real_candidates = [f for f in finalists if f["oos_net"] is not None and f["oos_net"] > 0 and
                        not (f["placebo_net"] is not None and abs(f["placebo_net"]) >= abs(f["oos_net"]) * 0.5)]
    print(f"  mascaras cribadas en TRAIN: {len(screened)} (de {len(masks)*len(HZ_SCREEN)} pruebas)")
    print(f"  confirmaron VAL: {len(survivors)}")
    print(f"  llegaron a OOS con n>=30: {len(finalists)}")
    print(f"  candidatos reales (OOS net>0 Y no reproducido por placebo): {len(real_candidates)}")
    for r in real_candidates:
        print(f"    >>> {r['label']} h={r['h_lbl']} [{r['mode']}] OOS_net={r['oos_net']:.1f}bp n={r['oos_n']}")

    print("\nfin R32 discovery")


if __name__ == "__main__":
    main()
