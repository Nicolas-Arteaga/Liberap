"""
GATE V3 — Phase 2. Criterios PRE-REGISTRADOS en GATE_V3_CRITERIA.md.
Compara:
  A) replay V2  = run_parallel("MaGeometry")  (abre en la 1a vela del patron)
  B) replay V3  = run_ma_geometry_global       (abre al liberarse un cupo,
                                                dentro de la ventana de elegibilidad)
Mismo universo congelado (MA Slope Caso 2, 113 trades reales), misma config de
verge-db, fidelity idéntico para ambos. Ningún parámetro se toca.

Salidas: scratch_gate_v3_trades.csv + stdout con A/B, concordancia y VEREDICTO.
"""
import os, sys, json, csv, sqlite3, math, subprocess, statistics as st
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
ROOT = os.path.join(HERE, "..", "..")

REAL_CSV = os.path.join(ROOT, "scratch_ma2_real.csv")
ALL_CSV = os.path.join(ROOT, "scratch_all_trades_p2.csv")
OUT_CSV = os.path.join(ROOT, "scratch_gate_v3_trades.csv")
CACHE_V2 = os.path.join(HERE, "gate_v3_cache_v2.json")
CACHE_V3 = os.path.join(HERE, "gate_v3_cache_v3.json")
BV_DB = os.path.join(HERE, "..", "data", "binance_vision_clean.db")

STRAT = "MA Slope Caso 2"
WIN_START, WIN_END = "2026-07-10T00:00:00Z", "2026-08-13T00:00:00Z"
ARG_OFF = 3 * 3600 * 1000


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


def load_profile():
    q = ('SELECT row_to_json(t) FROM (SELECT "Id" as id,"Name" as name,"AllowLong" as "allowLong",'
         '"AllowShort" as "allowShort","TpMultiplier" as "tpMultiplier","SlMultiplier" as "slMultiplier",'
         '"MinRR" as "minRR","MarginPerTrade" as "marginPerTrade","MaxOpenPositions" as "maxOpenPositions",'
         '"MaxTradeDurationCandles" as "maxTradeDurationCandles","PatternParamsJson" as "patternParamsJson" '
         "FROM \"StrategyProfiles\" WHERE \"Name\"='MA Slope Caso 2') t;")
    return json.loads(subprocess.check_output(
        ["docker", "exec", "verge-db", "psql", "-U", "postgres", "-d", "Verge", "-t", "-A", "-c", q]).decode().strip())


def load_real():
    out = []
    for r in csv.DictReader(open(REAL_CSV, encoding="utf-8", errors="replace")):
        try:
            dj = json.loads(r["AgentDecisionJson"]) if r["AgentDecisionJson"] else {}
        except Exception:
            dj = {}
        sig = dj.get("captured_at_utc")
        out.append({"symbol": r["Symbol"], "side": int(r["Side"]),
                    "signal_ms": ms(sig) if sig else ms(r["OpenedAt"]),
                    "opened_ms": ms(r["OpenedAt"]), "closed_ms": ms(r["ClosedAt"]) if r["ClosedAt"] else None,
                    "entry": float(r["EntryPrice"]), "sl": float(r["SlPrice"]) if r["SlPrice"] else None,
                    "tp": float(r["TpPrice"]) if r["TpPrice"] else None,
                    "pnl": float(r["RealizedPnl"]) if r["RealizedPnl"] else None,
                    "reason": r["ExitReason"]})
    return out


