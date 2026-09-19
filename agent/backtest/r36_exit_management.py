"""
ROUND 36 — SIMULACION CONTRAFACTUAL DE GESTION DE SALIDA sobre los 2,612
trades reales reconstruidos en R35. NO es una nueva estrategia de
entrada -- las señales, direccion, entrada, SL y TP originales quedan
EXACTAMENTE iguales; solo se simula que pasaria si, ademas, se aplicara
una regla de gestion dinamica de salida (break-even, take-profit parcial,
o trailing stop) sobre la MISMA trayectoria real de precio.

Orden temporal respetado barra a barra (15m), con convencion PESIMISTA
explicita: si dentro de la misma barra el precio toca el stop ANTES de
que la regla haya tenido oportunidad de moverlo (i.e. ambiguedad de "que
paso primero" dentro de la barra), se asume que el stop original se
ejecuta -- nunca se asume el mejor caso.
"""
import os, sys, math, numpy as np, sqlite3, collections, json
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CAP_BARS = 2880   # 30 dias de 15m, limite generoso para la trayectoria contrafactual
FEE_PER_TRADE = 0.12   # observado en DB (EntryFee+ExitFee ~ $0.06+$0.06 sobre notional $150)


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Symbol","Side","EntryPrice","ClosePrice","SlPrice","TpPrice",
                   "OpenedAt","ClosedAt","ExitReason","RealizedPnl","StrategyProfileId","Amount"
                   FROM "SimulatedTrades" WHERE "ExitReason" IN ('tp_hit','sl_hit')""")
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(con, symbol):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)).fetchall()
    if len(k) < 3000:
        return None
    t = np.array([r[0] for r in k], np.int64); o = np.array([r[1] for r in k], float)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float)
    c = np.array([r[4] for r in k], float); v = np.array([r[5] for r in k], float)
    return dict(t=t, o=o, h=h, l=l, c=c, v=v)


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def bp(side, entry, px):
    return side * math.log(px / entry) * 1e4


def simulate_rule(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size, rule):
    """Camina barra a barra desde i_start (inclusive) hasta CAP_BARS, aplicando
    `rule`. Devuelve dict con pnl_usd, exit_reason, bars_used, mfe_bp_running_al_cierre.
    rule = {'type':'baseline'} | {'type':'be','thresholds':[bp,...]} |
           {'type':'partial','steps':[(thr_bp, close_frac, after)]} |
           {'type':'trail','steps':[(thr_bp, new_sl_bp)]}
    'after' en partial: 'be' (resto a breakeven) o 'tp' (resto sigue al TP original).
    """
    sl_cur = sl0_px
    tp_cur = tp0_px
    remaining = 1.0
    realized = 0.0
    be_applied = set()
    trail_applied = set()
    partial_applied = set()
    max_fav_bp = 0.0
    n_bars_avail = min(CAP_BARS, n - i_start)
    exit_reason = "time_cap"
    exit_bar_offset = n_bars_avail

    for k in range(n_bars_avail):
        j = i_start + k
        hi, lo = h[j], l[j]
        # a) chequear stop actual (adverso) PRIMERO -- convencion pesimista
        sl_hit = (lo <= sl_cur) if side > 0 else (hi >= sl_cur)
        if sl_hit:
            exit_px = sl_cur
            realized += remaining * side * (exit_px - entry_px) * size
            exit_reason = "sl_or_be"
            exit_bar_offset = k
            remaining = 0.0
            break
        # b) chequear TP actual (si queda parte abierta apuntando al TP original o de la regla)
        tp_hit = (hi >= tp_cur) if side > 0 else (lo <= tp_cur)
        if tp_hit and tp_cur is not None:
            exit_px = tp_cur
            realized += remaining * side * (exit_px - entry_px) * size
            exit_reason = "tp"
            exit_bar_offset = k
            remaining = 0.0
            break
        # c) actualizar excursion favorable y aplicar reglas pendientes
        fav_px = hi if side > 0 else lo
        fav_bp = bp(side, entry_px, fav_px)
        if fav_bp > max_fav_bp:
            max_fav_bp = fav_bp

        if rule["type"] == "be":
            for thr in rule["thresholds"]:
                if thr not in be_applied and fav_bp >= thr:
                    be_applied.add(thr)
                    sl_cur = entry_px   # mover a breakeven (sin comision extra modelada aparte, ya incluida en FEE_PER_TRADE)
        elif rule["type"] == "trail":
            for (thr, new_sl_bp) in rule["steps"]:
                if thr not in trail_applied and fav_bp >= thr:
                    trail_applied.add(thr)
                    new_sl_px = entry_px * math.exp(side * new_sl_bp / 1e4)
                    if side > 0:
                        sl_cur = max(sl_cur, new_sl_px)
                    else:
                        sl_cur = min(sl_cur, new_sl_px)
        elif rule["type"] == "partial":
            for (thr, frac, after) in rule["steps"]:
                key = (thr, frac, after)
                if key not in partial_applied and fav_bp >= thr and remaining > 0:
                    partial_applied.add(key)
                    close_now = min(frac, remaining)
                    exit_px = entry_px * math.exp(side * thr / 1e4)
                    realized += close_now * side * (exit_px - entry_px) * size
                    remaining -= close_now
                    if after == "be":
                        sl_cur = entry_px
                    elif after == "tp":
                        pass  # tp_cur ya es el original
    else:
        # se acabo el CAP sin cerrar del todo: liquidar el resto al ultimo close disponible
        if remaining > 0:
            j_last = min(i_start + n_bars_avail - 1, n - 1)
            exit_px = (h[j_last] + l[j_last]) / 2
            realized += remaining * side * (exit_px - entry_px) * size
            remaining = 0.0

    realized -= FEE_PER_TRADE
    return dict(pnl_usd=realized, exit_reason=exit_reason, bars_used=exit_bar_offset, max_fav_bp=max_fav_bp)


RULES = {
    "baseline": {"type": "baseline"},
    "BE-1_50bp": {"type": "be", "thresholds": [50]},
    "BE-2_75bp": {"type": "be", "thresholds": [75]},
    "BE-3_100bp": {"type": "be", "thresholds": [100]},
    "BE-4_150bp": {"type": "be", "thresholds": [150]},
    "BE-5_200bp": {"type": "be", "thresholds": [200]},
    "Partial-A_100to25_TPrest": {"type": "partial", "steps": [(100, 0.25, "tp")]},
    "Partial-B_100to50_BErest": {"type": "partial", "steps": [(100, 0.5, "be")]},
    "Partial-C_150to25_250BErest": {"type": "partial", "steps": [(150, 0.25, "be"), (250, 0.0, "be")]},
    "Partial-D_200to50_TPrest": {"type": "partial", "steps": [(200, 0.5, "tp")]},
    "Trail-1": {"type": "trail", "steps": [(100, 0), (150, 50), (200, 100)]},
    "Trail-2": {"type": "trail", "steps": [(150, 50), (250, 100)]},
}


def main():
    print("=== ROUND 36 — SIMULACION CONTRAFACTUAL DE GESTION DE SALIDA ===\n")
    trades = load_trades()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    syms = sorted(set(t[0] for t in trades))
    kdata = {}
    for s in syms:
        d = load_symbol_klines(con, s)
        if d is not None:
            kdata[s] = d
    con.close()
    print(f"trades totales tp/sl: {len(trades)}  simbolos con klines: {len(kdata)}/{len(syms)}")

    recs = []
    skipped = 0
    for (sym, side_raw, entry_px, close_px, sl_px, tp_px, opened, closed, reason, pnl_v, prof, amount) in trades:
        if sym not in kdata or sl_px is None or tp_px is None:
            skipped += 1
            continue
        d = kdata[sym]
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None or i < 100 or i + 10 >= len(d["c"]):
            skipped += 1
            continue
        side = 1 if side_raw == 0 else -1
        entry_px = float(entry_px); sl_px = float(sl_px); tp_px = float(tp_px)
        size = float(amount) / entry_px
        recs.append(dict(symbol=sym, side=side, entry_px=entry_px, sl0=sl_px, tp0=tp_px, size=size,
                          i=i + 1, opened=opened, closed=closed, orig_reason=reason,
                          orig_pnl=float(pnl_v) if pnl_v else 0.0, profile=str(prof), d=d))
    print(f"trades simulables: {len(recs)}  (descartados sin kline/SL/TP: {skipped})\n")

    def seg2(dt):
        # split temporal simple: primera vs segunda mitad por fecha de apertura
        return None

    dates_sorted = sorted(r["opened"] for r in recs)
    mid = dates_sorted[len(dates_sorted) // 2]
    tcut = dates_sorted[int(len(dates_sorted) * 0.5)]
    vcut = dates_sorted[int(len(dates_sorted) * 0.75)]
    def seg3(dt): return "train" if dt <= tcut else ("val" if dt <= vcut else "oos")

    print(f"corte TRAIN/VAL/OOS por fecha de apertura: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    results = {rname: {"train": [], "val": [], "oos": [], "half1": [], "half2": []} for rname in RULES}
    baseline_calib_diff = []

    for r in recs:
        n = len(r["d"]["c"])
        h, l = r["d"]["h"], r["d"]["l"]
        seg = seg3(r["opened"])
        half = "half1" if r["opened"] <= mid else "half2"
        for rname, rule in RULES.items():
            sim = simulate_rule(h, l, r["i"], n, r["side"], r["entry_px"], r["sl0"], r["tp0"], r["size"], rule)
            results[rname][seg].append((sim["pnl_usd"], r["orig_pnl"], sim["exit_reason"], r))
            results[rname][half].append((sim["pnl_usd"], r["orig_pnl"], sim["exit_reason"], r))
            if rname == "baseline":
                baseline_calib_diff.append(sim["pnl_usd"] - r["orig_pnl"])

    calib = np.array(baseline_calib_diff)
    print(f"CALIBRACION baseline reconstruido vs RealizedPnl real: diff media=${calib.mean():.3f} "
          f"mediana=${np.median(calib):.3f} (debería ser chico -- valida el motor de simulacion)\n")

    print("#" * 100)
    print(f"{'REGLA':30s} {'seg':6s} {'n':>5s} {'PnL':>10s} {'PnL/mes':>9s} {'vs_base':>9s} "
          f"{'WR':>5s} {'PF':>6s} {'salvados':>9s} {'empeorados':>10s}")
    print("#" * 100)

    baseline_by_seg = {}
    for rname in RULES:
        for seg in ("train", "val", "oos"):
            rows = results[rname][seg]
            if len(rows) < 20:
                continue
            pnl = np.array([x[0] for x in rows])
            orig = np.array([x[1] for x in rows])
            days_span = (max(r["opened"] for r in recs if seg3(r["opened"]) == seg) -
                         min(r["opened"] for r in recs if seg3(r["opened"]) == seg)).days or 1
            pnl_mo = pnl.sum() / (days_span / 30)
            wr = (pnl > 0).mean()
            grossp = pnl[pnl > 0].sum(); grossl = -pnl[pnl < 0].sum()
            pf = grossp / grossl if grossl > 0 else float("inf")
            if rname == "baseline":
                baseline_by_seg[seg] = pnl.sum()
            delta_vs_base = pnl.sum() - baseline_by_seg.get(seg, pnl.sum())
            saved = int(((orig < 0) & (pnl > orig)).sum())
            worsened = int(((orig > 0) & (pnl < orig)).sum())
            print(f"{rname:30s} {seg:6s} {len(rows):5d} ${pnl.sum():9.1f} ${pnl_mo:8.1f} ${delta_vs_base:8.1f} "
                  f"{wr:5.2f} {pf:6.2f} {saved:9d} {worsened:10d}")
        print()

    print("#" * 100 + "\n SPLIT TEMPORAL (mitad 1 vs mitad 2) -- estabilidad\n" + "#" * 100)
    for rname in RULES:
        r1 = results[rname]["half1"]; r2 = results[rname]["half2"]
        if len(r1) < 20 or len(r2) < 20:
            continue
        p1 = np.array([x[0] for x in r1]).sum(); p2 = np.array([x[0] for x in r2]).sum()
        print(f"  {rname:30s} half1_PnL=${p1:8.1f}  half2_PnL=${p2:8.1f}")

    print("\nfin FASE 2-7 de R36 -- ver PARTE B para el desglose de los 1032 SL con MFE>=100bp")

    out = {"recs_n": len(recs), "calib_mean": float(calib.mean())}
    with open(os.path.join(HERE, "..", "..", "scratch_r36_summary.json"), "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
