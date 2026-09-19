"""
ROUND 11 — dOI ECONOMIC RESCUE-OR-KILL.
Ventana EXTENDIDA (klines_clean 15m + oi_metrics 5m ahora desde 2025-06).
Repite EXACTAMENTE el test de régimen de R10 (misma def A/D, régimen BTC ±1.5%
sobre trailing 24h, mismos horizontes, mismos controles) + estacionariedad por
mes/trimestre/mitad + leave-top-k + sim económica causal con capital <=450.

Universo: EX-ANTE (oi_universe.json) restringido a símbolos con klines Y oi_metrics
desde <= 2025-07-01 (existían antes de TRAIN). Se documenta cuántos quedan.
NO se agregan features (top-trader L/S, OI accel, taker, funding-como-señal, ML):
prohibido en R11. Funding SÍ entra pero solo como COSTO real en la sim económica.
"""
import os, sys, json, math, numpy as np, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import zscore_causal, agg_pairs
from r9_oi_alpha import load_panel
from r10_doi_regime import build_feats, regime, HOR, hlabel, ROLL, W, REG_THR
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CUTOFF_EXIST = date(2025, 7, 1)           # símbolo debe existir antes de esto
FEE_SIDE = 5.0; SPREAD_SIDE = 3.0; SLIP_SIDE = 4.0
RT_BP = 2 * (FEE_SIDE + SPREAD_SIDE + SLIP_SIDE)     # 24 bp
rng = np.random.default_rng(20260914)


