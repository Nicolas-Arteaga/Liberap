"""
GATE V4 — GOLD STANDARD (Phase 3). Criterios PRE-REGISTRADOS: GATE_V4_CRITERIA.md.

NO intenta demostrar que el motor funciona. NO ajusta parametros. NO fuerza
coincidencia de trades. Pregunta unica: ¿el motor clasifica bien ganadora/perdedora
y estima la expectancy agregada de forma robusta para decidir research?

Benchmark: 7 estrategias pre-declaradas (ver GATE_V4_CRITERIA.md §1).
  MaGeometry (Caso 1/2/3/3-15m): Monte Carlo COMPLETO (precompute 1x + slot_sim Nx
    con jitter de admision/liberacion, desempates y seeds).
  FVG (15m/1m) y ADN Micro: 1 corrida fiel + Monte Carlo de FIFO de cupos
    (re-_capital_sim con desempate perturbado) — cobertura MC reducida, marcada.

Salidas: scratch_gate_v4_*.json + BACKTEST_RELIABILITY_PHASE3_REPORT insumos + stdout.
"""
import os, sys, json, csv, math, subprocess, statistics as st, time
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
ROOT = os.path.join(HERE, "..", "..")
BV_DB = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
ALL_CSV = os.path.join(ROOT, "scratch_all_trades_p2.csv")
OUT = os.path.join(ROOT, "scratch_gate_v4_results.json")

ARG_OFF = 3 * 3600 * 1000

BENCH = [
    dict(name="MA Slope Caso 3",             fam="MaGeometry",     cls="WINNER"),
    dict(name="FVG - 15m",                   fam="FVG",            cls="WINNER"),
    dict(name="MA Slope Caso 3 (15m)",       fam="MaGeometry",     cls="WINNER"),
    dict(name="MA Slope Caso 1",             fam="MaGeometry",     cls="NEUTRAL"),   # borderline PF 0.91
    dict(name="FVG - 1m",                    fam="FVG",            cls="LOSER"),
    dict(name="Compresion ADN - Micro (5m)", fam="AdnCompression", cls="LOSER"),
    dict(name="MA Slope Caso 2",             fam="MaGeometry",     cls="LOSER"),
]

SEEDS = int(os.environ.get("V4_SEEDS", "80"))
# grid de perturbacion: (jitter_s, jitter_ticks, tiebreak). El 1o es el baseline
# determinista; el resto varian con seed.
PERTURB = [(0, 0, "sym_asc")] + [
    (js, 0, "shuffle") for js in (0, 1, 2, 5, 10)
] + [(0, jt, "shuffle") for jt in (1, 2)]
COSTS_BP = [0, 2, 5]


def ms(iso):
    if not iso:
        return None
    s = iso.strip().replace("T", " ").replace("Z", "")
    for x in ("+00:00", "+00"):
        if s.endswith(x):
            s = s[:-len(x)].strip()
    if "." in s:
        h, fr = s.split("."); s = h + "." + (fr + "000000")[:6]
        return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp() * 1000)
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def q1(sql):
    return subprocess.check_output(["docker", "exec", "verge-db", "psql", "-U", "postgres",
                                    "-d", "Verge", "-t", "-A", "-F", "\t", "-c", sql]).decode()


def load_profile(name):
    esc = name.replace("'", "''")
    j = q1('SELECT row_to_json(t) FROM (SELECT "Id" as id,"Name" as name,"StrategyType" as "strategyType",'
           '"AllowLong" as "allowLong","AllowShort" as "allowShort","TpMultiplier" as "tpMultiplier",'
           '"SlMultiplier" as "slMultiplier","MinRR" as "minRR","MarginPerTrade" as "marginPerTrade",'
           '"MaxOpenPositions" as "maxOpenPositions","MaxTradeDurationCandles" as "maxTradeDurationCandles",'
           f"\"PatternParamsJson\" as \"patternParamsJson\" FROM \"StrategyProfiles\" WHERE \"Name\"='{esc}') t;").strip()
    return json.loads(j)


