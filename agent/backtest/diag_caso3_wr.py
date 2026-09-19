"""
DIAGNÓSTICO CAUSAL del sesgo de win rate del motor — MA Slope Caso 3.
NO repara nada. NO optimiza. NO usa lookahead salvo en el modelo DIAGNÓSTICO
(marcado). Aisla qué componente convierte ganadoras reales en perdedoras.

Ground truth: scratch_caso3_gt.json (45 trades reales, join de
scratch_all_trades_p2.csv [tiempos exactos] + agent/data/trades.csv [precios]).
Limitaciones: 45/70 trades (incompleto); `result` de trades.csv está roto
(se recalcula del precio); pnl_usd de trades.csv es aproximado; MAE/MFE NO
disponible (estaba en el `MaxAdversePrice`/`MaxFavorablePrice` de la DB perdida)
-> se reconstruye de klines de 5m y se etiqueta como tal.

Modelos de entrada:
  A candle_close  = close de la vela de 5m que contiene el signal_ts (lo que hace el motor)
  B next_open     = open de la 1a vela de 5m que ABRE después del signal_ts (sin lookahead)
  C real_entry    = precio real de entrada de trades.csv  [DIAGNÓSTICO — leakage]
  D prev_close    = close de la última vela de 5m ya cerrada antes del signal_ts (sin lookahead)

Modelos de salida:
  R replay_SLTP   = solo SL/TP estructural + zombie_timeout(48h, solo si pnl<0) + tope 720h
  P prod_like_cap = SL/TP estructural + cierre SIEMPRE a las 48h (gane o pierda)  [aprox. de producción]
"""
import os, sys, json, sqlite3, statistics
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..", "..")
GT = os.path.join(ROOT, "scratch_caso3_gt.json")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")

CAP_MS = 48 * 3600 * 1000            # maxTradeDurationCandles 192 * 15m
HARD_CAP_MS = 720 * 3600 * 1000
BASE = 5 * 60 * 1000


def load_5m(conn, sym, a, b):
    return conn.execute(
        "SELECT open_time,open,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' "
        "AND open_time>=? AND open_time<=? ORDER BY open_time", (sym, a, b)).fetchall()


def sim_short(entry, sl, tp, kl, start_ms, exit_model):
    """kl = 5m candles desde la entrada. SHORT: tp<entry<sl. Devuelve (outcome, exit_px, dur_h)."""
    for ot, o, h, l, c in kl:
        if ot < start_ms:
            continue
        age = ot + BASE - start_ms
        # el motor chequea TP primero (hit_tp = l<=tp), después SL (h>=sl)
        if l <= tp:
            return "TP", tp, age / 3600000
        if h >= sl:
            return "SL", sl, age / 3600000
        pnl_pct = (entry - c) / entry
        if exit_model == "R":
            if age >= CAP_MS and pnl_pct < 0:
                return "ZOMBIE", c, age / 3600000
            if age >= HARD_CAP_MS:
                return "MAXDUR", c, age / 3600000
        else:  # P: cierre siempre a 48h
            if age >= CAP_MS:
                return "CAP48", c, age / 3600000
    # se acabaron las velas
    return "NODATA", kl[-1][4] if kl else entry, 0


def outcome_pnl(entry, exit_px):
    qty = 150.0 / entry
    gross = qty * (entry - exit_px)          # SHORT
    fee = (qty * entry + qty * exit_px) * 0.0004
    return gross - fee


