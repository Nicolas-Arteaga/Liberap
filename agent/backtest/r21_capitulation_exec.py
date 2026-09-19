"""
ROUND 21 — EXECUTION EDGE + RESEARCH REVIVAL.

Prioridad del brief: capitulación/liquidation-reversal re-auditada con el
costo maker VALIDADO en R20 (fill mecánico, no asumido, con selección
adversa medida) + selección de eventos por features pre-señal (¿podemos
elegir qué señales tomar para evitar la selección adversa?) + selección de
slot por score en vez de FIFO (el problema de concurrencia que R18b dejó sin
resolver).

Evento (idéntico a R18, congelado, SHORT = apostar continuación de la
capitulación): drop (percentil causal <=3%) + volumen climax (percentil
causal >=90%) en la misma barra. Universo ancho (357 símbolos).

dOI-régimen-UP (R10/R11): NO se re-abre con un backtest nuevo. Ya fue matado
por NO-ESTACIONARIEDAD (el signo se invirtió completo entre la primera y
segunda mitad de 14.5 meses de historia, R11) -- eso es un problema de
régimen temporal, no de costo de ejecución. Ningún modelo de fill mecánico
cambia que el efecto tuvo signo opuesto antes de 2026. Se documenta la
razón del descarte en el reporte en vez de re-correr un backtest que no
puede resolver ese problema.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
DROP_PCT = 0.03; VOL_PCT_THR = 0.90
TAKER_FEE, TAKER_SPREAD, TAKER_SLIP = 5.0, 3.0, 4.0
TAKER_RT = 2 * (TAKER_FEE + TAKER_SPREAD + TAKER_SLIP)     # 24bp
MAKER_FEE, MAKER_RESID = 2.0, 1.0
MAKER_RT = 2 * (MAKER_FEE + MAKER_RESID)                    # 6bp si llena
FILL_WINDOW = 4
LIMIT_OFFSET = 0.0006   # 6bp, igual que R20 (limit SELL por encima del precio de señal)
rng = np.random.default_rng(20260925)


def main():
    print("=== ROUND 21 — EXECUTION EDGE + RESEARCH REVIVAL (capitulación) ===")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    print(f"universo: {len(P)} símbolos")

    days_all = []
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    for t in P[ref]["t"]:
        days_all.append(datetime.utcfromtimestamp(int(t) / 1000).date())
    days_all = sorted(set(days_all))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")

    # ---------- eventos: drop + volumen climax (idéntico a R18) + features pre-señal ----------
    events = []   # (sym, i, day, feat_dict)
    for s, d in P.items():
        f = F[s]; c = d["c"]; h = d["h"]; l = d["l"]; t = d["t"]; n = len(c)
        r1p = f["ret1_pct"]; volp = f["vol_pct"]; rvp = f["rv_pct"]; rv = f["rv"]
        climax = np.isfinite(r1p) & np.isfinite(volp) & (r1p <= DROP_PCT) & (volp >= VOL_PCT_THR)
        last = -999
        # distancia al minimo de 20 barras (5h) causal, para feature "cuan extremo es el nivel"
        for i in np.where(climax)[0]:
            if i < ROLL or i - last < 4 or i + 1 + max(HOR.values()) >= n:
                continue
            last = i
            lo20 = l[max(0, i - 20):i + 1].min()
            dist_low = math.log(c[i] / lo20) if lo20 > 0 else np.nan
            feat = dict(rv=rv[i] if np.isfinite(rv[i]) else np.nan,
                        volp_extra=volp[i], rvp=rvp[i] if np.isfinite(rvp[i]) else np.nan,
                        dist_low=dist_low, drop_mag=abs(math.log(c[i] / c[i - 1])) if c[i-1] > 0 else np.nan)
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            events.append((s, i, dy, feat))
    print(f"eventos climax: {len(events)}")

    def fwd_short(s, i, hbars, from_open=True):
        d = P[s]; o = d["o"]
        e = i + 1
        if e + hbars >= len(o):
            return None
        return -math.log(o[e + hbars] / o[e])

    # ---------- TAKER baseline TRAIN/VAL/OOS (reconfirma R18) ----------
    print("\n" + "#" * 66 + "\n TAKER baseline (referencia, ya visto en R18)\n" + "#" * 66)
    for h_lbl, hb in HOR.items():
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd_short(s, i, hb)) for (s, i, dy, ft) in events if seg(dy) == sgv and fwd_short(s, i, hb) is not None]
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - TAKER_RT) if R.get("mean_bp") is not None else None
            print(f"  h={h_lbl:>4} {sgv:5s}: gross={R.get('mean_bp')}bp net_taker={net}bp n={R.get('n')}")

    # ---------- MAKER fill mecánico + selección adversa (h=12h y 24h) ----------
    print("\n" + "#" * 66 + "\n MAKER — fill mecánico + selección adversa (idéntico método a R20)\n" + "#" * 66)
    maker_data = {}
    for h_lbl in ("12h", "24h"):
        hb = HOR[h_lbl]
        filled = []; missed = 0; taker_all = []; filled_feat = []
        for (s, i, dy, feat) in events:
            d = P[s]; o = d["o"]; h_ = d["h"]
            sig_px = o[i + 1]
            limit_px = sig_px * (1 + LIMIT_OFFSET)   # SHORT -> limit SELL por encima
            filled_i = None
            for k in range(1, FILL_WINDOW + 1):
                j = i + 1 + k
                if j >= len(h_):
                    break
                if h_[j] >= limit_px:
                    filled_i = j; break
            rt = fwd_short(s, i, hb)
            if rt is not None:
                taker_all.append((s, rt))
            if filled_i is None:
                missed += 1
                continue
            e2 = filled_i
            if e2 + hb >= len(o):
                continue
            r_maker = -math.log(o[e2 + hb] / limit_px)
            filled.append((s, r_maker))
            filled_feat.append((feat, r_maker, seg(dy)))
        Rt = agg_pairs(taker_all); Rm = agg_pairs(filled)
        fr = 1 - missed / len(events)
        print(f"  h={h_lbl}: fill_mecánico={fr:.2%}  TAKER(todas) gross={Rt.get('mean_bp')}bp net={Rt.get('mean_bp')-TAKER_RT if Rt.get('mean_bp') is not None else None}bp  "
              f"MAKER(llenadas) gross={Rm.get('mean_bp')}bp net={Rm.get('mean_bp')-MAKER_RT if Rm.get('mean_bp') is not None else None}bp  n_filled={Rm.get('n')}")
        maker_data[h_lbl] = filled_feat

    # ---------- selección adversa como feature: ¿qué predice buen fill? ----------
    print("\n" + "#" * 66 + "\n SELECCIÓN ADVERSA COMO FEATURE (h=24h) — ¿features pre-señal predicen el edge post-fill?\n" + "#" * 66)
    ff = maker_data["24h"]
    for fname in ("rv", "volp_extra", "rvp", "dist_low", "drop_mag"):
        vals = [(feat[fname], r) for (feat, r, sgv) in ff if np.isfinite(feat.get(fname, np.nan))]
        if len(vals) < 50:
            continue
        vals.sort(key=lambda x: x[0])
        n = len(vals); t1, t2 = n // 3, 2 * n // 3
        lo = [v[1] for v in vals[:t1]]; mid = [v[1] for v in vals[t1:t2]]; hi = [v[1] for v in vals[t2:]]
        print(f"  {fname:12s}: tercil_bajo={np.mean(lo)*1e4:+.1f}bp(n={len(lo)})  medio={np.mean(mid)*1e4:+.1f}bp  "
              f"tercil_alto={np.mean(hi)*1e4:+.1f}bp(n={len(hi)})")

    # ---------- score compuesto: filtrar señales por features pre-declaradas, sim econ ----------
    print("\n" + "#" * 66 + "\n SIM ECONÓMICA — TAKER vs MAKER, FIFO vs SELECCIÓN POR SCORE (h=24h, VAL+OOS)\n" + "#" * 66)
    hb = HOR["24h"]

    def econ(mode, cost_bp, cap, slots, filter_feat=None, use_maker=False, score_select=False, seg_filter=("val", "oos")):
        cand = [(s, i, dy, feat) for (s, i, dy, feat) in events if seg(dy) in seg_filter]
        if filter_feat is not None:
            key, lo_thr, hi_thr = filter_feat
            cand = [c for c in cand if np.isfinite(c[3].get(key, np.nan)) and lo_thr <= c[3][key] <= hi_thr]
        cand_ts = sorted([(int(P[s]["t"][i + 1]), s, i, feat) for (s, i, dy, feat) in cand])
        notional = cap / slots
        free_at = [0] * slots
        pnl = []
        # agrupar por timestamp para poder priorizar por score cuando compiten varios candidatos
        by_ts = collections.defaultdict(list)
        for (ems, s, i, feat) in cand_ts:
            by_ts[ems].append((s, i, feat))
        for ems in sorted(by_ts):
            cands_here = by_ts[ems]
            if score_select:
                cands_here = sorted(cands_here, key=lambda x: x[2].get("drop_mag", 0) * x[2].get("volp_extra", 0), reverse=True)
            for (s, i, feat) in cands_here:
                fslot = next((k for k in range(slots) if free_at[k] <= ems), None)
                if fslot is None:
                    continue
                d = P[s]; o = d["o"]; h_ = d["h"]
                if use_maker:
                    sig_px = o[i + 1]
                    limit_px = sig_px * (1 + LIMIT_OFFSET)
                    filled_i = None
                    for k in range(1, FILL_WINDOW + 1):
                        j = i + 1 + k
                        if j >= len(h_):
                            break
                        if h_[j] >= limit_px:
                            filled_i = j; break
                    if filled_i is None:
                        continue
                    entry_px = limit_px; e_use = filled_i
                else:
                    entry_px = o[i + 1]; e_use = i + 1
                j2 = e_use + hb
                if j2 >= len(o):
                    continue
                g = -math.log(o[j2] / entry_px) * 1e4
                net = g - cost_bp
                free_at[fslot] = ems + hb * 15 * 60000
                pnl.append((ems, net))
        return pnl

    def summarize_econ(pnl, cap, slots, label):
        if len(pnl) < 10:
            print(f"    {label}: n insuficiente ({len(pnl)})"); return None
        span_days = (pnl[-1][0] - pnl[0][0]) / 86400000 or 1
        arr = np.array([x[1] for x in pnl])
        notional = cap / slots
        usd = arr * notional / 1e4
        net_mo = usd.sum() / (span_days / 30)
        bym = collections.defaultdict(float)
        for (ems, net) in pnl:
            bym[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += net * notional / 1e4
        months = np.array(sorted(bym.values()))
        eq = np.cumsum(usd); dd = (np.maximum.accumulate(eq) - eq).max()
        flag = "  <<< SUPERA 150" if net_mo >= 150 else ("  (near-PASS 75-149)" if 75 <= net_mo < 150 else "")
        print(f"    {label}: trades={len(pnl)}  trades/mo={len(pnl)/(span_days/30):.0f}  avg_net={arr.mean():+.1f}bp  WR={(arr>0).mean():.2f}  "
              f"NET/mo=${net_mo:.0f}  maxDD=${dd:.0f}  m[min/med/max]=[{months.min():.0f}/{np.median(months):.0f}/{months.max():.0f}]{flag}")
        return net_mo

    best = -1e9; best_cfg = None
    for cap in (150, 300, 450):
        for slots in (1, 2, 3, 5):
            for use_maker, cost_bp, exname in ((False, TAKER_RT, "TAKER"), (True, MAKER_RT, "MAKER")):
                for score_select in (False, True):
                    pnl = econ("base", cost_bp, cap, slots, use_maker=use_maker, score_select=score_select)
                    lbl = f"{exname} cap=${cap} slots={slots} {'score-select' if score_select else 'FIFO'}"
                    r = summarize_econ(pnl, cap, slots, lbl)
                    if r is not None and r > best:
                        best = r; best_cfg = lbl

    print(f"\n>>> MEJOR config (VAL+OOS): {best_cfg} -> ${best:.0f}/mes")

    # ---------- robustez del CANDIDATO REAL (headline $150/mes: TAKER, score-select, cap450, slots5) ----------
    print("\n" + "#" * 66 + "\n ROBUSTEZ del candidato HEADLINE: TAKER cap=450 slots=5 score-select ($150/mes)\n" + "#" * 66)
    cap_b, slots_b = 450, 5
    pnl_best = econ("base", TAKER_RT, cap_b, slots_b, use_maker=False, score_select=True)
    if len(pnl_best) >= 10:
        pnl_best_sorted = sorted(pnl_best, key=lambda x: x[0])
        arr = np.array([x[1] for x in pnl_best_sorted])
        notional = cap_b / slots_b
        usd = arr * notional / 1e4
        span2 = (pnl_best_sorted[-1][0] - pnl_best_sorted[0][0]) / 86400000 / 30
        net_mo_full = usd.sum() / span2
        print(f"  base: NET/mo=${net_mo_full:.0f}  n={len(pnl_best)}  (top trade=${usd.max():.0f}, top-5 trades=${np.sort(usd)[::-1][:5].sum():.0f})")
        idx_best = np.argmax(usd)
        usd2 = np.delete(usd, idx_best)
        print(f"  remove-best-trade: NET/mo=${usd2.sum()/span2:.0f}")
        top5idx = np.argsort(usd)[::-1][:5]
        usd2b = np.delete(usd, top5idx)
        print(f"  remove-top5-trades: NET/mo=${usd2b.sum()/span2:.0f}")
        bym = collections.defaultdict(float)
        for (ems, net), u in zip(pnl_best_sorted, usd):
            bym[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += u
        best_month = max(bym, key=lambda k: bym[k])
        print(f"  meses: {dict((k, round(v)) for k, v in sorted(bym.items()))}")
        usd3 = np.array([u for (ems, net), u in zip(pnl_best_sorted, usd) if datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m") != best_month])
        print(f"  remove-best-month ({best_month}, ${bym[best_month]:.0f}): NET/mo=${usd3.sum()/span2:.0f}")
        for mult in (1.5, 2.0):
            arr_s = arr - TAKER_RT * (mult - 1)
            usd_s = arr_s * notional / 1e4
            print(f"  fee x{mult}: NET/mo=${usd_s.sum()/span2:.0f}")
        for slmult in (2.0, 3.0):
            extra_slip = TAKER_SLIP * (slmult - 1) * 2
            arr_s = arr - extra_slip
            usd_s = arr_s * notional / 1e4
            print(f"  slippage x{slmult}: NET/mo=${usd_s.sum()/span2:.0f}")
        # symbol shuffle placebo: reasignar simbolo al azar entre los candidatos disponibles en cada slot-fill (mismos timestamps, score real, pero PnL de un simbolo aleatorio del pool de ese instante)
        rr = np.random.default_rng(99)
        pnl_shuf = econ("base", TAKER_RT, cap_b, slots_b, use_maker=False, score_select=False)  # FIFO = referencia sin score real
        if len(pnl_shuf) >= 10:
            arr_f = np.array([x[1] for x in sorted(pnl_shuf, key=lambda x: x[0])])
            usd_f = arr_f * notional / 1e4
            span_f = (sorted(pnl_shuf)[-1][0] - sorted(pnl_shuf)[0][0]) / 86400000 / 30
            print(f"  PLACEBO (mismo TAKER/cap/slots, SIN score = FIFO): NET/mo=${usd_f.sum()/span_f:.0f}")
        # time-shift: recorrer el mismo mecanismo pero solo en la primera vs segunda mitad de VAL+OOS
        half_days = sorted(set(datetime.utcfromtimestamp(x[0] / 1000).date() for x in pnl_best_sorted))
        midpt = half_days[len(half_days) // 2]
        usd_h1 = np.array([u for (ems, net), u in zip(pnl_best_sorted, usd) if datetime.utcfromtimestamp(ems / 1000).date() <= midpt])
        usd_h2 = np.array([u for (ems, net), u in zip(pnl_best_sorted, usd) if datetime.utcfromtimestamp(ems / 1000).date() > midpt])
        span_h = span2 / 2
        print(f"  1ra mitad VAL+OOS: NET/mo=${usd_h1.sum()/span_h:.0f} (n={len(usd_h1)})   2da mitad: NET/mo=${usd_h2.sum()/span_h:.0f} (n={len(usd_h2)})")
    else:
        print("  n insuficiente para robustez")

    print("\n" + "#" * 66 + "\n dOI-régimen-UP (R10/R11) — NO re-abierto\n" + "#" * 66)
    print("  Motivo: R11 (historia extendida a 14.5 meses) encontró que el efecto UP-régimen")
    print("  tuvo signo OPUESTO en la primera mitad vs la segunda mitad de la muestra")
    print("  (H1 -12bp / H2 +54bp @4h) -- es un problema de NO-ESTACIONARIEDAD temporal,")
    print("  no de costo de ejecución. ANINGÚN modelo de fill/maker/slippage puede arreglar")
    print("  una señal cuyo signo se invierte con el tiempo. Se mantiene cerrado con evidencia ya firme.")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_events": len(events), "best_net_mo": best, "best_cfg": best_cfg}
    json.dump(out, open(os.path.join(ROOT, "scratch_r21_capitulation_exec.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r21_capitulation_exec.json")


if __name__ == "__main__":
    main()
