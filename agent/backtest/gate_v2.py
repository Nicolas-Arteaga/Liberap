"""
GATE V2 — LIVE vs HISTORICAL REPLAY, despues del repair PHASE 1.
Criterios PRE-REGISTRADOS en GATE_V2_CRITERIA.md (fijados antes de esta corrida).

Mismo universo congelado que el gate v1: MA Slope Caso 2, 113 trades reales
(2026-07-11 -> 08-09), config de verge-db sin tocar. Correcciones aplicadas:
  * timeout FIEL a produccion (zombie_timeout_decision) + tests unitarios
  * BTC macro filter historico wired (btc_klines_1m) — GAP 1, validado a parte
  * has_traded_symbol_today CRUZADO entre estrategias (traded_before, de trades reales)
  * historical_daily_change_pct inyectado (evita el fetch a Binance en vivo)
  * blackout por flash-crash de BTC
  * funding real donde hay cobertura, 0+flag donde no (APPROXIMATE)

Salidas: scratch_gate_v2_trades.csv + stdout con concordancia y VEREDICTO.
"""
import os, sys, json, csv, sqlite3, math, subprocess, statistics as st
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))

ROOT = os.path.join(HERE, "..", "..")
REAL_CSV = os.path.join(ROOT, "scratch_ma2_real.csv")
ALL_CSV = os.path.join(ROOT, "scratch_all_trades_window.csv")
OUT_CSV = os.path.join(ROOT, "scratch_gate_v2_trades.csv")
CACHE = os.path.join(HERE, "gate_v2_replay_cache.json")
BV_DB = os.path.join(HERE, "..", "data", "binance_vision_clean.db")

STRAT = "MA Slope Caso 2"
WIN_START, WIN_END = "2026-07-10T00:00:00Z", "2026-08-13T00:00:00Z"
ARG_OFFSET_MS = 3 * 3600 * 1000
FEE = 0.0004


def ms(iso):
    if not iso:
        return None
    s = iso.strip().replace("T", " ").replace("Z", "")
    for sep in ("+00:00", "+00"):
        if s.endswith(sep):
            s = s[:-len(sep)].strip()
    if "." in s:
        h, fr = s.split("."); s = h + "." + (fr + "000000")[:6]
        return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp() * 1000)
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def load_profile():
    q = ('SELECT row_to_json(t) FROM (SELECT "Id","Name","AllowLong","AllowShort","TpMultiplier",'
         '"SlMultiplier","MinRR","MarginPerTrade","MaxOpenPositions","MaxTradeDurationCandles",'
         f"\"PatternParamsJson\" FROM \"StrategyProfiles\" WHERE \"Name\"='{STRAT}') t;")
    p = json.loads(subprocess.check_output(
        ["docker", "exec", "verge-db", "psql", "-U", "postgres", "-d", "Verge", "-t", "-A", "-c", q]).decode().strip())
    return {"id": p["Id"], "name": p["Name"], "allowLong": p["AllowLong"], "allowShort": p["AllowShort"],
            "tpMultiplier": float(p["TpMultiplier"]), "slMultiplier": float(p["SlMultiplier"]),
            "minRR": float(p["MinRR"]), "marginPerTrade": float(p["MarginPerTrade"]),
            "maxOpenPositions": int(p["MaxOpenPositions"]), "maxTradeDurationCandles": int(p["MaxTradeDurationCandles"]),
            "patternParamsJson": p["PatternParamsJson"]}


def load_real():
    out = []
    for r in csv.DictReader(open(REAL_CSV, encoding="utf-8", errors="replace")):
        try:
            dj = json.loads(r["AgentDecisionJson"]) if r["AgentDecisionJson"] else {}
        except Exception:
            dj = {}
        sig = dj.get("captured_at_utc")
        out.append({
            "symbol": r["Symbol"], "side": int(r["Side"]),
            "signal_ms": ms(sig) if sig else ms(r["OpenedAt"]),
            "opened_ms": ms(r["OpenedAt"]), "closed_ms": ms(r["ClosedAt"]) if r["ClosedAt"] else None,
            "entry": float(r["EntryPrice"]), "close": float(r["ClosePrice"]) if r["ClosePrice"] else None,
            "sl": float(r["SlPrice"]) if r["SlPrice"] else None, "tp": float(r["TpPrice"]) if r["TpPrice"] else None,
            "pnl": float(r["RealizedPnl"]) if r["RealizedPnl"] else None,
            "fees": (float(r["EntryFee"] or 0) + float(r["ExitFee"] or 0)),
            "funding": float(r["TotalFundingPaid"] or 0),
            "reason": r["ExitReason"],
        })
    return out