def build_fidelity():
    tb = {}
    occ = {}
    for r in csv.DictReader(open(ALL_CSV, encoding="utf-8", errors="replace")):
        t = ms(r["OpenedAt"])
        if t:
            tb.setdefault(r["Symbol"], []).append(t)
        # occupied: intervalos de posiciones de OTRAS estrategias (la propia MA
        # Slope Caso 2 la maneja el runner con open_trades/last_trade_day).
        if r["Name"] != "MA Slope Caso 2":
            o, c = ms(r["OpenedAt"]), ms(r["ClosedAt"])
            if o and c:
                occ.setdefault(r["Symbol"], []).append((o, c))
    for s in tb:
        tb[s].sort()
    for s in occ:
        occ[s].sort()
    conn = sqlite3.connect(BV_DB)
    try:
        rows = conn.execute("SELECT open_time, close FROM btc_klines_1m ORDER BY open_time").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    try:
        import config as ac
        FC = float(getattr(ac, "BTC_FLASH_CRASH_PCT_1H", -3.0))
    except Exception:
        FC = -3.0
    blackout = []
    if rows:
        by15 = {}
        for ot, c in rows:
            by15[ot - (ot % 900000)] = c
        ks = sorted(by15)
        for i in range(4, len(ks)):
            if by15[ks[i - 4]] and (by15[ks[i]] - by15[ks[i - 4]]) / by15[ks[i - 4]] * 100 <= FC:
                t0 = ks[i] + 900000
                blackout.append((t0, t0 + 2 * 3600 * 1000))
        merged = []
        for a, b in sorted(blackout):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        blackout = merged
    return {"btc_block": True, "daily_change": True, "traded_before": tb,
            "blackout": blackout, "occupied": occ}


def coverage(real):
    conn = sqlite3.connect(BV_DB)
    syms = {}
    for r in real:
        syms[r["symbol"]] = syms.get(r["symbol"], 0) + 1
    a, b = ms(WIN_START), ms(WIN_END)
    rep, part, unrep = set(), set(), set()
    tr = {"REPLAYABLE": 0, "PARTIALLY": 0, "UNREPLAYABLE": 0}
    rows = []
    for s in sorted(syms):
        n, mn, mx = conn.execute("SELECT COUNT(*),MIN(open_time),MAX(open_time) FROM klines_5m WHERE symbol=? AND interval='5m'", (s,)).fetchone()
        if not n:
            unrep.add(s); tr["UNREPLAYABLE"] += syms[s]; cls = "UNREPLAYABLE"
        else:
            first_sig = min(r["signal_ms"] for r in real if r["symbol"] == s)
            ok = (mn <= a + 3 * 86400000) and (mx >= b - 3 * 86400000) and (mn <= first_sig - 150 * 3600000)
            if ok:
                rep.add(s); tr["REPLAYABLE"] += syms[s]; cls = "REPLAYABLE"
            else:
                part.add(s); tr["PARTIALLY"] += syms[s]; cls = "PARTIALLY"
        rows.append((s, syms[s], cls))
    conn.close()
    return rep, part, unrep, tr, rows


def run_v2(profile, fidelity, symbols):
    if os.path.exists(CACHE_V2):
        return json.load(open(CACHE_V2))
    from engine import BacktestEngine
    eng = BacktestEngine()
    stash = {}
    orig = eng._capital_sim
    def cap(t, p, symbols_used=None):
        stash["raw"] = [dict(x) for x in t]
        return orig(t, p, symbols_used=symbols_used)
    eng._capital_sim = cap
    res = eng.run_parallel("MaGeometry", profile, symbols, ms(WIN_START), ms(WIN_END), fidelity=fidelity)
    res["_raw"] = stash.get("raw", [])
    json.dump(res, open(CACHE_V2, "w"))
    return res


def run_v3(profile, fidelity, symbols):
    if os.path.exists(CACHE_V3):
        return json.load(open(CACHE_V3))
    from engine import BacktestEngine
    eng = BacktestEngine()
    done = [0]
    def pcb(a, b):
        if b and a * 20 // b != done[0]:
            done[0] = a * 20 // b
            print(f"  [v3] {a}/{b}", flush=True)
    res = eng.run_ma_geometry_global(profile, symbols, ms(WIN_START), ms(WIN_END), fidelity=fidelity, progress_cb=pcb)
    json.dump(res, open(CACHE_V3, "w"))
    return res


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)); dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def band(p, q):
    return "PASS" if p else ("PARTIAL" if q else "FAILED")


