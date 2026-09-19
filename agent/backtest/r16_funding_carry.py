"""
ROUND 16 — FUNDING-RATE CARRY (cash-and-carry delta-neutral), NO direccional.

MECANISMO: funding positivo -> longs pagan a shorts. Estructura OPERABLE:
  LONG SPOT + SHORT PERP  (financiamos el spot con capital propio -- no hace
  falta pedir prestado nada). Capturamos el funding que cobra el short-perp,
  el spot cubre la exposicion direccional.
Estructura NO OPERABLE (funding negativo, SHORT SPOT + LONG PERP): requeriria
  pedir prestado el spot para venderlo en corto. No tenemos datos de borrow-rate
  ni infraestructura de margen cruzado -> se calcula matematicamente para
  diagnostico pero se marca explicitamente NO OPERABLE, nunca como estrategia.

UNIVERSO: interseccion real funding_hist (63) x spot_klines (240) x klines_clean
perp (450) = 43 simbolos. Esto NO es una reduccion arbitraria -- es el universo
donde el mecanismo (comparar spot vs perp) es fisicamente calculable con los
datos que tenemos. Ventana: 2025-12-01 .. 2026-08-17 (8.5 meses, limitado por
spot_klines, que no se extendio hacia atras como el perp/OI/funding de R11).

Todo predeclarado: umbrales de trailing funding, N de concentracion,
frecuencias de rebalanceo, esquemas de ponderacion, costos.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from datetime import datetime, timezone, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")

# costos predeclarados (bp por lado, no elegidos para salvar el resultado)
SPOT_FEE = 10.0; SPOT_SLIP = 4.0     # spot taker ~10bp tipico + slippage
PERP_FEE = 5.0; PERP_SLIP = 4.0      # perp taker ~5bp + slippage
# round-trip completo (abrir+cerrar) de UN par (spot+perp) si se rota 100%:
RT_BP_PAIR = 2 * (SPOT_FEE + SPOT_SLIP) + 2 * (PERP_FEE + PERP_SLIP)   # = 46bp

REBAL_OPTIONS = {"8h": 1, "24h": 3, "72h": 9}   # en # de settlements (8h cada uno tipicamente)
TRAIL_WINDOWS = {"8h": 1, "24h": 3, "72h": 9, "7d": 21}
N_OPTIONS = [1, 2, 3, 5, 10]
CAPITALS = [150, 300, 450]
LEV_PERP = 3.0   # apalancamiento del lado perp, contabilizado explicitamente (conservador)
rng = np.random.default_rng(20260919)


def universe():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    f = set(s for (s,) in con.execute("SELECT DISTINCT symbol FROM funding_hist"))
    sp = set(s for (s,) in con.execute("SELECT DISTINCT symbol FROM spot_klines"))
    pe = set(s for (s,) in con.execute("SELECT DISTINCT symbol FROM klines_clean WHERE interval='15m'"))
    con.close()
    return sorted(f & sp & pe)


def load_symbol(con, s):
    perp = con.execute("SELECT open_time,close FROM klines_clean WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
    spot = con.execute("SELECT open_time,close FROM spot_klines WHERE symbol=? AND interval='15m' ORDER BY open_time", (s,)).fetchall()
    fund = con.execute("SELECT calc_time,funding_rate FROM funding_hist WHERE symbol=? ORDER BY calc_time", (s,)).fetchall()
    if len(perp) < 500 or len(spot) < 500 or len(fund) < 20:
        return None
    pt = np.array([r[0] for r in perp], np.int64); pc = np.array([r[1] for r in perp], float)
    st = np.array([r[0] for r in spot], np.int64); sc = np.array([r[1] for r in spot], float)
    ft = np.array([r[0] for r in fund], np.int64); fr = np.array([r[1] for r in fund], float)
    # alinear spot al calendario perp
    spos = {int(t): i for i, t in enumerate(st)}
    spot_aligned = np.full(len(pt), np.nan)
    for i, t in enumerate(pt):
        j = spos.get(int(t))
        if j is not None:
            spot_aligned[i] = sc[j]
    return dict(pt=pt, pc=pc, spot=spot_aligned, ft=ft, fr=fr, ppos={int(t): i for i, t in enumerate(pt)})


def trailing_funding(ft, fr, k):
    """media causal de los ultimos k settlements ANTERIORES a cada indice i (excluye el propio)."""
    n = len(fr)
    out = np.full(n, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(fr)])
    for i in range(k, n):
        out[i] = (cs[i] - cs[i - k]) / k
    return out


def main():
    print("=== ROUND 16 — FUNDING-RATE CARRY (delta-neutral spot vs perp) ===")
    syms = universe()
    print(f"universo REAL (funding x spot x perp): {len(syms)} símbolos -> {syms}")
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    D = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is not None:
            D[s] = d
    con.close()
    print(f"cargados: {len(D)}")

    span0 = min(int(d["pt"][0]) for d in D.values()); span1 = max(int(d["pt"][-1]) for d in D.values())
    def dd(ms): return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    print(f"ventana: {dd(span0)} .. {dd(span1)}")

    # ---------- FASE 4: PERSISTENCIA DEL FUNDING ----------
    print("\n" + "#" * 70 + "\n# PERSISTENCIA / ESTABILIDAD DEL FUNDING (todos los símbolos, todos los settlements)\n" + "#" * 70)
    all_signs = []; runlens = []; flips = 0; total_pairs = 0
    extreme_episode_lens = []
    for s, d in D.items():
        fr = d["fr"]
        signs = np.sign(fr)
        for i in range(1, len(signs)):
            total_pairs += 1
            if signs[i] != signs[i - 1] and signs[i] != 0 and signs[i - 1] != 0:
                flips += 1
        # duracion de rachas del mismo signo
        cur_sign = None; cur_len = 0
        for x in signs:
            if x == 0:
                continue
            if x == cur_sign:
                cur_len += 1
            else:
                if cur_sign is not None:
                    runlens.append(cur_len)
                cur_sign = x; cur_len = 1
        if cur_sign is not None:
            runlens.append(cur_len)
        # episodios "extremos": |funding| > p90 causal simple (percentil global del simbolo, para diagnostico)
        thr = np.nanpercentile(np.abs(fr), 90)
        ext = np.abs(fr) >= thr
        cur = 0
        for x in ext:
            if x:
                cur += 1
            else:
                if cur > 0:
                    extreme_episode_lens.append(cur)
                cur = 0
        if cur > 0:
            extreme_episode_lens.append(cur)
    print(f"  probabilidad de cambio de signo settlement-a-settlement: {flips/total_pairs:.2%}  (n={total_pairs})")
    print(f"  duración media de racha de mismo signo: {np.mean(runlens):.1f} settlements (~{np.mean(runlens)*8:.0f}h)  mediana={np.median(runlens):.0f}")
    print(f"  duración media de episodio 'extremo' (>p90 |funding| del propio símbolo): {np.mean(extreme_episode_lens):.1f} settlements (~{np.mean(extreme_episode_lens)*8:.0f}h)")
    print("  -> INTERPRETACIÓN: funding NO es ruido puro (rachas > 1 settlement en promedio),")
    print("     pero tampoco es infinitamente persistente -> es 'transitorio pero potencialmente capturable' si el rebalanceo es lo bastante frecuente.")

    # correlacion trailing(pasado) vs funding del PROXIMO settlement, por ventana de trailing
    print("\n  Correlación trailing_funding(pasado) vs funding del PRÓXIMO settlement (predictividad de persistencia):")
    for lbl, k in TRAIL_WINDOWS.items():
        xs = []; ys = []
        for s, d in D.items():
            tr = trailing_funding(d["ft"], d["fr"], k)
            for i in range(k, len(d["fr"]) - 1):
                if np.isfinite(tr[i]):
                    xs.append(tr[i]); ys.append(d["fr"][i])
        xs = np.array(xs); ys = np.array(ys)
        cc = np.corrcoef(xs, ys)[0, 1] if len(xs) > 10 else np.nan
        print(f"    trailing {lbl}: corr={cc:.3f}  n={len(xs)}")

    # ---------- construir grid de rebalanceo por simbolo alineado, y funciones de sim ----------
    # settlement index -> perp index (para precios de entrada/salida) via ft->pt map cercano
    def nearest_perp_idx(d, t_ms):
        j = d["ppos"].get(int(t_ms))
        if j is not None:
            return j
        # buscar el bar de perp mas cercano (<=)
        k = np.searchsorted(d["pt"], t_ms, side="right") - 1
        return k if 0 <= k < len(d["pt"]) else None

    def run_strategy(rebal_lbl, trail_lbl, n_legs, weight_scheme, leverage, capital, seg_filter=None,
                     placebo=None, exclude_q3=False, only_extreme=None):
        """Simula el book de carry positivo (LONG SPOT + SHORT PERP) rebalanceando cada
        REBAL_OPTIONS[rebal_lbl] settlements, rankeando por trailing_funding[trail_lbl]."""
        rebal_k = REBAL_OPTIONS[rebal_lbl]; trail_k = TRAIL_WINDOWS[trail_lbl]
        # precomputar trailing funding por simbolo
        TR = {s: trailing_funding(d["ft"], d["fr"], trail_k) for s, d in D.items()}
        # grid maestro de settlements = union de calc_time, tomado de un simbolo con buena cobertura (BTCUSDT)
        ref = "BTCUSDT" if "BTCUSDT" in D else max(D, key=lambda s: len(D[s]["ft"]))
        ft_ref = D[ref]["ft"]
        rebal_points = list(range(trail_k + 1, len(ft_ref) - 1, rebal_k))
        trades = []   # (entry_ms, exit_ms, sym, notional, funding_pnl, price_pnl_spot, price_pnl_perp, fee_cost)
        book = {}     # sym -> (entry_ms, entry_i_settlement_idx_per_sym, notional)
        for ridx in rebal_points:
            tms = int(ft_ref[ridx])
            day = datetime.utcfromtimestamp(tms / 1000).date()
            if seg_filter is not None and seg_filter(day) is False:
                continue
            if exclude_q3 and date(2026, 7, 1) <= day <= date(2026, 8, 17):
                continue
            # candidatos: simbolos con trailing funding positivo en este ts (y con dato)
            cand = {}
            for s, d in D.items():
                j = d.get("_ft_pos")
                # mapear tms al indice de settlement propio del simbolo (mas cercano <=)
                k2 = np.searchsorted(d["ft"], tms, side="right") - 1
                if k2 < trail_k or k2 >= len(d["ft"]):
                    continue
                v = TR[s][k2]
                if np.isfinite(v) and v > 0:
                    cand[s] = (v, k2)
            if len(cand) < n_legs:
                continue
            if only_extreme is not None:
                allv = [v for v, k2 in cand.values()]
                thr = np.percentile(allv, only_extreme)
                cand = {s: vk for s, vk in cand.items() if vk[0] >= thr}
                if len(cand) < n_legs:
                    continue
            if placebo == "random_selection":
                keys = list(cand); rng.shuffle(keys); chosen = keys[:n_legs]
            elif placebo == "matched_vol":
                # rankear por volatilidad realizada del perp en vez de funding (misma cantidad de legs)
                volmap = {}
                for s in cand:
                    d = D[s]; k2 = cand[s][1]
                    i_p = nearest_perp_idx(d, d["ft"][k2])
                    if i_p is None or i_p < 96:
                        continue
                    r = np.diff(np.log(d["pc"][max(0, i_p - 96):i_p + 1]))
                    volmap[s] = np.std(r) if len(r) > 5 else np.nan
                volmap = {s: v for s, v in volmap.items() if np.isfinite(v)}
                chosen = sorted(volmap, key=lambda s: volmap[s], reverse=True)[:n_legs]
            else:
                chosen = sorted(cand, key=lambda s: cand[s][0], reverse=True)[:n_legs]
            if len(chosen) < 1:
                continue
            # pesos
            if weight_scheme == "equal":
                w = {s: 1.0 / len(chosen) for s in chosen}
            elif weight_scheme == "funding_weighted":
                tot = sum(cand[s][0] for s in chosen)
                w = {s: cand[s][0] / tot for s in chosen}
            elif weight_scheme == "capped":
                base = 1.0 / len(chosen); cap = min(0.4, base * 2)
                w = {s: min(cap, base) for s in chosen}
                tot = sum(w.values()); w = {s: v / tot for s, v in w.items()}
            else:
                w = {s: 1.0 / len(chosen) for s in chosen}

            # capital = notional*(1 spot) + notional/leverage (margen perp)  =>  notional = capital/(1+1/leverage)
            notional_total = capital / (1 + 1 / leverage)

            # cerrar posiciones que ya no estan en 'chosen' (turnover)
            for s in list(book):
                if s not in chosen:
                    entry_ms, entry_kf, notion = book.pop(s)
                    d = D[s]
                    i_p0 = nearest_perp_idx(d, entry_ms); i_p1 = nearest_perp_idx(d, tms)
                    if i_p0 is None or i_p1 is None:
                        continue
                    spot0 = d["spot"][i_p0]; spot1 = d["spot"][i_p1]
                    perp0 = d["pc"][i_p0]; perp1 = d["pc"][i_p1]
                    if not (np.isfinite(spot0) and np.isfinite(spot1) and perp0 > 0 and perp1 > 0):
                        continue
                    price_pnl = notion * (math.log(spot1 / spot0) - math.log(perp1 / perp0))
                    close_kf = int(np.searchsorted(d["ft"], tms, side="right"))
                    fund_pnl = notion * float(np.sum(d["fr"][entry_kf:close_kf]))
                    fees = notion * RT_BP_PAIR / 1e4
                    trades.append((entry_ms, tms, s, notion, fund_pnl, price_pnl, fees))
            # abrir nuevas
            for s in chosen:
                if s not in book:
                    notion = notional_total * w[s]
                    k2 = cand[s][1]
                    book[s] = (tms, k2, notion)
        # cerrar lo que quede abierto al final
        for s, (entry_ms, entry_kf, notion) in book.items():
            d = D[s]
            i_p0 = nearest_perp_idx(d, entry_ms); i_p1 = len(d["pt"]) - 1
            if i_p0 is None:
                continue
            spot0 = d["spot"][i_p0]; spot1 = d["spot"][i_p1]
            perp0 = d["pc"][i_p0]; perp1 = d["pc"][i_p1]
            if not (np.isfinite(spot0) and np.isfinite(spot1) and perp0 > 0 and perp1 > 0):
                continue
            price_pnl = notion * (math.log(spot1 / spot0) - math.log(perp1 / perp0))
            fund_pnl = notion * float(np.sum(d["fr"][entry_kf:]))
            fees = notion * RT_BP_PAIR / 1e4
            trades.append((entry_ms, int(d["pt"][-1]), s, notion, fund_pnl, price_pnl, fees))
        return trades

    def summarize(trades, label, capital):
        if len(trades) < 5:
            print(f"  {label}: trades insuficientes ({len(trades)})"); return None
        gross_fund = sum(t[4] for t in trades)
        gross_price = sum(t[5] for t in trades)
        fees = sum(t[6] for t in trades)
        net = gross_fund + gross_price - fees
        span_days = (max(t[1] for t in trades) - min(t[0] for t in trades)) / 86400000 or 1
        net_mo = net / (span_days / 30)
        fund_mo = gross_fund / (span_days / 30)
        fees_mo = fees / (span_days / 30)
        price_mo = gross_price / (span_days / 30)
        # por mes
        bym = collections.defaultdict(float)
        for t in trades:
            mk = datetime.utcfromtimestamp(t[0] / 1000).strftime("%Y-%m")
            netleg = t[4] + t[5] - t[6]
            bym[mk] += netleg
        months = np.array(sorted(bym.values())) if bym else np.array([0.0])
        eq = np.cumsum([t[4] + t[5] - t[6] for t in sorted(trades, key=lambda x: x[1])])
        dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
        flag = "  <<< SUPERA 150" if net_mo >= 150 else ("  (PARK zone 75-149)" if 75 <= net_mo < 150 else "")
        print(f"  {label}: trades={len(trades)}  NET/mes=${net_mo:.1f}  (funding/mes=${fund_mo:.1f} price/mes=${price_mo:.1f} fees/mes=${fees_mo:.1f})  "
              f"maxDD=${dd:.1f}  worst_mes=${months.min():.1f}  best_mes=${months.max():.1f}  "
              f"meses+/-={int((months>0).sum())}/{int((months<0).sum())}{flag}")
        return dict(net_mo=net_mo, fund_mo=fund_mo, price_mo=price_mo, fees_mo=fees_mo, dd=dd,
                    worst=float(months.min()), best=float(months.max()), n_trades=len(trades),
                    pos_months=int((months > 0).sum()), neg_months=int((months < 0).sum()))

    print("\n" + "#" * 70 + "\n# ESTRUCTURA A (LONG SPOT + SHORT PERP, funding positivo) — OPERABLE\n" + "#" * 70)
    results = {}
    print("\n-- Sensibilidad de N (rebal=24h, trail=24h, equal-weight, lev=3x, cap=450) --")
    for N in N_OPTIONS:
        tr = run_strategy("24h", "24h", N, "equal", LEV_PERP, 450)
        r = summarize(tr, f"N={N}", 450)
        results[f"N{N}"] = r

    print("\n-- Sensibilidad de rebalanceo (N=3, trail=24h, equal, lev=3x, cap=450) --")
    for rlbl in REBAL_OPTIONS:
        tr = run_strategy(rlbl, "24h", 3, "equal", LEV_PERP, 450)
        r = summarize(tr, f"rebal={rlbl}", 450)
        results[f"rebal_{rlbl}"] = r

    print("\n-- Sensibilidad de ventana trailing (N=3, rebal=24h, equal, lev=3x, cap=450) --")
    for tlbl in TRAIL_WINDOWS:
        tr = run_strategy("24h", tlbl, 3, "equal", LEV_PERP, 450)
        r = summarize(tr, f"trail={tlbl}", 450)
        results[f"trail_{tlbl}"] = r

    print("\n-- Esquemas de ponderación (N=5, rebal=24h, trail=24h, lev=3x, cap=450) --")
    for wsch in ("equal", "funding_weighted", "capped"):
        tr = run_strategy("24h", "24h", 5, wsch, LEV_PERP, 450)
        r = summarize(tr, f"weight={wsch}", 450)
        results[f"weight_{wsch}"] = r

    print("\n-- Capital y leverage (N=3, rebal=24h, trail=24h, equal) --")
    for cap in CAPITALS:
        for lev in (1.0, 3.0):
            tr = run_strategy("24h", "24h", 3, "equal", lev, cap)
            r = summarize(tr, f"cap=${cap} lev={lev}x", cap)
            results[f"cap{cap}_lev{lev}"] = r

    # mejor config heuristica para el resto de las pruebas
    best_key = max(results, key=lambda k: results[k]["net_mo"] if results[k] else -1e9)
    print(f"\n>>> Mejor config hasta ahora: {best_key} -> ${results[best_key]['net_mo']:.1f}/mes")
    BEST = dict(rebal="24h", trail="24h", n=5, weight="equal", lev=3.0, cap=450)   # config primaria congelada

    print("\n" + "#" * 70 + "\n# SLICES TEMPORALES (config primaria: N=5, rebal=24h, trail=24h, equal, lev=3x, cap=450)\n" + "#" * 70)
    all_days = []
    ref = "BTCUSDT" if "BTCUSDT" in D else list(D)[0]
    for t in D[ref]["ft"]:
        all_days.append(datetime.utcfromtimestamp(int(t) / 1000).date())
    all_days = sorted(set(all_days))
    tcut, vcut = all_days[int(len(all_days) * 0.5)], all_days[int(len(all_days) * 0.75)]
    print(f"corte TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")

    tr_full = run_strategy("24h", "24h", 5, "equal", 3.0, 450)
    summarize(tr_full, "Slice A (dataset completo)", 450)
    tr_exq3 = run_strategy("24h", "24h", 5, "equal", 3.0, 450, exclude_q3=True)
    summarize(tr_exq3, "Slice B (excluye Q3-2026 explícitamente)", 450)
    tr_oos = [t for t in tr_full if datetime.utcfromtimestamp(t[0] / 1000).date() > vcut]
    summarize(tr_oos, "Slice C (OOS puro, > vcut)", 450)
    tr_train = [t for t in tr_full if datetime.utcfromtimestamp(t[0] / 1000).date() <= tcut]
    summarize(tr_train, "  (referencia) TRAIN puro", 450)
    tr_val = [t for t in tr_full if tcut < datetime.utcfromtimestamp(t[0] / 1000).date() <= vcut]
    summarize(tr_val, "  (referencia) VAL puro", 450)
    tr_extreme = run_strategy("24h", "24h", 5, "equal", 3.0, 450, only_extreme=75)
    summarize(tr_extreme, "Slice D (solo funding extremo, >p75 del cross-section)", 450)

    print("\n" + "#" * 70 + "\n# PLACEBOS / CONTROLES (config primaria)\n" + "#" * 70)
    tr_rand = run_strategy("24h", "24h", 5, "equal", 3.0, 450, placebo="random_selection")
    summarize(tr_rand, "PLACEBO random_selection (mismo N, símbolo al azar entre funding+)", 450)
    tr_vol = run_strategy("24h", "24h", 5, "equal", 3.0, 450, placebo="matched_vol")
    summarize(tr_vol, "CONTROL matched_vol (rankea por volatilidad, no por funding)", 450)

    print("\n" + "#" * 70 + "\n# ESTRUCTURA B (SHORT SPOT + LONG PERP, funding negativo) — NO OPERABLE\n" + "#" * 70)
    print("  No hay datos de borrow-rate ni infraestructura de margen para vender spot en corto.")
    print("  Cálculo matemático SOLO para diagnóstico (funding negativo capturado sin costo de préstamo,")
    print("  que en la realidad SIEMPRE existe y suele ser mayor al funding capturado en altcoins ilíquidas):")
    neg_pnl = 0.0; neg_n = 0
    for s, d in D.items():
        neg = d["fr"][d["fr"] < 0]
        neg_pnl += -float(neg.sum())   # si fueramos long perp, cobramos -funding
        neg_n += len(neg)
    print(f"  (diagnóstico bruto, SIN costo de borrow, SIN fees) suma funding negativo capturable: {neg_pnl*1e4:.0f} bp-equivalente sobre {neg_n} settlements -- IRRELEVANTE sin borrow-rate real. NO OPERABLE, no se reporta como estrategia.")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "universe": syms,
           "n_symbols": len(D), "window": [dd(span0), dd(span1)], "results": results,
           "best_key": best_key}
    json.dump(out, open(os.path.join(ROOT, "scratch_r16_funding_carry.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r16_funding_carry.json")


if __name__ == "__main__":
    main()
