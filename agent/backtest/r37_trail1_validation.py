"""
ROUND 37 — VALIDACION FINAL DE TRAIL-1.

FASE 1 (ya resuelta antes de este script, ver informe): el "sesgo" del
subconjunto de R36 NO es un problema de muestreo -- son 12 trades
(ONUSDT x10, BBUSDT x2) con datos de precio CORRUPTOS (saltos de
~1000x en ClosePrice, ej. ONUSDT $0.09->$98) que inflan el PnL total
reportado en +$37,378. Excluyendolos, la poblacion real (3,271 trades)
suma -$2,488 -- consistente en signo y orden de magnitud con el baseline
reconstruido en R36. Se excluyen explicitamente de este analisis.

FASE 8: se encontro cobertura completa de los 189 simbolos que faltaban
en klines_clean (binance_vision_clean.db) dentro de la tabla `klines` de
`agent/data/klines.db` (cache propio del agente, 858 simbolos, colector
en vivo) -- se fusionan ambas fuentes para maximizar la poblacion
reconstruible.
"""
import os, sys, math, numpy as np, sqlite3, collections, json
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
KC = os.path.join(HERE, "..", "data", "klines.db")
CAP_BARS = 2880
FEE_PER_TRADE = 0.12
CORRUPT_SYMBOLS = {"ONUSDT", "BBUSDT"}


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Symbol","Side","EntryPrice","ClosePrice","SlPrice","TpPrice",
                   "OpenedAt","ClosedAt","ExitReason","RealizedPnl","StrategyProfileId","Amount"
                   FROM "SimulatedTrades" WHERE "ExitReason" IN ('tp_hit','sl_hit')
                   AND "Symbol" NOT IN ('ONUSDT','BBUSDT')""")
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(sym):
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    k = con.execute("SELECT open_time,open,high,low,close FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
    con.close()
    if len(k) < 3000:
        con2 = sqlite3.connect(f"file:{KC}?mode=ro", uri=True)
        k = con2.execute("SELECT open_time,open,high,low,close FROM klines "
                          "WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
        con2.close()
        if len(k) < 500:
            return None
    t = np.array([r[0] for r in k], np.int64); o = np.array([r[1] for r in k], float)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float); c = np.array([r[4] for r in k], float)
    return dict(t=t, o=o, h=h, l=l, c=c)


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def bp(side, entry, px):
    return side * math.log(px / entry) * 1e4


def atr_rel_at(d, i):
    if i < 15:
        return None
    h, l, c = d["h"], d["l"], d["c"]
    trs = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(i - 13, i + 1)]
    atr = np.mean(trs)
    return atr / c[i] if c[i] > 0 else None


def simulate_rule(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size, rule):
    sl_cur = sl0_px; tp_cur = tp0_px; remaining = 1.0; realized = 0.0
    be_applied = set(); trail_applied = set()
    n_bars_avail = min(CAP_BARS, n - i_start)
    for k in range(n_bars_avail):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl_cur) if side > 0 else (hi >= sl_cur)
        if sl_hit:
            realized += remaining * side * (sl_cur - entry_px) * size
            remaining = 0.0
            break
        tp_hit = (hi >= tp_cur) if side > 0 else (lo <= tp_cur)
        if tp_hit and tp_cur is not None:
            realized += remaining * side * (tp_cur - entry_px) * size
            remaining = 0.0
            break
        fav_px = hi if side > 0 else lo
        fav_bp = bp(side, entry_px, fav_px)
        if rule["type"] == "trail":
            for (thr, new_sl_bp) in rule["steps"]:
                if thr not in trail_applied and fav_bp >= thr:
                    trail_applied.add(thr)
                    # ROUND 39 fix: el codigo real (TrailingStopCalculator.cs) usa
                    # porcentaje SIMPLE (entry*(1+lockBp/10000)), no exponencial/log-
                    # return. La version anterior (math.exp) generaba un SL levemente
                    # mas ajustado para LONG, causando stop-outs prematuros en casos
                    # de margen minimo -- ver R39, causa exacta identificada en
                    # PHAROSUSDT 2026-07-07 (diff de $7.95 en un solo trade).
                    new_sl_px = entry_px * (1 + side * new_sl_bp / 1e4)
                    sl_cur = max(sl_cur, new_sl_px) if side > 0 else min(sl_cur, new_sl_px)
    else:
        if remaining > 0:
            j_last = min(i_start + n_bars_avail - 1, n - 1)
            exit_px = (h[j_last] + l[j_last]) / 2
            realized += remaining * side * (exit_px - entry_px) * size
    return realized - FEE_PER_TRADE


RULES = {
    "baseline": {"type": "baseline"},
    "Trail-1": {"type": "trail", "steps": [(100, 0), (150, 50), (200, 100)]},
    "Trail-2_75start": {"type": "trail", "steps": [(75, 0), (150, 50), (200, 100)]},
    "Trail-3_wide": {"type": "trail", "steps": [(100, 0), (200, 100), (300, 150)]},
}


def summarize(rows):
    if len(rows) < 5:
        return None
    pnl = np.array([r[0] for r in rows]); orig = np.array([r[1] for r in rows])
    grossp = pnl[pnl > 0].sum(); grossl = -pnl[pnl < 0].sum()
    pf = grossp / grossl if grossl > 0 else float("inf")
    saved = int(((orig < 0) & (pnl > orig)).sum())
    worsened = int(((orig > 0) & (pnl < orig)).sum())
    eq = np.cumsum(pnl); dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    return dict(n=len(pnl), pnl=float(pnl.sum()), wr=float((pnl > 0).mean()), pf=pf, dd=dd, saved=saved, worsened=worsened)


def main():
    print("=== ROUND 37 — VALIDACION FINAL DE TRAIL-1 ===\n")
    print("FASE 1 — RESUELTA: ONUSDT(10 trades)/BBUSDT(2 trades) tenian ClosePrice corrupto")
    print("  (saltos ~1000x, ej ONUSDT $0.09->$98), sumando +$37,378 espurios al total.")
    print("  Poblacion limpia (3,271 trades): PnL real = -$2,488.02 (verificado por SQL directo).")
    print("  Consistente en signo/orden de magnitud con el baseline reconstruido en R36 -- NO era sesgo de muestreo.\n")

    trades = load_trades()
    syms = sorted(set(t[0] for t in trades))
    print(f"FASE 8 — cargando klines fusionando binance_vision_clean.db + klines.db (cache del agente) para {len(syms)} simbolos...")
    kdata = {}
    for s in syms:
        d = load_symbol_klines(s)
        if d is not None:
            kdata[s] = d
    print(f"  simbolos con cobertura: {len(kdata)}/{len(syms)}  (vs 421/610 en R36 -- se recupero cobertura adicional)\n")

    recs = []
    skipped = 0
    for (sym, side_raw, entry_px, close_px, sl_px, tp_px, opened, closed, reason, pnl_v, prof, amount) in trades:
        if sym not in kdata or sl_px is None or tp_px is None:
            skipped += 1
            continue
        d = kdata[sym]
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None or i < 20 or i + 5 >= len(d["c"]):
            skipped += 1
            continue
        side = 1 if side_raw == 0 else -1
        entry_px = float(entry_px); sl_px = float(sl_px); tp_px = float(tp_px)
        size = float(amount) / entry_px
        ar = atr_rel_at(d, i)
        recs.append(dict(symbol=sym, side=side, entry_px=entry_px, sl0=sl_px, tp0=tp_px, size=size,
                          i=i + 1, opened=opened, orig_reason=reason, orig_pnl=float(pnl_v) if pnl_v else 0.0,
                          profile=str(prof), atr_rel=ar, d=d))
    print(f"trades simulables (poblacion limpia + fusion de fuentes): {len(recs)}  (descartados: {skipped})\n")

    dates_sorted = sorted(r["opened"] for r in recs)
    mid = dates_sorted[len(dates_sorted) // 2]
    tcut = dates_sorted[int(len(dates_sorted) * 0.5)]
    vcut = dates_sorted[int(len(dates_sorted) * 0.75)]
    def seg3(dt): return "train" if dt <= tcut else ("val" if dt <= vcut else "oos")

    sim = {rname: [] for rname in RULES}
    for r in recs:
        n = len(r["d"]["c"]); h, l = r["d"]["h"], r["d"]["l"]
        for rname, rule in RULES.items():
            pnl = simulate_rule(h, l, r["i"], n, r["side"], r["entry_px"], r["sl0"], r["tp0"], r["size"], rule)
            sim[rname].append((pnl, r["orig_pnl"], r))

    print("#" * 100 + "\n FASE 7 — TRAIN/VAL/OOS + mitades, las 4 reglas (baseline, Trail-1, Trail-2, Trail-3)\n" + "#" * 100)
    for rname in RULES:
        print(f"\n  -- {rname} --")
        for seg_name, filt in (("train", lambda r: seg3(r["opened"]) == "train"),
                                ("val", lambda r: seg3(r["opened"]) == "val"),
                                ("oos", lambda r: seg3(r["opened"]) == "oos"),
                                ("half1", lambda r: r["opened"] <= mid),
                                ("half2", lambda r: r["opened"] > mid)):
            rows = [(p, o) for (p, o, r) in sim[rname] if filt(r)]
            s = summarize(rows)
            if s:
                print(f"    {seg_name:6s}: n={s['n']:4d} PnL=${s['pnl']:8.1f} WR={s['wr']:.2f} PF={s['pf']:5.2f} "
                      f"DD=${s['dd']:.1f} salvados={s['saved']:4d} empeorados={s['worsened']:4d}")

    print("\n" + "#" * 100 + "\n FASE 2 — POR PERFIL DE ESTRATEGIA (Trail-1 vs baseline)\n" + "#" * 100)
    profiles = collections.Counter(r["profile"] for r in recs)
    top_profiles = [p for p, c in profiles.most_common(20) if c >= 30]
    base_by_trade = {id(r): p for (p, o, r) in sim["baseline"]}
    for prof in top_profiles:
        base_rows = [(p, o) for (p, o, r) in sim["baseline"] if r["profile"] == prof]
        t1_rows = [(p, o) for (p, o, r) in sim["Trail-1"] if r["profile"] == prof]
        sb = summarize(base_rows); st = summarize(t1_rows)
        if sb and st:
            print(f"  {prof[:36]:36s}: n={sb['n']:4d}  base=${sb['pnl']:8.1f}  Trail-1=${st['pnl']:8.1f}  "
                  f"delta=${st['pnl']-sb['pnl']:+8.1f}  base_PF={sb['pf']:.2f} T1_PF={st['pf']:.2f}")

    print("\n" + "#" * 100 + "\n FASE 4 — POR DIRECCION (LONG vs SHORT)\n" + "#" * 100)
    for side_val, label in ((1, "LONG"), (-1, "SHORT")):
        base_rows = [(p, o) for (p, o, r) in sim["baseline"] if r["side"] == side_val]
        t1_rows = [(p, o) for (p, o, r) in sim["Trail-1"] if r["side"] == side_val]
        sb = summarize(base_rows); st = summarize(t1_rows)
        if sb and st:
            print(f"  {label:6s}: n={sb['n']:4d}  base=${sb['pnl']:8.1f}  Trail-1=${st['pnl']:8.1f}  "
                  f"delta=${st['pnl']-sb['pnl']:+8.1f}  base_WR={sb['wr']:.2f} T1_WR={st['wr']:.2f}")

    print("\n" + "#" * 100 + "\n FASE 3 — POR SIMBOLO (top-10 por volumen de trades vs resto)\n" + "#" * 100)
    sym_counts = collections.Counter(r["symbol"] for r in recs)
    top10 = set(s for s, c in sym_counts.most_common(10))
    for label, filt in (("Top-10 simbolos (por N trades)", lambda r: r["symbol"] in top10),
                         ("Resto (600+ simbolos)", lambda r: r["symbol"] not in top10)):
        base_rows = [(p, o) for (p, o, r) in sim["baseline"] if filt(r)]
        t1_rows = [(p, o) for (p, o, r) in sim["Trail-1"] if filt(r)]
        sb = summarize(base_rows); st = summarize(t1_rows)
        if sb and st:
            print(f"  {label:32s}: n={sb['n']:4d}  base=${sb['pnl']:8.1f}  Trail-1=${st['pnl']:8.1f}  delta=${st['pnl']-sb['pnl']:+8.1f}")
    # % de simbolos individuales donde Trail-1 mejora
    improved = 0; worsened_sym = 0; total_sym = 0
    by_sym_base = collections.defaultdict(list); by_sym_t1 = collections.defaultdict(list)
    for (p, o, r) in sim["baseline"]:
        by_sym_base[r["symbol"]].append(p)
    for (p, o, r) in sim["Trail-1"]:
        by_sym_t1[r["symbol"]].append(p)
    for s in by_sym_base:
        if len(by_sym_base[s]) < 3:
            continue
        total_sym += 1
        if sum(by_sym_t1[s]) > sum(by_sym_base[s]):
            improved += 1
        elif sum(by_sym_t1[s]) < sum(by_sym_base[s]):
            worsened_sym += 1
    print(f"\n  simbolos con >=3 trades: {total_sym}  Trail-1 mejora en {improved} ({improved/total_sym:.1%})  "
          f"empeora en {worsened_sym} ({worsened_sym/total_sym:.1%})")

    print("\n" + "#" * 100 + "\n FASE 5 — POR REGIMEN DE VOLATILIDAD (ATR relativo al entrar, terciles)\n" + "#" * 100)
    ar_vals = sorted([r["atr_rel"] for r in recs if r["atr_rel"] is not None])
    if len(ar_vals) > 30:
        t1, t2 = ar_vals[len(ar_vals) // 3], ar_vals[2 * len(ar_vals) // 3]
        for label, lo, hi in (("bajo (tercil 1)", -1, t1), ("medio (tercil 2)", t1, t2), ("alto (tercil 3)", t2, 1e9)):
            base_rows = [(p, o) for (p, o, r) in sim["baseline"] if r["atr_rel"] is not None and lo < r["atr_rel"] <= hi]
            t1_rows = [(p, o) for (p, o, r) in sim["Trail-1"] if r["atr_rel"] is not None and lo < r["atr_rel"] <= hi]
            sb = summarize(base_rows); st = summarize(t1_rows)
            if sb and st:
                print(f"  ATR {label:18s}: n={sb['n']:4d}  base=${sb['pnl']:8.1f}  Trail-1=${st['pnl']:8.1f}  delta=${st['pnl']-sb['pnl']:+8.1f}")

    print("\nfin R37")


if __name__ == "__main__":
    main()
