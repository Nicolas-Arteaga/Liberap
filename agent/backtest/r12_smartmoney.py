"""
ROUND 12 — SMART MONEY DIVERGENCE -> ECONOMIC ALPHA (+ OI ACCELERATION fallback).

MECANISMO 1 (primario): divergencia entre posicionamiento de CUENTAS globales
(`global_ls_acct`, proxy retail-crowd, ratio long/short por número de cuentas) y
posicionamiento de TOP TRADERS por tamaño de POSICION (`toptrader_ls_pos`).
  D   = z(global_ls_acct) - z(toptrader_ls_pos)      (causal, ROLL=2880=30d, 15m)
  z_D = zscore_causal(D, ROLL)
  pct_D = percentil causal de D en su ventana de 30d
  dD  = D[t] - D[t-W]   (W=4=1h)
Eventos extremos en percentiles PRE-DECLARADOS: P90/95/97.5/99, DOS lados:
  RL_SS (retail LONG / smart SHORT) = D en el percentil ALTO  -> hip. caída
  RS_SL (retail SHORT / smart LONG) = D en el percentil BAJO  -> hip. subida
No se asume signo: se reporta RAW forward return (log ret crudo) en ambos lados.

MECANISMO 2 (fallback automático si M1 falla): OI ACCELERATION.
  oi1 = dOI  (= H13-C, ya usado, W=4)
  oi2 = oi1[t] - oi1[t-W]     (aceleración = 2da diferencia)
  z_oi2 = zscore_causal(oi2, ROLL)
Eventos: |z_oi2| >= 1.5 (predeclarado), con y sin confirmación de precio
(sign(oi2)==sign(retW) vs divergente).

Todo con: universo restringido (45 símbolos ex-ante que ya cotizaban <=2025-07-01,
igual que R11), horizontes 15m/30m/1h/2h/4h/8h/24h, TRAIN/VAL/OOS 50/25/25,
cluster-bootstrap, placebos (random-ranking, time-shift +24h, sign-inversion,
matched-control), regresion incremental, y SIM ECONOMICA INMEDIATA (entry
open[t+1], RT 24bp + funding real, capital <=450, concurrencia) para cualquier
variante con CI que excluya 0 y signo estable train->val->oos.
"""
import os, sys, json, math, numpy as np, sqlite3
from numpy.lib.stride_tricks import sliding_window_view
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs
from r9_oi_alpha import load_panel
from r10_doi_regime import HOR, hlabel, ROLL, W
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CUTOFF_EXIST = date(2025, 7, 1)
RT_BP = 2 * (5.0 + 3.0 + 4.0)   # fee+spread+slip por lado x2 = 24bp, igual que R11
PCTS = [0.90, 0.95, 0.975, 0.99]
rng = np.random.default_rng(20260915)


def pctile_causal(a, win):
    n = len(a); out = np.full(n, np.nan)
    if n <= win:
        return out
    sw = sliding_window_view(a, win)
    cur = a[win:n]; past = sw[0:n - win]
    with np.errstate(invalid="ignore"):
        out[win:n] = np.nanmean(past < cur[:, None], axis=1)
    return out


def restrict_universe(P):
    keep = {}
    for s, d in P.items():
        first = datetime.utcfromtimestamp(int(d["t"][0]) / 1000).date()
        if first <= CUTOFF_EXIST and np.isfinite(d["oi"]).sum() > 5000:
            keep[s] = d
    return keep


def fwd(c, i, h):
    return math.log(c[i + h] / c[i]) if i + h < len(c) else None


def report(bucket, label):
    print(f"\n--- {label} ---")
    out = {}
    for h in HOR:
        R = agg_pairs(bucket.get(h, []))
        out[h] = R
        if "mean_bp" not in R:
            print(f"  {hlabel(h):>4}: n={R.get('n')}"); continue
        print(f"  {hlabel(h):>4}: {R['mean_bp']:>7.2f}bp CI[{R['ci_bp'][0]:>6.1f},{R['ci_bp'][1]:>6.1f}] "
              f"excl0={str(R['ci_excl_0']):5s} h1/h2=({R['half1_bp']:.0f},{R['half2_bp']:.0f}) "
              f"symPos={R['frac_sym_pos']} conc={R['top5_conc']} n={R['n']} nS={R['n_sym']}")
    return out