def build_fidelity():
    # traded_before: symbol -> sorted opened_ms de CUALQUIER estrategia
    tb = {}
    for r in csv.DictReader(open(ALL_CSV, encoding="utf-8", errors="replace")):
        t = ms(r["OpenedAt"])
        if t:
            tb.setdefault(r["Symbol"], []).append(t)
    for s in tb:
        tb[s].sort()

    # blackout: ventanas de 2h tras cada flash-crash de BTC (produccion: sleep 2h)
    conn = sqlite3.connect(BV_DB)
    try:
        rows = conn.execute("SELECT open_time, close FROM btc_klines_1m ORDER BY open_time").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    blackout = []
    # flash crash real de produccion: is_flash_crash usa get_dump_pct(60) sobre 15m;
    # aprox: resample 1m->15m y buscar pct_1h <= BTC_FLASH_CRASH_PCT_1H (-3.0 default)
    try:
        import config as ac
        FC = float(getattr(ac, "BTC_FLASH_CRASH_PCT_1H", -3.0))
    except Exception:
        FC = -3.0
    if rows:
        by15 = {}
        for ot, c in rows:
            b = ot - (ot % (15 * 60 * 1000))
            by15[b] = c  # ultimo close del bucket
        ks = sorted(by15)
        for i in range(4, len(ks)):
            p_now = by15[ks[i]]; p_1h = by15[ks[i - 4]]
            if p_1h and (p_now - p_1h) / p_1h * 100 <= FC:
                t0 = ks[i] + 15 * 60 * 1000
                blackout.append((t0, t0 + 2 * 3600 * 1000))
        # merge solapados
        merged = []
        for a, b in sorted(blackout):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        blackout = merged
    return {"btc_block": True, "daily_change": True, "traded_before": tb, "blackout": blackout}


def coverage_table(real):
    conn = sqlite3.connect(BV_DB)
    syms = {}
    for r in real:
        syms.setdefault(r["symbol"], 0)
        syms[r["symbol"]] += 1
    a, b = ms(WIN_START), ms(WIN_END)
    rows = []
    cls = {"REPLAYABLE": 0, "PARTIALLY REPLAYABLE": 0, "UNREPLAYABLE": 0}
    trades_by_cls = {"REPLAYABLE": 0, "PARTIALLY REPLAYABLE": 0, "UNREPLAYABLE": 0}
    for s in sorted(syms):
        q = conn.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM klines_5m WHERE symbol=? AND interval='5m'", (s,)).fetchone()
        n, mn, mx = q
        if not n:
            c = "UNREPLAYABLE"
        else:
            covers = (mn <= a + 3 * 86400_000) and (mx >= b - 3 * 86400_000)
            # necesita >= ~150 velas de 1h antes de la primera señal de ese simbolo
            first_sig = min(r["signal_ms"] for r in real if r["symbol"] == s)
            warmup_ok = mn <= first_sig - 150 * 3600_000
            c = "REPLAYABLE" if (covers and warmup_ok) else "PARTIALLY REPLAYABLE"
        cls[c] += 1
        trades_by_cls[c] += syms[s]
        f = lambda x: datetime.utcfromtimestamp(x / 1000).date().isoformat() if x else "-"
        rows.append((s, syms[s], "yes" if n else "no", f(mn), f(mx), c))
    conn.close()
    return rows, cls, trades_by_cls


