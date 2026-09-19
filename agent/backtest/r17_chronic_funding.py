"""
ROUND 17 — CHRONIC FUNDING YIELD ATTACK.

R16 aisló la causa de fallo: el turnover del ranking (rota cada ~36h) genera
fees que superan al funding capturado 5-20x. R17 ataca exactamente eso:
¿hay símbolos con sesgo de funding ESTRUCTURAL (semanas/meses), suficiente
para sostener una posición con rotación mínima?

Diseño (day-level, no 15m -- el holding es de semanas, no horas):
  - Funding y precios agregados a DIARIO (causal).
  - "Chronic score" por símbolo y ventana W (30/60d primarias; 7/14/90/180d
    como diagnóstico de dónde vive la persistencia, no para tradear directo):
        score_W(t) = mean_W(t) / std_W(t) * frac_samesign_W(t)
    (magnitud + persistencia + estabilidad, todo causal, [t-W, t-1]).
  - HISTÉRESIS para minimizar turnover (exactamente lo que R16 no tenía):
      ENTER si |score| >= ENTER_THR ; mantener hasta que:
        (a) el signo de mean_W se invierte, o
        (b) |score| cae debajo de KEEP_THR (< ENTER_THR), o
        (c) se alcanza el holding máximo predeclarado.
      NO se cierra una posición solo porque otro símbolo la superó en el
      ranking -- eso es precisamente lo que generaba el turnover de R16.
  - Selección A (threshold absoluto, sin cap de N), B (top-N por magnitud
    cruda, IGNORA persistencia -- control), C (top-N por chronic score,
    persistencia+magnitud -- la hipótesis principal).
  - Estructura B (funding crónicamente negativo -> short spot) sigue NO
    OPERABLE (sin borrow-rate) -- solo diagnóstico.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r16_funding_carry import universe, load_symbol, RT_BP_PAIR
from datetime import datetime, timezone, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
LOOKBACKS_DIAG = [7, 14, 30, 60, 90, 180]
LOOKBACKS_MAIN = [30, 60]
MAXHOLD_OPTIONS = [7, 14, 30, 60, 90]
N_OPTIONS = [1, 2, 3, 5, 10]
ENTER_THR = 1.0; KEEP_THR = 0.5      # histeresis, predeclarado
CAPITALS = [150, 300, 450]
LEV_PERP = 3.0
rng = np.random.default_rng(20260920)


def daily_build(d):
    """agrega perp/spot/funding a DIARIO (UTC), causal, sin lookahead."""
    pt = d["pt"]; day = (pt // 86400000).astype(np.int64)
    order = np.argsort(pt)
    last_idx = {}
    for pos in order:
        last_idx[int(day[pos])] = pos   # ultimo bar del dia (pt ordenado creciente)
    days = np.array(sorted(last_idx), np.int64)
    perp_c = np.array([d["pc"][last_idx[dd]] for dd in days])
    spot_c = np.array([d["spot"][last_idx[dd]] for dd in days])
    # funding diario = suma de settlements de ese dia calendario
    fday = (d["ft"] // 86400000).astype(np.int64)
    fmap = collections.defaultdict(float)
    for fd, fr in zip(fday, d["fr"]):
        fmap[int(fd)] += fr
    fund_daily = np.array([fmap.get(int(dd), 0.0) for dd in days])
    has_fund = np.array([int(dd) in fmap for dd in days])
    return dict(days=days, perp=perp_c, spot=spot_c, fund=fund_daily, has_fund=has_fund)


def rolling_stats(fund, has_fund, W):
    """mean/std/frac_samesign causales sobre [t-W, t-1] dias CON funding real."""
    n = len(fund)
    mean_ = np.full(n, np.nan); std_ = np.full(n, np.nan); frac_ = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - W)
        seg = fund[lo:i][has_fund[lo:i]]
        if len(seg) >= max(5, W * 0.5):
            m = seg.mean(); s = seg.std()
            mean_[i] = m; std_[i] = s
            frac_[i] = (seg > 0).mean() if m > 0 else (seg < 0).mean()
    return mean_, std_, frac_


def main():
    print("=== ROUND 17 — CHRONIC FUNDING YIELD ATTACK ===")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    RAW = {}; DAY = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        RAW[s] = d; DAY[s] = daily_build(d)
    con.close()
    print(f"universo: {len(DAY)} símbolos")
    span0 = min(int(v["days"][0]) for v in DAY.values()); span1 = max(int(v["days"][-1]) for v in DAY.values())
    def ds(x): return (date(1970, 1, 1) + timedelta(days=int(x))).isoformat()
    print(f"ventana diaria: {ds(span0)} .. {ds(span1)}  ({span1-span0} días)")

    # ---------- FASE 1: DIAGNÓSTICO ESTRUCTURAL (full-sample, todas las ventanas) ----------
    print("\n" + "#" * 70 + "\n# FASE 1-2 — DIAGNÓSTICO 'CHRONIC FUNDING' (full-sample, por ventana)\n" + "#" * 70)
    diag = {}
    for W in LOOKBACKS_DIAG:
        rows = []
        for s, dd in DAY.items():
            fu_full = dd["fund"]; hf = dd["has_fund"]
            if hf.sum() < W:
                continue
            # ventana TRAILING real de W días (rolling, no todo el sample): usa la misma
            # función causal que la estrategia, y caracteriza la distribución de esos
            # promedios rolling a lo largo del tiempo (no un único número full-sample).
            m_roll, sd_roll, fr_roll = rolling_stats(fu_full, hf, W)
            valid = np.isfinite(m_roll)
            if valid.sum() < 5:
                continue
            m_of_means = float(np.nanmean(m_roll[valid]))
            sd_of_means = float(np.nanstd(m_roll[valid])) or 1e-9
            pospct = float((m_roll[valid] > 0).mean())
            fu = fu_full[hf]
            ac1 = np.corrcoef(fu[:-1], fu[1:])[0, 1] if len(fu) > 10 else np.nan
            stab = float((np.sign(m_roll[valid]) == np.sign(m_of_means)).mean())
            tstat = m_of_means / sd_of_means * math.sqrt(valid.sum())
            rows.append((s, m_of_means, sd_of_means, pospct, ac1, stab, tstat, int(valid.sum())))
        rows.sort(key=lambda r: abs(r[6]), reverse=True)
        diag[W] = rows
        print(f"\n  ventana {W}d — top 5 por |t-stat| (símbolo, media/día_bp, %pos, autocorr_lag1, estabilidad_signo_30d, t-stat, n):")
        for r in rows[:5]:
            print(f"    {r[0]:12s} mean={r[1]*1e4:+.2f}bp  %pos={r[3]:.2f}  ac1={r[4]:.2f}  stab30d={r[5]:.2f}  t={r[6]:.1f}  n={r[7]}")

    chronic_syms = sorted(set(r[0] for W in (30, 60) for r in diag[W][:8]))
    print(f"\n  Símbolos 'crónicos' candidatos (top-8 por |t-stat| en 30d o 60d, unión): {chronic_syms}")

    # ---------- FASE 3-6: ESTRATEGIA CAUSAL (histéresis, sin lookahead) ----------
    ref = max(DAY, key=lambda s: len(DAY[s]["days"]))
    master_days = DAY[ref]["days"]
    idx_of = {s: {int(d_): i for i, d_ in enumerate(DAY[s]["days"])} for s in DAY}

    def build_rolling(W):
        R = {}
        for s, dd in DAY.items():
            m, sd, fr_ = rolling_stats(dd["fund"], dd["has_fund"], W)
            score = np.where((sd > 0), m / np.where(sd > 0, sd, 1) * fr_, 0.0)
            R[s] = dict(mean=m, std=sd, frac=fr_, score=score)
        return R

    def simulate(W, rank_mode, n_cap, maxhold, capital, placebo=None, day_filter=None, stress_fund=1.0, stress_fee=1.0, stress_slip=1.0):
        Rs = ROLLING[W]
        book = {}   # sym -> (entry_day_idx_in_master, notional, entry_perp_i, entry_spot_i)
        trades = []
        rt_bp = (2 * (10.0 * stress_fee + 4.0 * stress_slip) + 2 * (5.0 * stress_fee + 4.0 * stress_slip))
        warm = max(W, 30) + 1
        for t in range(warm, len(master_days)):
            tday = int(master_days[t])
            if day_filter is not None and not day_filter(tday):
                continue
            # 1) evaluar salidas del book
            for s in list(book):
                j = idx_of[s].get(int(master_days[t - 1]))   # dato de ayer (causal, ya liquidado el dia)
                if j is None:
                    continue
                m = Rs[s]["mean"][j]; sc = Rs[s]["score"][j]
                entry_day, notion, entry_i = book[s]
                held = t - entry_day
                exit_ = False
                if np.isfinite(m) and m < 0:      # sign flip
                    exit_ = True
                elif np.isfinite(sc) and abs(sc) < KEEP_THR:
                    exit_ = True
                elif held >= maxhold:
                    exit_ = True
                if exit_:
                    ii0 = idx_of[s].get(int(master_days[entry_i]))
                    ii1 = idx_of[s].get(tday)
                    if ii0 is not None and ii1 is not None:
                        d = DAY[s]
                        spot0, spot1 = d["spot"][ii0], d["spot"][ii1]
                        perp0, perp1 = d["perp"][ii0], d["perp"][ii1]
                        fu = d["fund"][ii0:ii1][d["has_fund"][ii0:ii1]]
                        fund_pnl = notion * float(fu.sum()) * stress_fund
                        price_pnl = notion * (math.log(spot1 / spot0) - math.log(perp1 / perp0)) if (spot0 > 0 and spot1 > 0 and perp0 > 0 and perp1 > 0) else 0.0
                        fees = notion * rt_bp / 1e4
                        trades.append((int(master_days[entry_i]), tday, s, notion, fund_pnl, price_pnl, fees))
                    del book[s]
            # 2) evaluar entradas
            if len(book) >= n_cap:
                continue
            cand = {}
            for s in DAY:
                if s in book:
                    continue
                j = idx_of[s].get(int(master_days[t - 1]))
                if j is None:
                    continue
                m = Rs[s]["mean"][j]; sc = Rs[s]["score"][j]
                if not (np.isfinite(m) and m > 0 and np.isfinite(sc)):
                    continue
                if rank_mode == "abs_threshold" and abs(sc) < ENTER_THR:
                    continue
                if rank_mode in ("topN_magnitude", "topN_score") and abs(sc) < ENTER_THR:
                    continue
                cand[s] = (m, sc)
            if not cand:
                continue
            if placebo == "random_selection":
                keys = list(cand); rng.shuffle(keys); chosen = keys[:max(0, n_cap - len(book))]
            elif placebo == "matched_vol":
                volmap = {}
                for s in cand:
                    ii = idx_of[s].get(tday)
                    if ii is None or ii < 30:
                        continue
                    r = np.diff(np.log(DAY[s]["perp"][max(0, ii - 30):ii + 1]))
                    volmap[s] = np.std(r) if len(r) > 5 else np.nan
                volmap = {s: v for s, v in volmap.items() if np.isfinite(v)}
                chosen = sorted(volmap, key=lambda s: volmap[s], reverse=True)[:max(0, n_cap - len(book))]
            elif rank_mode == "topN_magnitude":
                chosen = sorted(cand, key=lambda s: cand[s][0], reverse=True)[:max(0, n_cap - len(book))]
            else:   # topN_score, abs_threshold
                chosen = sorted(cand, key=lambda s: abs(cand[s][1]), reverse=True)[:max(0, n_cap - len(book))]
            notional_each = (capital / (1 + 1 / LEV_PERP)) / max(1, n_cap)
            for s in chosen:
                book[s] = (t, notional_each, t)
        # cerrar lo que quede
        for s, (entry_i, notion, _) in book.items():
            ii0 = idx_of[s].get(int(master_days[entry_i])); ii1 = len(DAY[s]["days"]) - 1
            if ii0 is None:
                continue
            d = DAY[s]
            spot0, spot1 = d["spot"][ii0], d["spot"][ii1]; perp0, perp1 = d["perp"][ii0], d["perp"][ii1]
            fu = d["fund"][ii0:][d["has_fund"][ii0:]]
            fund_pnl = notion * float(fu.sum()) * stress_fund
            price_pnl = notion * (math.log(spot1 / spot0) - math.log(perp1 / perp0)) if (spot0 > 0 and spot1 > 0 and perp0 > 0 and perp1 > 0) else 0.0
            fees = notion * rt_bp / 1e4
            trades.append((int(master_days[entry_i]), int(d["days"][ii1]), s, notion, fund_pnl, price_pnl, fees))
        return trades

    def summarize(trades, label):
        if len(trades) < 3:
            print(f"  {label}: trades insuficientes ({len(trades)})"); return None
        gross_fund = sum(t[4] for t in trades); gross_price = sum(t[5] for t in trades); fees = sum(t[6] for t in trades)
        net = gross_fund + gross_price - fees
        span_days = (max(t[1] for t in trades) - min(t[0] for t in trades)) or 1
        net_mo = net / (span_days / 30); fund_mo = gross_fund / (span_days / 30); fees_mo = fees / (span_days / 30)
        holds = [t[1] - t[0] for t in trades]
        bym = collections.defaultdict(float)
        for t in trades:
            mk = (date(1970, 1, 1) + timedelta(days=t[0])).strftime("%Y-%m")
            bym[mk] += t[4] + t[5] - t[6]
        months = np.array(sorted(bym.values())) if bym else np.array([0.0])
        eq = np.cumsum([t[4] + t[5] - t[6] for t in sorted(trades, key=lambda x: x[1])])
        dd_ = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
        syms_used = sorted(set(t[2] for t in trades))
        sym_pnl = collections.defaultdict(float)
        for t in trades:
            sym_pnl[t[2]] += t[4] + t[5] - t[6]
        top1_share = (max(sym_pnl.values()) / sum(v for v in sym_pnl.values() if v > 0)) if any(v > 0 for v in sym_pnl.values()) else float('nan')
        flag = "  <<< SUPERA 150" if net_mo >= 150 else ("  (PARK 75-149)" if 75 <= net_mo < 150 else "")
        print(f"  {label}: trades={len(trades)} avg_hold={np.mean(holds):.0f}d  NET/mes=${net_mo:.1f}  (fund=${fund_mo:.1f} fees=${fees_mo:.1f})  "
              f"maxDD=${dd_:.1f} worst=${months.min():.1f} best=${months.max():.1f} meses+/-={int((months>0).sum())}/{int((months<0).sum())} "
              f"nSym={len(syms_used)} top1_share={top1_share:.2f}{flag}")
        return dict(net_mo=net_mo, fund_mo=fund_mo, fees_mo=fees_mo, dd=dd_, worst=float(months.min()), best=float(months.max()),
                    n_trades=len(trades), avg_hold=float(np.mean(holds)), n_sym=len(syms_used), top1_share=top1_share,
                    pos_months=int((months > 0).sum()), neg_months=int((months < 0).sum()))

    global ROLLING
    ROLLING = {W: build_rolling(W) for W in LOOKBACKS_MAIN}

    print("\n" + "#" * 70 + "\n# ESTRATEGIA CAUSAL — screening (cap $450)\n" + "#" * 70)
    results = {}
    print("\n-- Selección A/B/C x ventana (N cap=5, maxhold=60d) --")
    for W in LOOKBACKS_MAIN:
        for mode in ("abs_threshold", "topN_magnitude", "topN_score"):
            tr = simulate(W, mode, 5, 60, 450)
            r = summarize(tr, f"W={W}d mode={mode}")
            results[f"W{W}_{mode}"] = r

    print("\n-- Sensibilidad de N (W=30d, topN_score, maxhold=60d) --")
    for N in N_OPTIONS:
        tr = simulate(30, "topN_score", N, 60, 450)
        r = summarize(tr, f"N={N}")
        results[f"N{N}"] = r

    print("\n-- Sensibilidad de max-holding (W=30d, topN_score, N=5) --")
    for mh in MAXHOLD_OPTIONS:
        tr = simulate(30, "topN_score", 5, mh, 450)
        r = summarize(tr, f"maxhold={mh}d")
        results[f"maxhold{mh}"] = r

    print("\n-- Capital / leverage (W=30d, topN_score, N=3, maxhold=60d) --")
    for cap in CAPITALS:
        tr = simulate(30, "topN_score", 3, 60, cap)
        r = summarize(tr, f"cap=${cap}")
        results[f"cap{cap}"] = r

    best_key = max((k for k in results if results[k]), key=lambda k: results[k]["net_mo"])
    print(f"\n>>> MEJOR configuración: {best_key} -> ${results[best_key]['net_mo']:.1f}/mes")
    W_B, MODE_B, N_B, MH_B = 30, "topN_score", 5, 60   # config primaria para el resto de los tests

    print("\n" + "#" * 70 + f"\n# ROBUSTEZ TEMPORAL (config primaria W={W_B} {MODE_B} N={N_B} mh={MH_B})\n" + "#" * 70)
    all_days_list = sorted(set(int(x) for x in master_days))
    tcut, vcut = all_days_list[int(len(all_days_list) * 0.5)], all_days_list[int(len(all_days_list) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    q3_start = (date(2026, 7, 1) - date(1970, 1, 1)).days
    tr_full = simulate(W_B, MODE_B, N_B, MH_B, 450)
    summarize(tr_full, "FULL dataset")
    tr_train = [t for t in tr_full if seg(t[0]) == "train"]
    summarize(tr_train, "TRAIN (referencia)")
    tr_val = [t for t in tr_full if seg(t[0]) == "val"]
    summarize(tr_val, "VAL (referencia)")
    tr_oos = [t for t in tr_full if seg(t[0]) == "oos"]
    summarize(tr_oos, "OOS puro (post-descubrimiento, últimos 25%)")
    tr_exq3 = [t for t in tr_full if t[0] < q3_start]
    summarize(tr_exq3, "OOS 1: excluye 2026Q3 explícitamente")
    tr_q3 = [t for t in tr_full if t[0] >= q3_start]
    summarize(tr_q3, "OOS 2: SOLO 2026Q3 (período de funding/dispersión extrema)")

    print("\n" + "#" * 70 + "\n# PLACEBOS / CONTROLES (config primaria)\n" + "#" * 70)
    tr_rand = simulate(W_B, MODE_B, N_B, MH_B, 450, placebo="random_selection")
    summarize(tr_rand, "PLACEBO random_selection")
    tr_vol = simulate(W_B, MODE_B, N_B, MH_B, 450, placebo="matched_vol")
    summarize(tr_vol, "CONTROL matched_vol")
    tr_magonly = simulate(W_B, "topN_magnitude", N_B, MH_B, 450)
    summarize(tr_magonly, "CONTROL magnitud-sola (sin persistencia, = 'B' del brief)")

    print("\n" + "#" * 70 + "\n# STRESS TEST del mejor candidato (config primaria)\n" + "#" * 70)
    for sf in (1.0, 0.75, 0.5, 0.25):
        tr = simulate(W_B, MODE_B, N_B, MH_B, 450, stress_fund=sf)
        summarize(tr, f"stress funding x{sf}")
    for ff in (1.0, 1.5, 2.0):
        tr = simulate(W_B, MODE_B, N_B, MH_B, 450, stress_fee=ff)
        summarize(tr, f"stress fees x{ff}")
    for sl in (1.0, 2.0, 3.0):
        tr = simulate(W_B, MODE_B, N_B, MH_B, 450, stress_slip=sl)
        summarize(tr, f"stress slippage x{sl}")

    print("\n" + "#" * 70 + "\n# ESTRUCTURA B (funding crónicamente negativo) — NO OPERABLE\n" + "#" * 70)
    print("  Requeriría short/borrow de spot. Sin datos de borrow-rate -> NO se reporta como estrategia.")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_symbols": len(DAY),
           "window": [ds(span0), ds(span1)], "results": results, "best_key": best_key,
           "chronic_symbols_candidates": chronic_syms}
    json.dump(out, open(os.path.join(ROOT, "scratch_r17_chronic_funding.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r17_chronic_funding.json")


if __name__ == "__main__":
    main()