def main():
    print("=== ROUND 11 — dOI ECONOMIC RESCUE-OR-KILL ===")
    P, bret, btpos = load_panel()
    # restringir universo
    keep = {}
    for s, d in P.items():
        first = datetime.utcfromtimestamp(int(d["t"][0]) / 1000).date()
        oi_ok = np.isfinite(d["oi"]).sum() > 5000
        if first <= CUTOFF_EXIST and oi_ok:
            keep[s] = d
    dropped = sorted(set(P) - set(keep))
    P = keep
    F, btc_tr, mkt_cum = build_feats(P, bret, btpos)
    bc = P["BTCUSDT"]["c"]; btms = {int(t): i for i, t in enumerate(P["BTCUSDT"]["t"])}
    span = (min(int(d["t"][0]) for d in P.values()), max(int(d["t"][-1]) for d in P.values()))
    def dd(ms): return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    print(f"universo restringido: {len(P)}/63 símbolos (existen <= {CUTOFF_EXIST}, OI ok)")
    print(f"dropados ({len(dropped)}): {dropped}")
    print(f"span de datos: {dd(span[0])} .. {dd(span[1])}")

    # ---- eventos A/D (def congelada) ----
    EV = []   # (sym, i, quad, regime, day, entry_open_idx)
    for s, d in P.items():
        f = F[s]; c = d["c"]; n = len(c)
        sig = (np.abs(f["z_ret"]) >= 1.0) & (np.abs(f["z_doi"]) >= 1.0)
        last = {"A": -999, "D": -999}
        for i in np.where(sig)[0]:
            if i < ROLL or i + max(HOR) + 2 >= n:
                continue
            sr = np.sign(f["retW"][i]); so = np.sign(f["dOI"][i])
            q = "A" if (sr < 0 and so > 0) else ("D" if (sr > 0 and so < 0) else None)
            if q is None or i - last[q] < W:
                continue
            last[q] = i
            tms = int(d["t"][i]); reg = regime(btc_tr.get(tms))
            if reg is None:
                continue
            EV.append((s, i, q, reg, datetime.utcfromtimestamp(tms / 1000).date(), i + 1))
    print(f"\neventos A/D totales (ventana extendida, universo restringido): {len(EV)}")
    days = sorted(set(e[4] for e in EV))
    tcut, vcut = days[int(len(days) * 0.5)], days[int(len(days) * 0.75)]
    print(f"corte temporal: TRAIN <= {tcut} · VAL <= {vcut} · OOS > {vcut}")
    def seg(dy): return "train" if dy <= tcut else ("val" if dy <= vcut else "oos")

    def sfwd(s, i, h):
        c = P[s]["c"]
        return -math.log(c[i + h] / c[i]) if i + h < len(c) else None

    # ---- (Fase 2) matriz régimen × TRAIN/VAL/OOS  (A+D SHORT) ----
    print("\n" + "=" * 66 + "\n(FASE 2) MATRIZ RÉGIMEN × TRAIN/VAL/OOS  (A+D SHORT, bp; *=CI excl 0)\n" + "=" * 66)
    matrix = {}
    for reg in ("UP", "FLAT", "DOWN"):
        matrix[reg] = {}
        for sg in ("train", "val", "oos"):
            row = {}
            for h in HOR:
                pairs = [(s, sfwd(s, i, h)) for (s, i, q, r, dy, e) in EV if r == reg and seg(dy) == sg and sfwd(s, i, h) is not None]
                R = agg_pairs(pairs)
                row[hlabel(h)] = (R.get("mean_bp"), R.get("n"), R.get("ci_excl_0"))
            matrix[reg][sg] = row
        print(f"\n  [{reg}]")
        for sg in ("train", "val", "oos"):
            nn = matrix[reg][sg]["4h"][1]
            cells = "  ".join(f"{hlabel(h)}={(lambda x:f'{x:+.0f}' if x is not None else 'na')(matrix[reg][sg][hlabel(h)][0])}"
                              f"{'*' if matrix[reg][sg][hlabel(h)][2] else ' '}" for h in HOR)
            print(f"    {sg:5s} n~{nn}: {cells}")

    # ---- (Fase 3) ESTACIONARIEDAD: signed_fwd @4h por mes / trimestre / mitad ----
    print("\n" + "=" * 66 + "\n(FASE 3) ESTACIONARIEDAD — A+D SHORT @4h (h=16), por período\n" + "=" * 66)
    def bucket_stats(getkey):
        b = {}
        for (s, i, q, r, dy, e) in EV:
            v = sfwd(s, i, 16)
            if v is None:
                continue
            b.setdefault((getkey(dy), "ALL"), []).append((s, v))
            b.setdefault((getkey(dy), r), []).append((s, v))
        return b
    def ym(dy): return f"{dy.year}-{dy.month:02d}"
    def yq(dy): return f"{dy.year}Q{(dy.month - 1) // 3 + 1}"
    def half(dy): return "H1" if dy <= days[len(days) // 2] else "H2"

    for name, fn in (("MES", ym), ("TRIMESTRE", yq), ("MITAD", half)):
        b = bucket_stats(fn)
        keys = sorted(set(k[0] for k in b))
        print(f"\n  por {name}:  (ALL | UP | FLAT | DOWN)  bp @4h [n]")
        for k in keys:
            def cell(reg):
                R = agg_pairs(b.get((k, reg), []))
                if "mean_bp" not in R:
                    return f"{'na':>8}[{R.get('n',0)}]"
                star = "*" if R["ci_excl_0"] else " "
                return f"{R['mean_bp']:+7.0f}{star}[{R['n']}]"
            print(f"    {k:8s}: {cell('ALL')}  {cell('UP')}  {cell('FLAT')}  {cell('DOWN')}")

    # ---- OLS beta-control por régimen, ventana extendida ----
    print("\n" + "=" * 66 + "\n(FASE 3b) OLS beta-control ventana extendida: signed_fwd ~ 1 + dOI + btc_fwd + mkt_fwd + retlong + rv\n" + "=" * 66)
    for reg in ("UP", "FLAT", "DOWN"):
        for h in (8, 16):
            rows = []
            for (s, i, q, r, dy, e) in EV:
                if r != reg:
                    continue
                v = sfwd(s, i, h)
                if v is None:
                    continue
                bi = btms.get(int(P[s]["t"][i]))
                bf = math.log(bc[bi + h] / bc[bi]) if (bi is not None and bi + h < len(bc)) else np.nan
                mf = (mkt_cum.get(int(P[s]["t"][i + h])) - mkt_cum.get(int(P[s]["t"][i]))) if (int(P[s]["t"][i + h]) in mkt_cum and int(P[s]["t"][i]) in mkt_cum) else np.nan
                rows.append((F[s]["dOI"][i], bf, mf, F[s]["retlong"][i], F[s]["rv"][i], v))
            rows = [x for x in rows if all(np.isfinite(z) for z in x)]
            if len(rows) < 200:
                print(f"  {reg} {hlabel(h)}: n={len(rows)}"); continue
            X = np.array([[1, a, b2, c2, d2, e2] for (a, b2, c2, d2, e2, y) in rows]); y = np.array([r2[5] for r2 in rows])
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ beta
            se = np.sqrt(np.diag((resid @ resid) / (len(y) - 6) * np.linalg.inv(X.T @ X)))
            X0 = X[:, [0, 2, 3, 4, 5]]; b0, *_ = np.linalg.lstsq(X0, y, rcond=None)
            dr2 = (1 - resid.var() / y.var()) - (1 - (y - X0 @ b0).var() / y.var())
            print(f"  {reg:5s} {hlabel(h):>3}: t(dOI)={beta[1]/se[1]:+.2f}  dR2={dr2:+.4f}  n={len(rows)}")

    # ---- (Fase 4) leave-top-k  (UP∪FLAT, @4h) ----
    print("\n" + "=" * 66 + "\n(FASE 4) CONCENTRACIÓN — leave-top-k, UP∪FLAT SHORT @4h\n" + "=" * 66)
    upflat = [(s, i) for (s, i, q, r, dy, e) in EV if r in ("UP", "FLAT")]
    by = {}
    for (s, i) in upflat:
        v = sfwd(s, i, 16)
        if v is not None:
            by.setdefault(s, []).append(v)
    order = sorted(by, key=lambda s: np.sum(by[s]), reverse=True)
    print(f"  {'excl':10s} {'edge_bp':>9s} {'PF':>6s} {'nSym':>5s} {'net_bp':>8s} {'n':>7s}")
    for k in (0, 1, 3, 5, 7):
        drop = set(order[:k])
        v = np.concatenate([np.array(by[s]) for s in by if s not in drop]) if k < len(by) else np.array([0.0])
        vb = v * 1e4
        pf = vb[vb > 0].sum() / max(1e-9, -vb[vb < 0].sum())
        print(f"  top{k:<7d} {vb.mean():>9.1f} {pf:>6.2f} {len(by)-k:>5d} {vb.mean()-RT_BP:>8.1f} {len(v):>7d}")

    # ---- (Fase 6-7) SIM ECONÓMICA causal, capital <=450, concurrencia ----
    print("\n" + "=" * 66 + f"\n(FASE 6-7) SIM ECONÓMICA — entrada open[t+1], SHORT, RT={RT_BP}bp + funding real\n" + "=" * 66)
    # funding real por símbolo
    fh = {}
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    for s in P:
        rows = con.execute("SELECT calc_time,funding_rate FROM funding_hist WHERE symbol=? ORDER BY calc_time", (s,)).fetchall()
        if rows:
            fh[s] = (np.array([r[0] for r in rows], np.int64), np.array([r[1] for r in rows], float))
    con.close()

    def funding_cost_bp(s, t0_ms, hold_ms):
        """coste de funding para un SHORT durante [t0, t0+hold]. short RECIBE funding positivo."""
        if s not in fh:
            return 0.0
        ct, fr = fh[s]
        m = (ct >= t0_ms) & (ct < t0_ms + hold_ms)
        # short paga -funding: si funding>0 short gana => coste negativo
        return -float(fr[m].sum()) * 1e4

    def simulate(events_sorted, hold_bars, n_slots, cap_total):
        """events_sorted: list de (entry_ms, sym, entry_i). Cierre por horizonte fijo."""
        notional = cap_total / n_slots
        slots_free_at = [0] * n_slots
        trades = []
        for (ems, s, ei) in events_sorted:
            fslot = next((k for k in range(n_slots) if slots_free_at[k] <= ems), None)
            if fslot is None:
                continue
            o = P[s]["o"]
            if ei + hold_bars >= len(o):
                continue
            g = -math.log(o[ei + hold_bars] / o[ei]) * 1e4      # SHORT gross bp
            fcost = funding_cost_bp(s, int(P[s]["t"][ei]), hold_bars * 15 * 60000)
            net = g - RT_BP - fcost
            slots_free_at[fslot] = ems + hold_bars * 15 * 60000
            trades.append((ems, net, notional))
        if not trades:
            return None
        span_days = (trades[-1][0] - trades[0][0]) / 86400000
        arr = np.array([t[1] for t in trades])
        pnl_usd = np.array([t[1] * t[2] / 1e4 for t in trades])
        # PnL mensual
        import collections
        bym = collections.defaultdict(float)
        for (ems, net, notn) in trades:
            mk = datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")
            bym[mk] += net * notn / 1e4
        months = np.array(sorted(bym.values()))
        eq = np.cumsum(pnl_usd); ddu = (np.maximum.accumulate(eq) - eq).max()
        return dict(n=len(trades), trades_mo=len(trades) / (span_days / 30),
                    avg_net_bp=float(arr.mean()), med_net_bp=float(np.median(arr)),
                    wr=float((arr > 0).mean()),
                    pf=float(arr[arr > 0].sum() / max(1e-9, -arr[arr < 0].sum())),
                    net_mo_usd=float(pnl_usd.sum() / (span_days / 30)),
                    maxdd_usd=float(ddu),
                    months_pos=int((months > 0).sum()), months_neg=int((months < 0).sum()),
                    m_p5=float(np.percentile(months, 5)), m_p50=float(np.median(months)),
                    m_p95=float(np.percentile(months, 95)))

    for regset, rname in ((("UP", "FLAT"), "UP∪FLAT"), (("UP",), "UP"), (("FLAT",), "FLAT"),
                          (("UP", "FLAT", "DOWN"), "ALL")):
        evs = sorted([(int(P[s]["t"][e]), s, e) for (s, i, q, r, dy, ee) in EV if r in regset for e in (ee,)])
        print(f"\n  --- {rname}  ({len(evs)} eventos candidatos) ---")
        for hold in (16, 32):
            for slots, cap in ((1, 450), (2, 450), (3, 450)):
                R = simulate(evs, hold, slots, cap)
                if R is None:
                    continue
                flag = "  <<<" if R["net_mo_usd"] >= 150 else ""
                print(f"    hold={hlabel(hold):>3} slots={slots}x${cap//slots:<3} : "
                      f"trades/mo={R['trades_mo']:5.0f}  NET/mo=${R['net_mo_usd']:7.0f}  "
                      f"avg={R['avg_net_bp']:+6.1f}bp med={R['med_net_bp']:+6.1f}bp WR={R['wr']:.2f} PF={R['pf']:.2f}  "
                      f"mDD=${R['maxdd_usd']:.0f}  m+/-={R['months_pos']}/{R['months_neg']}  "
                      f"m[P5/P50/P95]=[{R['m_p5']:.0f}/{R['m_p50']:.0f}/{R['m_p95']:.0f}]{flag}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "universe_kept": len(P), "dropped": dropped, "span": [dd(span[0]), dd(span[1])],
           "n_events": len(EV), "tcut": str(tcut), "vcut": str(vcut), "matrix": matrix}
    json.dump(out, open(os.path.join(ROOT, "scratch_r11_stationarity.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r11_stationarity.json")


if __name__ == "__main__":
    main()