def main():
    J = json.load(open(GT))
    conn = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)

    rows = []
    for j in J:
        sym = j["sym"]
        op = int(datetime.fromisoformat(j["open_utc"]).timestamp() * 1000)
        cl = int(datetime.fromisoformat(j["close_utc"]).timestamp() * 1000)
        entry_real, sl, tp, exit_real = j["entry"], j["sl"], j["tp"], j["exit_px"]
        # klines desde 3h antes de la señal hasta 800h después (cubre el 720h cap si hiciera falta, acotado)
        kl = load_5m(conn, sym, op - 3 * 3600000, op + 760 * 3600000)
        if len(kl) < 5:
            rows.append(dict(sym=sym, skip="no_5m"))
            continue
        # bar que contiene la señal (usamos open_utc como proxy del signal_ts; difieren ~seg)
        import bisect
        times = [k[0] for k in kl]
        bi = bisect.bisect_right(times, op) - 1          # vela que contiene op
        if bi < 1:
            rows.append(dict(sym=sym, skip="edge")); continue
        e_close = kl[bi][4]                               # A
        e_next_open = kl[bi + 1][1] if bi + 1 < len(kl) else e_close   # B
        e_prev_close = kl[bi - 1][4]                      # D
        # MAE/MFE reconstruido de 5m entre entrada y cierre real
        seg = [k for k in kl if op <= k[0] <= cl]
        mfe = max((entry_real - k[3]) / entry_real for k in seg) if seg else 0   # max favorable (low)
        mae = max((k[2] - entry_real) / entry_real for k in seg) if seg else 0   # max adverse (high)

        rec = dict(sym=sym, entry_real=entry_real, e_A=e_close, e_B=e_next_open, e_D=e_prev_close,
                   sl=sl, tp=tp, exit_real=exit_real, pnl_real=j["pnl"], dur_real=j["dur_h"],
                   real_outcome=j["real_outcome"],
                   d_A_pct=round((e_close - entry_real) / entry_real * 100, 3),
                   d_B_pct=round((e_next_open - entry_real) / entry_real * 100, 3),
                   d_D_pct=round((e_prev_close - entry_real) / entry_real * 100, 3),
                   mfe_pct=round(mfe * 100, 2), mae_pct=round(mae * 100, 2),
                   sl_dist_pct=round((sl - entry_real) / entry_real * 100, 2),
                   tp_dist_pct=round((tp - entry_real) / entry_real * 100, 2))
        start = kl[bi + 1][0] if bi + 1 < len(kl) else kl[bi][0]
        for em, epx in (("A", e_close), ("B", e_next_open), ("C", entry_real), ("D", e_prev_close)):
            for xm in ("R", "P"):
                # SL/TP se recalculan proporcionalmente al offset de entrada (estructura fija:
                # sl_buffer y tp son % sobre la entrada). Mantener sl_dist/tp_dist % de la entrada real.
                sld = (sl - entry_real) / entry_real
                tpd = (tp - entry_real) / entry_real
                sl_e = epx * (1 + sld)
                tp_e = epx * (1 + tpd)
                oc, xpx, dur = sim_short(epx, sl_e, tp_e, kl, start, xm)
                pnl = outcome_pnl(epx, xpx)
                rec[f"{em}{xm}_oc"] = oc
                rec[f"{em}{xm}_pnl"] = round(pnl, 2)
        # variante F: entrada real + SL/TP real EXACTOS (no reescalados) con salida R y P
        for xm in ("R", "P"):
            oc, xpx, dur = sim_short(entry_real, sl, tp, kl, start, xm)
            rec[f"REALEXACT_{xm}_oc"] = oc
            rec[f"REALEXACT_{xm}_pnl"] = round(outcome_pnl(entry_real, xpx), 2)
        rows.append(rec)

    valid = [r for r in rows if "skip" not in r]
    print(f"trades ground-truth: {len(J)} | simulados (con klines_5m): {len(valid)} | sin datos: {len(rows)-len(valid)}")
    json.dump(rows, open(os.path.join(ROOT, "scratch_caso3_diag.json"), "w"), indent=1, default=str)

    def agg(key_pnl, key_oc):
        pn = [r[key_pnl] for r in valid]
        pos = sum(p for p in pn if p > 0); neg = -sum(p for p in pn if p < 0)
        wr = 100 * sum(1 for p in pn if p > 0) / len(pn)
        import collections
        ocs = collections.Counter(r[key_oc] for r in valid)
        return dict(n=len(pn), net=round(sum(pn), 1), pf=round(pos / neg, 2) if neg else 99,
                    wr=round(wr), oc=dict(ocs))

    print("\n=== REAL (recalc de precios de trades.csv) ===")
    pn = [r["pnl_real"] for r in valid]
    pos = sum(p for p in pn if p > 0); neg = -sum(p for p in pn if p < 0)
    import collections
    print(f"  n={len(pn)} net={sum(pn):.1f} PF={pos/neg:.2f} WR_netpos={100*sum(1 for p in pn if p>0)/len(pn):.0f}%  "
          f"outcomes={dict(collections.Counter(r['real_outcome'] for r in valid))}")

    print("\n=== MATRIZ FACTORIAL: entrada × salida (WR_netpos / net / PF) ===")
    print(f"{'':12}{'salida R (replay)':>34}{'salida P (cap 48h siempre)':>36}")
    for em, lbl in (("A", "A candle_close"), ("B", "B next_open"), ("D", "D prev_close"), ("C", "C real_entry [LEAK]")):
        r = agg(f"{em}R_pnl", f"{em}R_oc"); p = agg(f"{em}P_pnl", f"{em}P_oc")
        print(f"{lbl:12} WR={r['wr']:>3}% net={r['net']:>7} PF={r['pf']:>5}   |   WR={p['wr']:>3}% net={p['net']:>7} PF={p['pf']:>5}")
    rr = agg("REALEXACT_R_pnl", "REALEXACT_R_oc"); rp = agg("REALEXACT_P_pnl", "REALEXACT_P_oc")
    print(f"{'REAL entry+SLTP exactos':12} WR={rr['wr']:>3}% net={rr['net']:>7} PF={rr['pf']:>5}   |   WR={rp['wr']:>3}% net={rp['net']:>7} PF={rp['pf']:>5}")

    print("\n=== outcomes por celda ===")
    for em in ("A", "B", "C", "D"):
        for xm in ("R", "P"):
            a = agg(f"{em}{xm}_pnl", f"{em}{xm}_oc")
            print(f"  {em}{xm}: {a['oc']}")

    print("\n=== los que REALMENTE fueron net-positivos (n=%d): qué hace el replay (celda A/R) ===" %
          sum(1 for r in valid if r["pnl_real"] > 0))
    flip = collections.Counter()
    for r in valid:
        real_w = r["pnl_real"] > 0
        rep_w = r["AR_pnl"] > 0
        flip[("REAL_WIN" if real_w else "REAL_LOSS", "rep_WIN" if rep_w else "rep_LOSS")] += 1
    for k, v in sorted(flip.items()):
        print(f"  {k[0]:9} -> {k[1]:9} : {v}")
    # de los reales ganadores que el replay pierde: por qué (outcome del replay)
    lost = [r for r in valid if r["pnl_real"] > 0 and r["AR_pnl"] <= 0]
    print(f"\n  de los {sum(1 for r in valid if r['pnl_real']>0)} reales ganadores, el replay (A/R) pierde {len(lost)}:")
    print(f"    outcome replay de esos: {dict(collections.Counter(r['AR_oc'] for r in lost))}")
    print(f"    MFE_pct (max favorable 5m) de esos: min {min(r['mfe_pct'] for r in lost):.1f} med {statistics.median([r['mfe_pct'] for r in lost]):.1f} max {max(r['mfe_pct'] for r in lost):.1f}")
    print(f"    MAE_pct (max adverso 5m) de esos:   min {min(r['mae_pct'] for r in lost):.1f} med {statistics.median([r['mae_pct'] for r in lost]):.1f} max {max(r['mae_pct'] for r in lost):.1f}  (SL a {statistics.median([r['sl_dist_pct'] for r in lost]):.1f}%)")

    print("\n=== offset de entrada A vs entrada real (SHORT: + = entrada peor) ===")
    for k in ("d_A_pct", "d_B_pct", "d_D_pct"):
        v = [r[k] for r in valid]
        print(f"  {k}: min {min(v):.2f}% med {statistics.median(v):.2f}% mean {statistics.mean(v):.2f}% max {max(v):.2f}%  "
              f"(|>0.5%| en {sum(1 for x in v if abs(x)>0.5)}/{len(v)})")

    print("\n=== SENSIBILIDAD: WR con entrada real desplazada -2,-1,0,+1,+2 ticks(=0.1% cada uno, aprox) ===")
    for off in (-0.002, -0.001, 0, 0.001, 0.002):
        w = 0; net = 0
        for r in valid:
            epx = r["entry_real"] * (1 + off)
            sld = (r["sl"] - r["entry_real"]) / r["entry_real"]; tpd = (r["tp"] - r["entry_real"]) / r["entry_real"]
            kl = load_5m(conn, r["sym"], int(datetime.fromisoformat([x for x in J if x['sym']==r['sym']][0]['open_utc']).timestamp()*1000) - 3*3600000,
                         int(datetime.fromisoformat([x for x in J if x['sym']==r['sym']][0]['open_utc']).timestamp()*1000) + 760*3600000)
            if len(kl) < 5:
                continue
            oc, xpx, _ = sim_short(epx, epx*(1+sld), epx*(1+tpd), kl, kl[1][0], "R")
            p = outcome_pnl(epx, xpx); net += p
            if p > 0:
                w += 1
        print(f"  offset {off*100:+.1f}%: WR={100*w/len(valid):.0f}% net={net:.1f}")


if __name__ == "__main__":
    main()