def econ_sim(events, hold_bars, slots, cap, fh, label):
    """events: list de (entry_ms, sym, entry_i, side) side=+1 LONG,-1 SHORT."""
    notional = cap / slots
    free_at = [0] * slots
    trades = []
    for (ems, s, ei, side, P) in events:
        fslot = next((k for k in range(slots) if free_at[k] <= ems), None)
        if fslot is None:
            continue
        o = P[s]["o"]
        if ei + hold_bars >= len(o):
            continue
        g = side * math.log(o[ei + hold_bars] / o[ei]) * 1e4
        fcost = 0.0
        if s in fh:
            ct, fr = fh[s]; t0 = int(P[s]["t"][ei])
            m = (ct >= t0) & (ct < t0 + hold_bars * 15 * 60000)
            fcost = side * float(fr[m].sum()) * 1e4   # LONG paga funding+ (side=+1) ; SHORT lo recibe (side=-1)
        net = g - RT_BP - fcost
        free_at[fslot] = ems + hold_bars * 15 * 60000
        trades.append((ems, net, notional))
    if not trades:
        print(f"    {label}: sin trades"); return None
    span_days = (trades[-1][0] - trades[0][0]) / 86400000 or 1
    arr = np.array([t[1] for t in trades]); pnl = np.array([t[1] * t[2] / 1e4 for t in trades])
    import collections
    bym = collections.defaultdict(float)
    for (ems, net, notn) in trades:
        bym[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += net * notn / 1e4
    months = np.array(sorted(bym.values())) if bym else np.array([0.0])
    net_mo = pnl.sum() / (span_days / 30)
    flag = "  <<< SUPERA 150" if net_mo >= 150 else ""
    print(f"    {label}: trades/mo={len(trades)/(span_days/30):.0f} NET/mo=${net_mo:.0f} "
          f"avg={arr.mean():+.1f}bp med={np.median(arr):+.1f}bp WR={(arr>0).mean():.2f} "
          f"PF={arr[arr>0].sum()/max(1e-9,-arr[arr<0].sum()):.2f} "
          f"m[P5/50/95]=[{np.percentile(months,5):.0f}/{np.median(months):.0f}/{np.percentile(months,95):.0f}]{flag}")
    return net_mo


def main():
    print("=== ROUND 12 — SMART MONEY DIVERGENCE + OI ACCELERATION ===")
    P, bret, btpos = load_panel()
    P = restrict_universe(P)
    print(f"universo: {len(P)}/63 símbolos (existen <= {CUTOFF_EXIST})")
    bc = P["BTCUSDT"]["c"]; btms = {int(t): i for i, t in enumerate(P["BTCUSDT"]["t"])}

    F = {}
    for s, d in P.items():
        c = d["c"]; n = len(c)
        z_gls = zscore_causal(d["gls"], ROLL)
        z_ttls = zscore_causal(d["ttls"], ROLL)
        Dv = z_gls - z_ttls
        z_D = zscore_causal(Dv, ROLL)
        pct_D = pctile_causal(Dv, ROLL)
        oi = d["oi"]
        oi1 = np.concatenate([np.full(W, np.nan), np.log(np.where(oi[W:] > 0, oi[W:], np.nan) / np.where(oi[:-W] > 0, oi[:-W], np.nan))])
        oi2 = np.concatenate([np.full(W, np.nan), oi1[W:] - oi1[:-W]])
        z_oi2 = zscore_causal(oi2, ROLL)
        retW = np.concatenate([np.full(W, np.nan), np.log(c[W:] / c[:-W])])
        r1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
        r4h = np.concatenate([np.full(16, np.nan), np.log(c[16:] / c[:-16])])
        r24h = np.concatenate([np.full(96, np.nan), np.log(c[96:] / c[:-96])])
        rv = np.full(n, np.nan)
        cs2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r1) ** 2)])
        for i in range(96, n):
            rv[i] = math.sqrt((cs2[i] - cs2[i - 96]) / 96)
        z_vol = zscore_causal(d["v"], ROLL)
        bal = np.array([bret[btpos[int(t)]] if int(t) in btpos else np.nan for t in d["t"]])
        F[s] = dict(z_gls=z_gls, z_ttls=z_ttls, D=Dv, z_D=z_D, pct_D=pct_D, oi1=oi1, oi2=oi2, z_oi2=z_oi2,
                    retW=retW, r1=r1, r4h=r4h, r24h=r24h, rv=rv, z_vol=z_vol, btc1h=bal)

    all_days = []
    for s, d in P.items():
        f = F[s]
        valid = np.where(np.isfinite(f["pct_D"]))[0]
        for i in valid[ROLL:]:
            all_days.append(datetime.utcfromtimestamp(int(d["t"][i]) / 1000).date())
    days = sorted(set(all_days))
    tcut, vcut = days[int(len(days) * 0.5)], days[int(len(days) * 0.75)]
    print(f"corte temporal: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")
    def seg(dy): return "train" if dy <= tcut else ("val" if dy <= vcut else "oos")

    # ================= MECANISMO 1: SMART MONEY DIVERGENCE =================
    print("\n" + "#" * 70 + "\n# MECANISMO 1 — RETAIL vs SMART-MONEY DIVERGENCE\n" + "#" * 70)

    THR = 0.95   # primario predeclarado; 90/97.5/99 = sensibilidad diagnostica
    def events_for(thr):
        RL, RS = [], []
        for s, d in P.items():
            f = F[s]; n = len(d["c"])
            hi = f["pct_D"] >= thr; lo = f["pct_D"] <= (1 - thr)
            last = -999
            for i in np.where(hi)[0]:
                if i < ROLL or i + max(HOR) + 2 >= n or i - last < W:
                    continue
                last = i; RL.append((s, i))
            last = -999
            for i in np.where(lo)[0]:
                if i < ROLL or i + max(HOR) + 2 >= n or i - last < W:
                    continue
                last = i; RS.append((s, i))
        return RL, RS

    RL, RS = events_for(THR)
    print(f"\nP{int(THR*100)}: retail-LONG/smart-SHORT eventos={len(RL)}  retail-SHORT/smart-LONG eventos={len(RS)}")

    def build_bucket(evs):
        b = {h: [] for h in HOR}
        segb = {sg: {h: [] for h in HOR} for sg in ("train", "val", "oos")}
        for (s, i) in evs:
            dy = datetime.utcfromtimestamp(int(P[s]["t"][i]) / 1000).date()
            sgv = seg(dy)
            for h in HOR:
                v = fwd(P[s]["c"], i, h)
                if v is None:
                    continue
                b[h].append((s, v)); segb[sgv][h].append((s, v))
        return b, segb

    rl_b, rl_seg = build_bucket(RL)
    rs_b, rs_seg = build_bucket(RS)
    report(rl_b, f"P{int(THR*100)} RETAIL-LONG/SMART-SHORT — raw fwd (+ = precio sube)")
    report(rs_b, f"P{int(THR*100)} RETAIL-SHORT/SMART-LONG — raw fwd (+ = precio sube)")
    print("\n  TRAIN/VAL/OOS (raw @4h,8h):")
    for name, segb in (("RL_SS", rl_seg), ("RS_SL", rs_seg)):
        for sg in ("train", "val", "oos"):
            r16 = agg_pairs(segb[sg][16]); r32 = agg_pairs(segb[sg][32])
            print(f"    {name} {sg:5s}: 4h={r16.get('mean_bp')}bp(n={r16.get('n')})  8h={r32.get('mean_bp')}bp(n={r32.get('n')})")

    # sensibilidad de threshold (diagnostico, @4h)
    print("\n  sensibilidad threshold (@4h, raw):")
    for thr in PCTS:
        rl2, rs2 = events_for(thr)
        b1, _ = build_bucket(rl2); b2, _ = build_bucket(rs2)
        R1 = agg_pairs(b1[16]); R2 = agg_pairs(b2[16])
        print(f"    P{thr*100:.1f}: RL_SS={R1.get('mean_bp')}bp(n={R1.get('n')})  RS_SL={R2.get('mean_bp')}bp(n={R2.get('n')})")

    # placebos
    print("\n  PLACEBOS (P95, @2h/@4h/@8h, raw):")
    # matched control: |z_D| <= 0.3
    mc = {h: [] for h in HOR}
    for s, d in P.items():
        f = F[s]; n = len(d["c"]); last = -999
        for i in np.where(np.abs(f["z_D"]) <= 0.3)[0][::5]:
            if i < ROLL or i + max(HOR) >= n or i - last < W:
                continue
            last = i
            for h in HOR:
                v = fwd(d["c"], i, h)
                if v is not None:
                    mc[h].append((s, v))
    for h in (8, 16, 32):
        R = agg_pairs(mc[h]); print(f"    matched(|z_D|<=0.3) {hlabel(h)}: {R.get('mean_bp')}bp n={R.get('n')}")
    # time-shift +24h
    def timeshift(evs, sh=96):
        b = {h: [] for h in (8, 16, 32)}
        for (s, i) in evs:
            for h in (8, 16, 32):
                if i + sh + h < len(P[s]["c"]):
                    b[h].append((s, fwd(P[s]["c"], i + sh, h)))
        return b
    tsl = timeshift(RL); tsr = timeshift(RS)
    for h in (8, 16, 32):
        print(f"    time-shift+24h RL {hlabel(h)}: {agg_pairs(tsl[h]).get('mean_bp')}bp   "
              f"RS {hlabel(h)}: {agg_pairs(tsr[h]).get('mean_bp')}bp")
    # random-ranking: mezclar simbolo<->evento (mismo timestamp set, simbolo aleatorio)
    all_syms = list(P.keys())
    rr = {h: [] for h in (8, 16, 32)}
    for (s, i) in RL[:min(len(RL), 3000)]:
        s2 = all_syms[rng.integers(0, len(all_syms))]
        j = P[s2]["pos"].get(int(P[s]["t"][i]))
        if j is None:
            continue
        for h in (8, 16, 32):
            v = fwd(P[s2]["c"], j, h)
            if v is not None:
                rr[h].append((s2, v))
    for h in (8, 16, 32):
        print(f"    random-ranking RL {hlabel(h)}: {agg_pairs(rr[h]).get('mean_bp')}bp n={agg_pairs(rr[h]).get('n')}")

    # regresion incremental
    print("\n  REGRESION INCREMENTAL: fwd ~ 1 + D + r1 + r1h(retW) + r4h + r24h + rv + vol + btc1h + oi1")
    for h in (8, 16):
        rows = []
        for s, d in P.items():
            f = F[s]; n = len(d["c"])
            idx = np.where(np.isfinite(f["pct_D"]))[0]
            idx = idx[(idx >= ROLL) & (idx + h < n)]
            idx = idx[::3]     # submuestreo para no explotar tamaño
            for i in idx:
                v = fwd(d["c"], i, h)
                if v is None:
                    continue
                row = (f["D"][i], f["r1"][i], f["retW"][i], f["r4h"][i], f["r24h"][i], f["rv"][i], f["z_vol"][i], f["btc1h"][i], f["oi1"][i], v)
                rows.append(row)
        rows = [r for r in rows if all(np.isfinite(x) for x in r)]
        if len(rows) < 500:
            print(f"    h={hlabel(h)}: n={len(rows)} insuficiente"); continue
        X = np.array([[1] + list(r[:-1]) for r in rows]); y = np.array([r[-1] for r in rows])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta; s2 = (resid @ resid) / (len(y) - X.shape[1])
        se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
        X0 = X[:, 1:]; b0, *_ = np.linalg.lstsq(X0, y, rcond=None)
        dr2 = (1 - resid.var() / y.var()) - (1 - (y - X0 @ b0).var() / y.var())
        print(f"    h={hlabel(h):>3} n={len(rows)}: t(D)={beta[1]/se[1]:+.2f}  dR2(D)={dr2:+.5f}  "
              f"beta_D={beta[1]:+.5f}")

    # sim economica inmediata (ambas direcciones, ambos horizontes candidatos)
    print("\n  SIM ECONOMICA INMEDIATA (entrada open[t+1], RT=24bp+funding, cap<=450):")
    fh = {}
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    for s in P:
        rows = con.execute("SELECT calc_time,funding_rate FROM funding_hist WHERE symbol=? ORDER BY calc_time", (s,)).fetchall()
        if rows:
            fh[s] = (np.array([r[0] for r in rows], np.int64), np.array([r[1] for r in rows], float))
    con.close()

    m1_results = {}
    for name, evs, side in (("RL_SS_SHORT", RL, -1), ("RL_SS_LONG", RL, +1),
                            ("RS_SL_LONG", RS, +1), ("RS_SL_SHORT", RS, -1)):
        events = [(int(P[s]["t"][i + 1]), s, i + 1, side, P) for (s, i) in evs if i + 1 < len(P[s]["o"])]
        events.sort(key=lambda x: x[0])
        for hold in (16, 32):
            for slots, cap in ((1, 450), (2, 450)):
                lbl = f"{name} hold={hlabel(hold)} {slots}x${cap//slots}"
                r = econ_sim(events, hold, slots, cap, fh, lbl)
                m1_results[lbl] = r

    best_m1 = max([v for v in m1_results.values() if v is not None], default=-1e9)
    print(f"\n  >>> MEJOR NET/mes Mecanismo 1: ${best_m1:.0f}")

    # ================= MECANISMO 2: OI ACCELERATION (fallback, siempre calculado) =================
    print("\n" + "#" * 70 + "\n# MECANISMO 2 — OI ACCELERATION (fallback)\n" + "#" * 70)
    ACC_Z = 1.5
    conf_ev, div_ev = [], []
    for s, d in P.items():
        f = F[s]; n = len(d["c"]); last = -999
        sig = np.abs(f["z_oi2"]) >= ACC_Z
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + 2 >= n or i - last < W:
                continue
            last = i
            confirm = np.sign(f["oi2"][i]) == np.sign(f["retW"][i])
            (conf_ev if confirm else div_ev).append((s, i))
    print(f"eventos |z_oi2|>=1.5: confirmado(precio+accel mismo signo)={len(conf_ev)}  divergente={len(div_ev)}")
    cb, cseg = build_bucket(conf_ev); db, dseg = build_bucket(div_ev)
    report(cb, "OI-ACCEL confirmado (precio y aceleración de OI mismo signo) — raw fwd")
    report(db, "OI-ACCEL divergente (precio y aceleración de OI signo opuesto) — raw fwd")
    print("\n  TRAIN/VAL/OOS (raw @4h):")
    for name, segb in (("confirm", cseg), ("diverge", dseg)):
        cells = "  ".join(f"{sg}={agg_pairs(segb[sg][16]).get('mean_bp')}bp(n={agg_pairs(segb[sg][16]).get('n')})" for sg in ("train", "val", "oos"))
        print(f"    {name}: {cells}")

    # direccion fijada por el signo de TRAIN (no post-hoc sobre VAL/OOS), luego se evalua economicamente en VAL+OOS
    m2_results = {}
    for name, evs, segb in (("confirm", conf_ev, cseg), ("diverge", div_ev, dseg)):
        tr16 = agg_pairs(segb["train"][16])
        if "mean_bp" not in tr16 or tr16["n"] < 30:
            print(f"  {name}: TRAIN insuficiente, se omite sim econ"); continue
        side = 1 if tr16["mean_bp"] > 0 else -1     # LONG si TRAIN fue positivo, SHORT si negativo
        valoos = [(s, i) for (s, i) in evs if seg(datetime.utcfromtimestamp(int(P[s]["t"][i]) / 1000).date()) != "train"]
        events = [(int(P[s]["t"][i + 1]), s, i + 1, side, P) for (s, i) in valoos if i + 1 < len(P[s]["o"])]
        events.sort(key=lambda x: x[0])
        print(f"  {name}: direccion fijada por TRAIN = {'LONG' if side>0 else 'SHORT'}  (VAL+OOS n={len(events)})")
        for hold in (16, 32):
            for slots, cap in ((1, 450), (2, 450)):
                lbl = f"OI-ACC {name} side={'L' if side>0 else 'S'} hold={hlabel(hold)} {slots}x${cap//slots}"
                r = econ_sim(events, hold, slots, cap, fh, lbl)
                m2_results[lbl] = r

    best_m2 = max([v for v in m2_results.values() if v is not None], default=-1e9)
    print(f"\n  >>> MEJOR NET/mes Mecanismo 2 (VAL+OOS, direccion fijada en TRAIN): ${best_m2:.0f}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "universe": len(P), "tcut": str(tcut), "vcut": str(vcut),
           "n_RL": len(RL), "n_RS": len(RS), "n_confirm": len(conf_ev), "n_diverge": len(div_ev),
           "best_m1_usd_mo": best_m1, "best_m2_usd_mo": best_m2,
           "m1_results": m1_results, "m2_results": m2_results}
    json.dump(out, open(os.path.join(ROOT, "scratch_r12_smartmoney.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r12_smartmoney.json")
    print(f"\n=== RESUMEN: mejor M1=${best_m1:.0f}/mes  mejor M2=${best_m2:.0f}/mes  target=$150/mes ===")


if __name__ == "__main__":
    main()