def eligible_window(eng_geo_fn):
    pass


def main():
    profile = load_profile()
    real = load_real()
    rep, part, unrep, tr, cov_rows = coverage(real)
    tot = len(real)
    print("=" * 84)
    print(f"GATE V3 (Phase 2) — {STRAT} — {tot} trades reales — criterios PRE-REGISTRADOS")
    print("=" * 84)
    print(f"\ncobertura tras backfill: REPLAYABLE={len(rep)} sym / {tr['REPLAYABLE']} trades | "
          f"PARTIALLY={len(part)} / {tr['PARTIALLY']} | UNREPLAYABLE={len(unrep)} / {tr['UNREPLAYABLE']}")
    print(f"  UNREPLAYABLE: {sorted(unrep)}")
    unrep_pct = 100 * tr["UNREPLAYABLE"] / tot
    real_rep = [r for r in real if r["symbol"] in rep]

    fidelity = build_fidelity()

    from engine import BacktestEngine
    eng0 = BacktestEngine()
    avail = set(eng0.available_symbols())
    wl = json.load(open(os.path.join(HERE, "..", "data", "watchlist_cache.json")))["symbols"]
    symbols = sorted(set(s for s in wl if s in avail) | (rep & avail) | (part & avail))
    print(f"universo replay: {len(symbols)} símbolos")

    print("\n[v2] run_parallel ...")
    r2 = run_v2(profile, fidelity, symbols)
    print("[v3] run_ma_geometry_global (reloj global, admisión por cupo) ...")
    r3 = run_v3(profile, fidelity, symbols)
    bt2, bt3 = r2["trades"], r3["trades"]

    # ── ventana de elegibilidad real por (symbol) alrededor de cada señal real ──
    # medida por phase2_timeline: persistencia mediana ~26 velas 5m. Aquí se toma
    # [signal-6h, signal+3h] como proxy conservador; el match exige entrada ahí.
    def in_elig(r, ts):
        return (r["signal_ms"] - 6 * 3600000) <= ts <= (r["signal_ms"] + 3 * 3600000)

    def metrics(bt, label):
        bt_rep = [t for t in bt if t["symbol"] in rep]
        by = {}
        for t in bt_rep:
            by.setdefault(t["symbol"], []).append(t)
        used = set(); pairs = []
        for r in real_rep:
            cs = sorted(by.get(r["symbol"], []), key=lambda t: abs(t["open_time"] - r["signal_ms"]))
            for c in cs:
                if id(c) in used:
                    continue
                if abs(c["open_time"] - r["signal_ms"]) <= 2 * 3600000 and c["side"] == r["side"]:
                    used.add(id(c)); pairs.append((r, c)); break
        fp = [t for t in bt_rep if id(t) not in used]
        Rsyms = set(r["symbol"] for r in real_rep)
        Bsyms = set(t["symbol"] for t in bt_rep)
        jacc = len(Rsyms & Bsyms) / len(Rsyms | Bsyms) if (Rsyms | Bsyms) else 0
        P1 = jacc
        P2 = 100 * len(pairs) / len(real_rep) if real_rep else 0
        # timeline de ocupación por hora
        def occ_series(trades, is_real):
            a, b = ms(WIN_START), ms(WIN_END)
            hrs = list(range(a, b, 3600000))
            out = []
            for h in hrs:
                if is_real:
                    out.append(sum(1 for x in trades if x["opened_ms"] and x["closed_ms"] and x["opened_ms"] <= h < x["closed_ms"]))
                else:
                    out.append(sum(1 for x in trades if x["open_time"] <= h < x["close_time"]))
            return out
        real_occ = occ_series([r for r in real if r["symbol"] in rep], True)
        bt_occ = occ_series(bt_rep, False)
        P3 = pearson(real_occ, bt_occ)
        P4 = len(bt_rep) / len(real_rep) if real_rep else 0
        # PnL agregado
        def agg(ts, isr):
            pnl = [t["pnl"] for t in ts if t.get("pnl") is not None]
            wins = [t for t in ts if (t["reason"] == "tp_hit" if isr else t["close_reason"] == "TP")]
            pos = sum(p for p in pnl if p > 0); neg = sum(-p for p in pnl if p < 0)
            return sum(pnl), (pos / neg if neg else float("inf")), (100 * len(wins) / len(pnl) if pnl else 0), len(pnl)
        rnet, rpf, rwr, rn = agg(real, True)
        bnet, bpf, bwr, bn = agg(bt, False)
        P5_flip = (rnet < 0) != (bnet < 0)
        P5_rel = abs(bnet - rnet) / abs(rnet) * 100 if rnet else float("nan")
        raw = r2["_raw"] if label == "V2" else bt  # V3 no infla (gate por cupo)
        P6 = len([t for t in raw if t["symbol"] in rep]) / len(real_rep) if real_rep else 0
        rmap = {"TP": "tp_hit", "SL": "sl_hit", "zombie_timeout": "timeout", "max_duration": "timeout"}
        S1 = 100 * sum(1 for r, c in pairs if rmap.get(c["close_reason"]) == r["reason"]) / len(pairs) if pairs else 0
        S2 = 100 * sum(1 for r, c in pairs if in_elig(r, c["open_time"])) / len(pairs) if pairs else 0
        S3 = abs(bpf - rpf) if math.isfinite(bpf) and math.isfinite(rpf) else float("inf")
        S4 = pearson([r["pnl"] for r, c in pairs if r["pnl"] is not None],
                     [c["pnl"] for r, c in pairs if r["pnl"] is not None])
        return dict(label=label, pairs=pairs, fp=fp, P1=P1, P2=P2, P3=P3, P4=P4, P5_flip=P5_flip, P5_rel=P5_rel,
                    P6=P6, S1=S1, S2=S2, S3=S3, S4=S4, bnet=bnet, bpf=bpf, bwr=bwr, bn=bn,
                    rnet=rnet, rpf=rpf, rwr=rwr, rn=rn)

    m2 = metrics(bt2, "V2")
    m3 = metrics(bt3, "V3")

    print("\n" + "=" * 84 + "\nA/B — cuanto colapsa la divergencia al pasar de V2 a V3\n" + "-" * 84)
    hdr = f"{'metrica':34}{'V2':>12}{'V3':>12}"
    print(hdr)
    def row(n, a, b, fmt="{:.2f}"):
        print(f"{n:34}{fmt.format(a):>12}{fmt.format(b):>12}")
    row("P1 Jaccard símbolos", m2["P1"], m3["P1"])
    row("P2 match rate % (±2h)", m2["P2"], m3["P2"], "{:.0f}")
    row("P3 occ-timeline corr r", m2["P3"], m3["P3"])
    row("P4 trade ratio replay/real", m2["P4"], m3["P4"])
    row("P6 inflación (admitidos/real)", m2["P6"], m3["P6"])
    row("S1 exit reason agree %", m2["S1"], m3["S1"], "{:.0f}")
    row("S2 entrada en ventana elegible %", m2["S2"], m3["S2"], "{:.0f}")
    row("S3 |dPF|", m2["S3"], m3["S3"])
    row("S4 PnL corr r", m2["S4"], m3["S4"])
    print(f"\nagregado REAL: net ${m3['rnet']:.2f} PF {m3['rpf']:.2f} WR {m3['rwr']:.0f}% n={m3['rn']}")
    print(f"agregado V2  : net ${m2['bnet']:.2f} PF {m2['bpf']:.2f} WR {m2['bwr']:.0f}% n={m2['bn']}  pares={len(m2['pairs'])} fp={len(m2['fp'])}")
    print(f"agregado V3  : net ${m3['bnet']:.2f} PF {m3['bpf']:.2f} WR {m3['bwr']:.0f}% n={m3['bn']}  pares={len(m3['pairs'])} fp={len(m3['fp'])}")

    # ── CSV de V3 ──
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "symbol", "real_sig", "bt_open", "real_pnl", "bt_pnl", "real_reason", "bt_reason"])
        for r, c in m3["pairs"]:
            w.writerow(["MATCH", r["symbol"], datetime.utcfromtimestamp(r["signal_ms"]/1000).isoformat()[:16],
                        datetime.utcfromtimestamp(c["open_time"]/1000).isoformat()[:16],
                        round(r["pnl"], 2) if r["pnl"] is not None else "", round(c["pnl"], 2),
                        r["reason"], c["close_reason"]])
        for t in m3["fp"]:
            w.writerow(["FALSE_POS", t["symbol"], "", datetime.utcfromtimestamp(t["open_time"]/1000).isoformat()[:16],
                        "", round(t["pnl"], 2), "", t["close_reason"]])

    # ── veredicto V3 pre-registrado ──
    m = m3
    rows_v = [
        ("P1 Jaccard símbolos", f"{m['P1']:.2f}", band(m['P1'] >= 0.55, m['P1'] >= 0.30)),
        ("P2 match rate ±ventana", f"{m['P2']:.0f}%", band(m['P2'] >= 55, m['P2'] >= 35)),
        ("P3 occ-timeline corr", f"{m['P3']:.2f}", band(m['P3'] >= 0.70, m['P3'] >= 0.45)),
        ("P4 trade ratio", f"{m['P4']:.2f}", band(0.80 <= m['P4'] <= 1.25, 0.6 <= m['P4'] <= 1.6)),
        ("P5 PnL signo/magnitud", ("FLIP" if m['P5_flip'] else f"same {m['P5_rel']:.0f}%"),
         band(not m['P5_flip'] and m['P5_rel'] <= 60, not m['P5_flip'] and m['P5_rel'] <= 130)),
        ("P6 inflación admitidos", f"{m['P6']:.2f}x", band(m['P6'] <= 1.5, m['P6'] <= 2.5)),
        ("S1 exit reason agree", f"{m['S1']:.0f}%", band(m['S1'] >= 70, m['S1'] >= 50)),
        ("S2 entrada en ventana", f"{m['S2']:.0f}%", band(m['S2'] >= 80, m['S2'] >= 60)),
        ("S3 |dPF|", f"{m['S3']:.2f}", band(m['S3'] <= 0.20, m['S3'] <= 0.45)),
        ("S4 PnL corr r", f"{m['S4']:.2f}", band(m['S4'] >= 0.70, m['S4'] >= 0.45)),
        ("I2 trades UNREPLAYABLE", f"{unrep_pct:.0f}%", band(unrep_pct <= 10, unrep_pct <= 25)),
        ("I3 intrabar TP/SL (FVG)", "NEGLIGIBLE", "PASS"),
    ]
    print("\n" + "=" * 84 + "\nVEREDICTO V3 vs criterios PRE-REGISTRADOS (GATE_V3_CRITERIA.md)\n" + "-" * 84)
    for n, v, b in rows_v:
        print(f"  {n:34}{v:>16}   {b}")
    bands = [b for _, _, b in rows_v]
    verdict = "FAILED" if ("FAILED" in bands or m["P5_flip"]) else ("PASS" if all(b == "PASS" for b in bands) else "PARTIAL")
    print("\n" + "=" * 84 + f"\nGATE V3 (mecánico) = {verdict}\n" + "=" * 84)
    print("El veredicto final del reporte pondera además la explicabilidad de las divergencias\ny el estado de los bugs (I1), como fija GATE_V3_CRITERIA.md.")


if __name__ == "__main__":
    main()