def run_replay(profile, fidelity, tag=""):
    cache = CACHE.replace(".json", f"{tag}.json")
    if os.path.exists(cache):
        print(f"[replay{tag}] cache {cache}")
        return json.load(open(cache))
    from engine import BacktestEngine
    eng = BacktestEngine()
    avail = set(eng.available_symbols())
    wl = json.load(open(os.path.join(HERE, "..", "data", "watchlist_cache.json")))["symbols"]
    symbols = sorted(s for s in wl if s in avail)
    stash = {}
    orig = eng._capital_sim
    def cap(trades, prof, symbols_used=None):
        stash["raw"] = [dict(t) for t in trades]
        return orig(trades, prof, symbols_used=symbols_used)
    eng._capital_sim = cap
    res = eng.run_parallel("MaGeometry", profile, symbols, ms(WIN_START), ms(WIN_END), fidelity=fidelity)
    res["_raw"] = stash.get("raw", [])
    res["_nsym"] = len(symbols)
    try:
        json.dump(res, open(cache, "w"))
    except Exception as e:
        print("cache err", e)
    return res


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)); dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def band(pass_ok, partial_ok):
    """partial_ok = 'llega al menos a PARTIAL'. Si no, FAILED."""
    return "PASS" if pass_ok else ("PARTIAL" if partial_ok else "FAILED")