def load_real(name):
    esc = name.replace("'", "''")
    rows = q1(f"""SELECT st."Symbol", st."Side", st."OpenedAt", st."ClosedAt",
        st."RealizedPnl", st."ExitReason"
        FROM "SimulatedTrades" st JOIN "StrategyProfiles" sp ON sp."Id"=st."StrategyProfileId"
        WHERE sp."Name"='{esc}' AND st."IsDeleted"=false AND st."ClosedAt" IS NOT NULL
        ORDER BY st."OpenedAt";""").strip().splitlines()
    out = []
    for ln in rows:
        p = ln.split("\t")
        if len(p) < 6:
            continue
        out.append(dict(symbol=p[0], side=int(p[1]), open=ms(p[2]), close=ms(p[3]),
                        pnl=float(p[4]) if p[4] else 0.0, reason=p[5]))
    return out


def stats(pnls, wins_n, durs_h, opens, closes):
    n = len(pnls)
    if n == 0:
        return dict(n=0, net=0, pf=float("nan"), exp=0, wr=0, dur=0, mdd=0, expo=0)
    pos = sum(p for p in pnls if p > 0); neg = -sum(p for p in pnls if p < 0)
    eq = 0.0; peak = 0.0; mdd = 0.0
    for p in pnls:
        eq += p; peak = max(peak, eq); mdd = min(mdd, eq - peak)
    # exposicion aproximada: suma de horas-posicion / horas de ventana
    span_h = (max(closes) - min(opens)) / 3600000 if opens else 1
    expo = (sum(durs_h) / span_h) if span_h else 0
    return dict(n=n, net=round(sum(pnls), 2), pf=(pos / neg if neg else float("inf")),
                exp=sum(pnls) / n, wr=100 * wins_n / n, dur=(st.median(durs_h) if durs_h else 0),
                mdd=round(mdd, 2), expo=round(expo, 2))


def real_stats(trades):
    pnls = [t["pnl"] for t in trades]
    wins = sum(1 for t in trades if "tp" in (t["reason"] or "").lower())
    durs = [(t["close"] - t["open"]) / 3600000 for t in trades if t["open"] and t["close"]]
    opens = [t["open"] for t in trades if t["open"]]
    closes = [t["close"] for t in trades if t["close"]]
    return stats(pnls, wins, durs, opens, closes)


def bt_stats(accepted):
    pnls = [t["pnl"] for t in accepted]
    wins = sum(1 for t in accepted if t["close_reason"] == "TP")
    durs = [(t["close_time"] - t["open_time"]) / 3600000 for t in accepted]
    opens = [t["open_time"] for t in accepted]
    closes = [t["close_time"] for t in accepted]
    return stats(pnls, wins, durs, opens, closes)


def classify(pf, exp):
    if pf != pf:  # nan
        return "UNKNOWN"
    if pf >= 1.15 and exp >= 0.05:
        return "WINNER"
    if pf <= 0.90 and exp <= -0.05:
        return "LOSER"
    return "NEUTRAL"


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100
    f = int(k)
    return xs[f] if f + 1 >= len(xs) else xs[f] + (xs[f + 1] - xs[f]) * (k - f)


def build_fidelity(win_a, win_b):
    tb, occ = {}, {}
    for r in csv.DictReader(open(ALL_CSV, encoding="utf-8", errors="replace")):
        t = ms(r["OpenedAt"])
        if t:
            tb.setdefault(r["Symbol"], []).append(t)
        o, c = ms(r["OpenedAt"]), ms(r["ClosedAt"])
        if o and c:
            occ.setdefault(r["Symbol"], []).append((o, c))
    for s in tb:
        tb[s].sort()
    for s in occ:
        occ[s].sort()
    return dict(btc_block=True, daily_change=True, traded_before=tb, occupied=occ, blackout=[])


def main():
    from engine import BacktestEngine
    eng = BacktestEngine()
    avail = set(eng.available_symbols())
    wl = json.load(open(os.path.join(HERE, "..", "data", "watchlist_cache.json")))["symbols"]
    universe = sorted(set(s for s in wl if s in avail))
    lim = int(os.environ.get("V4_UNIVERSE_LIMIT", "0"))
    if lim:
        universe = universe[:lim]
    only = os.environ.get("V4_ONLY", "")

    results = {}
    for spec in BENCH:
        name = spec["name"]
        if only and only.lower() not in name.lower():
            continue
        print(f"\n{'='*80}\n{name}  ({spec['fam']}, ground-truth {spec['cls']})\n{'='*80}", flush=True)
        prof = load_profile(name)
        real = load_real(name)
        if not real:
            results[name] = dict(error="no real trades"); continue
        wa = min(t["open"] for t in real)
        wb = min(max(t["close"] for t in real), ms("2026-08-15T00:00:00Z"))
        rw = [t for t in real if t["open"] and t["close"] and t["close"] <= wb]
        rs = real_stats(rw)
        rs["cls"] = classify(rs["pf"], rs["exp"])
        print(f"  REAL (ventana {datetime.utcfromtimestamp(wa/1000).date()}..{datetime.utcfromtimestamp(wb/1000).date()}): "
              f"n={rs['n']} net={rs['net']} PF={rs['pf']:.2f} exp={rs['exp']:.3f} WR={rs['wr']:.0f}% "
              f"dur={rs['dur']:.1f}h mdd={rs['mdd']} expo={rs['expo']} -> {rs['cls']}", flush=True)

        # símbolos de la estrategia sin histórico (para nota de cobertura)
        rsyms = set(t["symbol"] for t in rw)
        missing = sorted(rsyms - avail)
        cov = 1 - len(missing) / max(len(rsyms), 1)

        fid = build_fidelity(wa, wb)
        mc = []   # lista de dicts por (seed,perturb,cost)
        t0 = time.time()

        baseline_trades = []
        if spec["fam"] == "MaGeometry":
            print("  precompute ...", flush=True)
            pc = eng.ma_precompute(prof, universe, wa, wb, fidelity=fid)
            print(f"  precompute listo ({time.time()-t0:.0f}s), ready syms={len(pc['ready'])}", flush=True)
            _bt = eng.ma_slot_sim(pc, wa, wb, fidelity=fid, seed=0, jitter_s=0, jitter_ticks=0, tiebreak="sym_asc")
            _br = eng._capital_sim([dict(x) for x in _bt], prof, fee_per_side=0.0004, model_funding=True)
            baseline_trades = [dict(symbol=t["symbol"], open_time=t["open_time"], close_time=t["close_time"],
                                    pnl=round(t["pnl"], 4), close_reason=t["close_reason"]) for t in _br["trades"]]
            for (js, jt, tbk) in PERTURB:
                nseed = 1 if (js, jt, tbk) == (0, 0, "sym_asc") else SEEDS
                for sd in range(nseed):
                    trades = eng.ma_slot_sim(pc, wa, wb, fidelity=fid, seed=sd,
                                             jitter_s=js, jitter_ticks=jt, tiebreak=tbk)
                    for bp in COSTS_BP:
                        r = eng._capital_sim([dict(x) for x in trades], prof,
                                             fee_per_side=bp / 1e4, model_funding=False)
                        s = bt_stats(r["trades"])
                        mc.append(dict(js=js, jt=jt, tb=tbk, seed=sd, bp=bp, **s))
                    # prod-equivalente: 4bp + funding real
                    r = eng._capital_sim([dict(x) for x in trades], prof,
                                         fee_per_side=0.0004, model_funding=True)
                    s = bt_stats(r["trades"])
                    mc.append(dict(js=js, jt=jt, tb=tbk, seed=sd, bp="prod", **s))
                print(f"    perturb js={js} jt={jt} tb={tbk}: {nseed} seeds ({time.time()-t0:.0f}s)", flush=True)
        else:
            # FVG / ADN: 1 corrida fiel -> raw signals -> MC de FIFO de cupos
            print("  corrida fiel (puede tardar) ...", flush=True)
            if spec["fam"] == "FVG":
                base = eng.run_fvg_global(prof, universe, wa, wb, scan_step_ticks=3, fidelity=fid,
                                          progress_cb=lambda a, b: print(f"    fvg {a}/{b}", flush=True) if a % 3000 == 0 else None)
            else:
                base = eng.run_adn_compression(prof, universe, wa, wb, fidelity=fid)
            raw = base.get("all_signals_raw", [])
            _br = eng._capital_sim([dict(x) for x in raw], prof, fee_per_side=0.0004, model_funding=True,
                                   tiebreak="sym_asc")
            baseline_trades = [dict(symbol=t["symbol"], open_time=t["open_time"], close_time=t["close_time"],
                                    pnl=round(t["pnl"], 4), close_reason=t["close_reason"]) for t in _br["trades"]]
            print(f"  fiel listo ({time.time()-t0:.0f}s), raw signals={len(raw)}", flush=True)
            for tbk in ("sym_asc", "shuffle", "sym_desc"):
                nseed = 1 if tbk == "sym_asc" else max(40, SEEDS // 2)
                for sd in range(nseed):
                    for bp in COSTS_BP:
                        r = eng._capital_sim([dict(x) for x in raw], prof, fee_per_side=bp / 1e4,
                                             model_funding=False, tiebreak=tbk, seed=sd)
                        s = bt_stats(r["trades"])
                        mc.append(dict(js=0, jt=0, tb=tbk, seed=sd, bp=bp, **s))
                    r = eng._capital_sim([dict(x) for x in raw], prof, fee_per_side=0.0004,
                                         model_funding=True, tiebreak=tbk, seed=sd)
                    mc.append(dict(js=0, jt=0, tb=tbk, seed=sd, bp="prod", **bt_stats(r["trades"])))
            mc_note = "MC reducido: solo FIFO de cupos perturbado (deteccion fija)"
            print(f"  MC FIFO listo ({time.time()-t0:.0f}s)", flush=True)

        # ── resumen MC (usa bp='prod' para la clasificacion) ──
        prod = [m for m in mc if m["bp"] == "prod" and not (m["js"] == 0 and m["jt"] == 0 and m["tb"] == "sym_asc")]
        if not prod:
            prod = [m for m in mc if m["bp"] == "prod"]
        pfs = [m["pf"] for m in prod if m["pf"] == m["pf"] and m["pf"] != float("inf")]
        nets = [m["net"] for m in prod]
        exps = [m["exp"] for m in prod]
        med_pf = st.median(pfs) if pfs else float("nan")
        med_exp = st.median(exps) if exps else 0
        replay_cls = classify(med_pf, med_exp)
        # % seeds del lado correcto
        want_win = rs["cls"] == "WINNER"
        correct = sum(1 for m in prod if (m["pf"] > 1) == want_win) if rs["cls"] in ("WINNER", "LOSER") else None
        pct_correct = (100 * correct / len(prod)) if correct is not None and prod else None
        # sensibilidad jitter: clase por nivel de jitter_s
        jit_cls = {}
        for js in (0, 1, 2, 5, 10):
            g = [m["pf"] for m in mc if m["bp"] == "prod" and m["js"] == js and m["jt"] == 0 and m["tb"] == "shuffle" and m["pf"] == m["pf"] and m["pf"] != float("inf")]
            if g:
                jit_cls[js] = ("W" if st.median(g) > 1 else "L", round(st.median(g), 2), round(pct(g, 5), 2), round(pct(g, 95), 2))
        # costos
        cost_cls = {}
        for bp in COSTS_BP:
            g = [m["net"] for m in mc if m["bp"] == bp]
            if g:
                cost_cls[bp] = (round(st.median(g), 1), "pos" if st.median(g) > 0 else "neg")

        summ = dict(
            real=rs, window=[wa, wb], coverage=round(cov, 3), missing_syms=missing[:20],
            replay_median_pf=round(med_pf, 3), replay_median_exp=round(med_exp, 3),
            replay_cls=replay_cls, pct_seeds_correct=pct_correct,
            pf_dist={p: round(pct(pfs, p), 3) for p in (5, 25, 50, 75, 95)} if pfs else {},
            net_dist={p: round(pct(nets, p), 1) for p in (5, 25, 50, 75, 95)} if nets else {},
            exp_dist={p: round(pct(exps, p), 3) for p in (5, 25, 50, 75, 95)} if exps else {},
            jitter_by_level=jit_cls, cost_by_bp=cost_cls,
            n_mc=len(prod), fam=spec["fam"], gt_cls=spec["cls"],
            baseline_trades=baseline_trades,
            real_trades=[dict(open=t["open"], close=t["close"], pnl=t["pnl"], reason=t["reason"]) for t in rw],
        )
        results[name] = summ
        print(f"  REPLAY median PF={med_pf:.2f} exp={med_exp:.3f} -> {replay_cls} | "
              f"seeds correctos={pct_correct} | PF P5={summ['pf_dist'].get(5)} P95={summ['pf_dist'].get(95)}", flush=True)
        json.dump(results, open(OUT, "w"), indent=1, default=str)

    # ── GATES ──
    print("\n" + "=" * 80 + "\nGATES V4 (pre-registrados)\n" + "=" * 80)
    ok = [n for n in results if "real" in results[n]]
    real_pf = {n: results[n]["real"]["pf"] for n in ok}
    rep_pf = {n: results[n]["replay_median_pf"] for n in ok}

    # A sign
    signA = []
    for n in ok:
        rn, bn = results[n]["real"]["net"], results[n]["net_dist"].get(50, 0)
        same = (rn < 0) == (bn < 0)
        fp = (results[n]["real"]["cls"] == "LOSER" and bn > 0)
        signA.append((n, same, fp))
    a_pass = sum(1 for _, s, _ in signA if s)
    a_fp = any(fp for _, _, fp in signA)
    A = "FAILED" if (a_pass <= 5 or a_fp) else ("PASS" if a_pass == len(ok) else "LIMITED")

    # B ranking (spearman)
    import statistics
    rr = sorted(ok, key=lambda n: real_pf[n]); rrank = {n: i for i, n in enumerate(rr)}
    br = sorted(ok, key=lambda n: rep_pf[n]); brank = {n: i for i, n in enumerate(br)}
    d2 = sum((rrank[n] - brank[n]) ** 2 for n in ok); nn = len(ok)
    rho = (1 - 6 * d2 / (nn * (nn * nn - 1))) if nn >= 3 else float("nan")
    B = "UNKNOWN" if rho != rho else ("PASS" if rho >= 0.85 else ("LIMITED" if rho >= 0.60 else "FAILED"))

    # C MC stability
    cfail = []
    for n in ok:
        r = results[n]
        gt = r["real"]["cls"]
        if gt == "WINNER":
            if (r["pct_seeds_correct"] or 0) < 90 or r["pf_dist"].get(5, 0) <= 1.0:
                cfail.append((n, "winner P5<=1 or <90%"))
        elif gt == "LOSER":
            if (r["pct_seeds_correct"] or 0) < 90 or r["pf_dist"].get(95, 9) >= 1.0:
                cfail.append((n, "loser P95>=1 or <90%"))
    C = "FAILED" if any((results[n]["pct_seeds_correct"] or 0) < 75 for n in ok if results[n]["real"]["cls"] in ("WINNER", "LOSER")) or cfail else \
        ("PASS" if all((results[n]["pct_seeds_correct"] or 100) >= 90 for n in ok if results[n]["real"]["cls"] in ("WINNER", "LOSER")) else "LIMITED")

    # D false positive (REAL loser -> replay PF>=1.10)
    D_fp = [n for n in ok if results[n]["real"]["cls"] == "LOSER" and results[n]["replay_median_pf"] >= 1.10]
    D_soft = [n for n in ok if results[n]["real"]["cls"] == "LOSER" and 0.90 < results[n]["replay_median_pf"] < 1.10]
    D = "FAILED" if D_fp else ("PASS" if not D_soft else "LIMITED")

    # E false negative (REAL winner -> replay PF<=0.90)
    E_fn = [n for n in ok if results[n]["real"]["cls"] == "WINNER" and results[n]["replay_median_pf"] <= 0.90]
    E_soft = [n for n in ok if results[n]["real"]["cls"] == "WINNER" and 0.90 < results[n]["replay_median_pf"] < 1.15]
    E = "FAILED" if E_fn else ("PASS" if not E_soft else "LIMITED")

    # F jitter sensitivity
    ffail = []
    for n in ok:
        jl = results[n]["jitter_by_level"]
        classes = set(v[0] for v in jl.values())
        want = "W" if results[n]["real"]["cls"] == "WINNER" else ("L" if results[n]["real"]["cls"] == "LOSER" else None)
        if want and len(classes) > 1:
            ffail.append((n, "clase cambia con jitter"))
    F = "FAILED" if ffail else "PASS"

    # G costs (REAL loser net-positive at >=2bp in replay?  |  >=2 winners net-neg at 2bp)
    g_fp = [n for n in ok if results[n]["real"]["cls"] == "LOSER" and any(results[n]["cost_by_bp"].get(bp, (0, ""))[1] == "pos" for bp in (2, 5))]
    g_fn = [n for n in ok if results[n]["real"]["cls"] == "WINNER" and results[n]["cost_by_bp"].get(2, (0, ""))[1] == "neg"]
    G = "FAILED" if (g_fp or len(g_fn) >= 2) else ("PASS" if not g_fn else "LIMITED")

    verdict_gates = dict(A=A, B=round(rho, 2), Bv=B, C=C, D=D, E=E, F=F, G=G)
    print(json.dumps(verdict_gates, indent=1))
    print(f"  A sign: {a_pass}/{len(ok)} correct, hard-FP={a_fp} -> {A}")
    print(f"  B ranking spearman rho={rho:.2f} -> {B}")
    print(f"  C MC stability -> {C}  fails={cfail}")
    print(f"  D FALSE POSITIVE hard={D_fp} soft={D_soft} -> {D}")
    print(f"  E FALSE NEGATIVE hard={E_fn} soft={E_soft} -> {E}")
    print(f"  F jitter -> {F}  fails={ffail}")
    print(f"  G costs FP={g_fp} FN@2bp={g_fn} -> {G}")

    gates = [A, B, C, D, E, F, G]  # H (OOS) se hace en el reporte con más detalle
    nf = gates.count("FAILED")
    if D == "FAILED" or A == "FAILED" or C == "FAILED" or E == "FAILED" or nf >= 3:
        V = "FAILED"
    elif A == "PASS" and C == "PASS" and D == "PASS" and E == "PASS" and all(g in ("PASS", "LIMITED") for g in (B, F, G)) and gates.count("PASS") >= 5:
        V = "PASS"
    else:
        V = "LIMITED"
    print(f"\n{'='*80}\nGATE V4 (mecánico, sin H/OOS) = {V}\n{'='*80}")
    results["_gates"] = dict(A=A, B=B, rho=round(rho, 3), C=C, D=D, E=E, F=F, G=G, verdict=V,
                             A_detail=[(n, s, f) for n, s, f in signA], D_fp=D_fp, E_fn=E_fn)
    json.dump(results, open(OUT, "w"), indent=1, default=str)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