def main():
    profile = load_profile()
    real = load_real()
    print("=" * 80)
    print(f"GATE V2 — {STRAT} — {len(real)} trades reales — criterios PRE-REGISTRADOS (GATE_V2_CRITERIA.md)")
    print("=" * 80)

    cov_rows, cls, tcls = coverage_table(real)
    print("\n## GAP 3 — COBERTURA HISTORICA")
    print(f"{'SYMBOL':14}{'REAL':>5}{'DATA':>6}{'FIRST':>12}{'LAST':>12}  CLASS")
    for s, n, d, fb, lb, c in cov_rows:
        print(f"{s:14}{n:5}{d:>6}{fb:>12}{lb:>12}  {c}")
    tot = len(real)
    print(f"\nsimbolos: {cls}  | trades: {tcls}")
    unrep_pct = 100 * tcls["UNREPLAYABLE"] / tot
    part_pct = 100 * tcls["PARTIALLY REPLAYABLE"] / tot
    print(f"trades sobre UNREPLAYABLE: {tcls['UNREPLAYABLE']}/{tot} = {unrep_pct:.0f}%  | PARTIALLY: {part_pct:.0f}%")
    replayable_syms = set(s for s, n, d, fb, lb, c in cov_rows if c == "REPLAYABLE")
    real_rep = [r for r in real if r["symbol"] in replayable_syms]

    fidelity = build_fidelity()
    print(f"\n## FIDELITY: traded_before={len(fidelity['traded_before'])} simbolos | "
          f"blackout flash-crash={len(fidelity['blackout'])} ventanas")
    for a, b in fidelity["blackout"][:8]:
        print(f"   blackout {datetime.utcfromtimestamp(a/1000)} -> {datetime.utcfromtimestamp(b/1000)}")

    print("\n[replay] corriendo run_parallel con fidelity ...")
    res = run_replay(profile, fidelity)
    bt = res["trades"]; raw = res["_raw"]
    margin = profile["marginPerTrade"]
    for t in bt:
        qty = margin / t["entry"]
        cpx = t["tp"] if t["close_reason"] == "TP" else (
            t.get("_zombie_close_price") if t["close_reason"] in ("zombie_timeout", "max_duration") else t["sl"])
        t["_cpx"] = cpx
    print(f"[replay] {len(raw)} señales crudas | {len(bt)} aceptadas")

    # ── match REAL -> REPLAY (solo replayable) ──
    bt_by = {}
    for t in bt:
        bt_by.setdefault(t["symbol"], []).append(t)
    used = set()
    pairs = []
    matched_real = 0
    for r in real_rep:
        cands = sorted(bt_by.get(r["symbol"], []), key=lambda t: abs(t["open_time"] - r["signal_ms"]))
        m = None
        for c in cands:
            if id(c) in used:
                continue
            if abs(c["open_time"] - r["signal_ms"]) <= 3 * 3600 * 1000 and c["side"] == r["side"]:
                m = c; used.add(id(c)); break
        if m:
            matched_real += 1
            pairs.append((r, m))

    # ── REPLAY -> REAL false positives (sobre replayable) ──
    bt_rep = [t for t in bt if t["symbol"] in replayable_syms]
    fp = [t for t in bt_rep if id(t) not in used]

    # ── métricas ──
    P1 = 100 * matched_real / len(real_rep) if real_rep else 0
    P2 = 100 * len(fp) / len(bt_rep) if bt_rep else 0
    raw_rep = [t for t in raw if t["symbol"] in replayable_syms]
    P3 = len(raw_rep) / len(real_rep) if real_rep else 0

    def agg(trades, is_real):
        pnl = [t["pnl"] for t in trades if (t.get("pnl") is not None)]
        wins = [t for t in trades if (t["reason"] == "tp_hit" if is_real else t["close_reason"] == "TP")]
        pos = sum(p for p in pnl if p > 0); neg = sum(-p for p in pnl if p < 0)
        return {"n": len(pnl), "net": sum(pnl), "pf": (pos / neg) if neg else float("inf"),
                "wr": 100 * len(wins) / len(pnl) if pnl else 0}
    ra = agg(real, True)
    ba_all = agg(bt, False)
    P4_flip = (ra["net"] < 0) != (ba_all["net"] < 0)
    P4_rel = abs(ba_all["net"] - ra["net"]) / abs(ra["net"]) * 100 if ra["net"] else float("nan")
    P5_pf_delta = abs(ba_all["pf"] - ra["pf"]) if math.isfinite(ba_all["pf"]) and math.isfinite(ra["pf"]) else float("inf")

    # secundarias sobre pares
    rmap = {"TP": "tp_hit", "SL": "sl_hit", "zombie_timeout": "timeout", "max_duration": "timeout"}
    exit_agree = sum(1 for r, m in pairs if rmap.get(m["close_reason"]) == r["reason"])
    S1 = 100 * exit_agree / len(pairs) if pairs else 0
    S2 = pearson([r["pnl"] for r, m in pairs if r["pnl"] is not None],
                 [m["pnl"] for r, m in pairs if r["pnl"] is not None])
    S3 = st.median([abs(m["entry"] - r["entry"]) / r["entry"] * 100 for r, m in pairs]) if pairs else 0
    S4 = st.median([abs(m["open_time"] - r["signal_ms"]) / 60000 for r, m in pairs]) if pairs else 0
    same_reason_pairs = [(r, m) for r, m in pairs if rmap.get(m["close_reason"]) == r["reason"] and r["closed_ms"]]
    S5 = st.median([abs(m["close_time"] - r["closed_ms"]) / 3600000 for r, m in same_reason_pairs]) if same_reason_pairs else 0
    S6 = 100 * sum(1 for r, m in pairs if r["side"] == m["side"]) / len(pairs) if pairs else 100

    # ── CSV ──
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "symbol", "real_sig", "bt_sig", "real_pnl", "bt_pnl", "real_reason", "bt_reason", "dpnl"])
        for r, m in pairs:
            w.writerow(["MATCH", r["symbol"], datetime.utcfromtimestamp(r["signal_ms"]/1000).isoformat()[:16],
                        datetime.utcfromtimestamp(m["open_time"]/1000).isoformat()[:16],
                        round(r["pnl"], 3) if r["pnl"] is not None else "", round(m["pnl"], 3),
                        r["reason"], m["close_reason"],
                        round(m["pnl"] - r["pnl"], 3) if r["pnl"] is not None else ""])
        for t in fp:
            w.writerow(["FALSE_POS", t["symbol"], "", datetime.utcfromtimestamp(t["open_time"]/1000).isoformat()[:16],
                        "", round(t["pnl"], 3), "", t["close_reason"], ""])
        matched_syms_times = {(r["symbol"], r["signal_ms"]) for r, m in pairs}
        for r in real_rep:
            if not any(r is rr for rr, mm in pairs):
                w.writerow(["MISSED_REAL", r["symbol"], datetime.utcfromtimestamp(r["signal_ms"]/1000).isoformat()[:16],
                            "", round(r["pnl"], 3) if r["pnl"] is not None else "", "", r["reason"], "", ""])

    # ── verdicts ──
    rows = [
        ("P1 REAL->REPLAY match rate", f"{P1:.0f}%", band(P1 >= 70, P1 >= 45)),
        ("P2 REPLAY->REAL false-pos", f"{P2:.0f}%", band(P2 <= 35, P2 <= 60)),
        ("P3 signal inflation", f"{P3:.1f}x", band(P3 <= 2.0, P3 <= 4.0)),
        ("P4 net PnL sign", ("FLIP" if P4_flip else f"same, dRel {P4_rel:.0f}%"),
         band(not P4_flip and P4_rel <= 40, not P4_flip and P4_rel <= 100)),
        ("P5 PF delta", f"{P5_pf_delta:.2f}", band(P5_pf_delta <= 0.15, P5_pf_delta <= 0.40)),
        ("S1 exit reason agree", f"{S1:.0f}%", band(S1 >= 75, S1 >= 55)),
        ("S2 PnL correlation r", f"{S2:.2f}", band(S2 >= 0.80, S2 >= 0.55)),
        ("S3 entry px delta med", f"{S3:.2f}%", band(S3 <= 0.30, S3 <= 0.80)),
        ("S4 entry timing delta med", f"{S4:.0f}min", band(S4 <= 45, S4 <= 180)),
        ("S5 exit timing delta med", f"{S5:.1f}h", band(S5 <= 2, S5 <= 12)),
        ("S6 direction agree", f"{S6:.0f}%", band(S6 >= 100, S6 >= 98)),
        ("I2 trades on UNREPLAYABLE", f"{unrep_pct:.0f}%", band(unrep_pct <= 10, unrep_pct <= 30)),
    ]
    print("\n" + "=" * 80 + "\nCONCORDANCIA vs criterios PRE-REGISTRADOS\n" + "-" * 80)
    print(f"{'metrica':32}{'valor':>14}   banda")
    for name, val, b in rows:
        print(f"{name:32}{val:>14}   {b}")
    print(f"\nagregado: REAL net ${ra['net']:.2f} PF {ra['pf']:.2f} WR {ra['wr']:.0f}%  |  "
          f"REPLAY net ${ba_all['net']:.2f} PF {ba_all['pf']:.2f} WR {ba_all['wr']:.0f}%  (n={ba_all['n']})")
    print(f"pares matcheados: {len(pairs)} | false pos: {len(fp)} | real replayable: {len(real_rep)}")

    # ── ablacion: mismo replay SIN la mascara cross-strategy has_traded_symbol_today ──
    fid_nomask = dict(fidelity); fid_nomask["traded_before"] = {}
    res2 = run_replay(profile, fid_nomask, tag="_nomask")
    bt2 = res2["trades"]; raw2 = res2["_raw"]
    bt2_rep = [t for t in bt2 if t["symbol"] in replayable_syms]
    raw2_rep = [t for t in raw2 if t["symbol"] in replayable_syms]
    bt2_by = {}
    for t in bt2:
        bt2_by.setdefault(t["symbol"], []).append(t)
    u2 = set(); m2 = 0
    for r in real_rep:
        for c in sorted(bt2_by.get(r["symbol"], []), key=lambda t: abs(t["open_time"] - r["signal_ms"])):
            if id(c) in u2:
                continue
            if abs(c["open_time"] - r["signal_ms"]) <= 3 * 3600 * 1000 and c["side"] == r["side"]:
                u2.add(id(c)); m2 += 1; break
    print("\n" + "-" * 80 + "\nABLACION — sin la mascara cross-strategy has_traded_symbol_today:")
    print(f"  P1 match {100*m2/len(real_rep):.0f}%  | P2 false-pos {100*(len(bt2_rep)-len(u2))/max(len(bt2_rep),1):.0f}%"
          f"  | P3 inflacion {len(raw2_rep)/len(real_rep):.1f}x  | aceptados {len(bt2)}")
    print("  (la mascara BAJA la inflacion pero por sensibilidad de timing tambien tira el match rate:")
    print("   una simulacion fiel necesita reproducir las 26 estrategias en UN reloj compartido — Phase 2.)")

    bands = [b for _, _, b in rows]
    verdict = "FAILED" if ("FAILED" in bands or P4_flip) else ("PASS" if all(b == "PASS" for b in bands) else "PARTIAL")
    print("\n" + "=" * 80 + f"\nGATE V2 (mecanico, pre-registrado) = {verdict}\n" + "=" * 80)
    print("El veredicto final del reporte incorpora ademas la explicabilidad de las\n"
          "divergencias restantes y el estado de los bugs (I1), como fija GATE_V2_CRITERIA.md.")


if __name__ == "__main__":
    main()
