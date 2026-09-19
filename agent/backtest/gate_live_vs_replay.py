"""
GATE DE CONFIABILIDAD DEL BACKTEST — LIVE vs HISTORICAL REPLAY RECONCILIATION
(pedido del usuario 2026-09-05). NO es research de alpha. Auditoria pura:
¿el motor historico (agent/backtest/engine.py) reproduce razonablemente lo que
paso en produccion real?

Universo CONGELADO (elegido por calidad de evidencia, sin cherry-picking de
resultado):
  estrategia : MA Slope Caso 2  (StrategyType=MaGeometry, direct-injection,
               SL/TP estructural reconstruible, Long-only, leverage 1x)
  por que    : 87 trades reales CERRADOS, ciclo de vida 100% dentro del dataset
               historico (2026-07-11 -> 2026-08-11, dataset llega a 2026-08-17);
               exit reasons limpios (solo sl_hit/timeout/tp_hit); 100% con
               SL/TP y AgentDecisionJson; misma ruta de codigo del motor
               (_run_generic / _capital_sim) que FVG/ADN/OrderBlock -> auditar
               esta estrategia audita el modelo economico comun a las 4
               familias "engine-faithful" del Post-Mortem.
  ventana    : señales 2026-07-10 -> 2026-08-13 (pad)
  config     : leida de StrategyProfiles en verge-db, SIN tocar nada
  NO se optimiza ni un parametro para hacer coincidir resultados.

Salidas: scratch_gate_trades.csv (tabla trade-a-trade) + stdout con agregados,
analisis TP/SL intrabar, chequeos de datos y VEREDICTO (PASS/CONDITIONAL/FAILED).
"""
import os, sys, json, csv, io, sqlite3, math, subprocess
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))

REAL_CSV = os.path.join(HERE, "..", "..", "scratch_ma2_real.csv")
OUT_CSV  = os.path.join(HERE, "..", "..", "scratch_gate_trades.csv")

STRAT_NAME = "MA Slope Caso 2"
WIN_START = "2026-07-10T00:00:00Z"
WIN_END   = "2026-08-13T00:00:00Z"
FEE_PER_SIDE = 0.0004  # el mismo que usa el motor

def ms(iso):
    if iso is None or iso == "":
        return None
    s = iso.strip().replace("T", " ").replace("Z", "")
    # quitar offset tz tipo +00 / +00:00
    for sep in ("+00:00", "+00", " +00", "-00:00"):
        if s.endswith(sep):
            s = s[: -len(sep)]
    s = s.strip()
    if "." in s:
        head, frac = s.split(".")
        frac = (frac + "000000")[:6]
        s = head + "." + frac
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f" if "." in s else "%Y-%m-%d %H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

def load_profile():
    q = ('SELECT row_to_json(t) FROM (SELECT "Id","Name","StrategyType","AllowLong","AllowShort",'
         '"TpMultiplier","SlMultiplier","MinRR","MarginPerTrade","MaxOpenPositions",'
         '"MaxTradeDurationCandles","PatternParamsJson" FROM "StrategyProfiles" '
         f"WHERE \"Name\"='{STRAT_NAME}') t;")
    out = subprocess.check_output(["docker","exec","verge-db","psql","-U","postgres","-d","Verge","-t","-A","-c",q])
    p = json.loads(out.decode().strip())
    # keys que el motor espera (camelCase del StrategyProfile DTO)
    return {
        "id": p["Id"], "name": p["Name"],
        "allowLong": p["AllowLong"], "allowShort": p["AllowShort"],
        "tpMultiplier": float(p["TpMultiplier"]), "slMultiplier": float(p["SlMultiplier"]),
        "minRR": float(p["MinRR"]), "marginPerTrade": float(p["MarginPerTrade"]),
        "maxOpenPositions": int(p["MaxOpenPositions"]),
        "maxTradeDurationCandles": int(p["MaxTradeDurationCandles"]),
        "patternParamsJson": p["PatternParamsJson"],
    }

def load_real():
    rows = []
    with open(REAL_CSV, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                dj = json.loads(r["AgentDecisionJson"]) if r["AgentDecisionJson"] else {}
            except Exception:
                dj = {}
            sig_iso = dj.get("captured_at_utc")
            sm = (dj.get("agent_meta") or {}).get("setup_metrics") or {}
            rows.append({
                "symbol": r["Symbol"],
                "side": int(r["Side"]),
                "opened_at": r["OpenedAt"],
                "closed_at": r["ClosedAt"],
                "signal_ts_ms": ms(sig_iso) if sig_iso else None,
                "opened_ms": ms(r["OpenedAt"]),
                "closed_ms": ms(r["ClosedAt"]) if r["ClosedAt"] else None,
                "entry": float(r["EntryPrice"]),
                "close": float(r["ClosePrice"]) if r["ClosePrice"] else None,
                "sl": float(r["SlPrice"]) if r["SlPrice"] else None,
                "tp": float(r["TpPrice"]) if r["TpPrice"] else None,
                "pnl": float(r["RealizedPnl"]) if r["RealizedPnl"] else None,
                "entry_fee": float(r["EntryFee"]) if r["EntryFee"] else 0.0,
                "exit_fee": float(r["ExitFee"]) if r["ExitFee"] else 0.0,
                "funding": float(r["TotalFundingPaid"]) if r["TotalFundingPaid"] else 0.0,
                "exit_reason": r["ExitReason"],
                "status": int(r["Status"]),
                "size": float(r["Size"]) if r["Size"] else None,
                "mfe": float(r["MaxFavorablePrice"]) if r["MaxFavorablePrice"] else None,
                "mae": float(r["MaxAdversePrice"]) if r["MaxAdversePrice"] else None,
                "rr_meta": sm.get("rr"),
                "sl_dist_pct_meta": sm.get("sl_distance_pct"),
            })
    return rows

CACHE = os.path.join(HERE, "gate_replay_cache.json")

def run_replay(profile):
    if os.path.exists(CACHE):
        print(f"[replay] usando cache {CACHE}")
        return json.load(open(CACHE))
    from engine import BacktestEngine, _INTERVAL_MS, BASE_MS
    eng = BacktestEngine()
    avail = set(eng.available_symbols())
    # universo faithful: watchlist de produccion ∩ lo que hay en el dataset
    wl = json.load(open(os.path.join(HERE, "..", "data", "watchlist_cache.json")))["symbols"]
    symbols = sorted(s for s in wl if s in avail)
    # + cualquier simbolo que realmente tradeo y no este en la watchlist actual
    real_syms = set(t["symbol"] for t in load_real())
    for s in sorted(real_syms):
        if s in avail and s not in symbols:
            symbols.append(s)
    print(f"[replay] universo: {len(symbols)} simbolos (watchlist∩dataset + {len(real_syms & avail - set(symbols))} extra reales)")
    missing_real = sorted(real_syms - avail)
    if missing_real:
        print(f"[replay] OJO: {len(missing_real)} simbolos con trades reales SIN datos historicos: {missing_real}")

    # capturar all_signals_raw ademas del resultado con capital-sim
    stash = {}
    orig = eng._capital_sim
    def cap(trades, prof, symbols_used=None):
        stash["raw"] = [dict(t) for t in trades]
        return orig(trades, prof, symbols_used=symbols_used)
    eng._capital_sim = cap

    # run_parallel: la deteccion corre en 8 procesos; _capital_sim (y por tanto
    # el monkeypatch de arriba) corre en el proceso principal sobre el conjunto
    # combinado de señales -> captura all_raw_trades igual. MaGeometry es
    # direct-injection sin competencia top-5, asi que run_parallel es FIEL
    # (identico al secuencial salvo desempates, ya resueltos en _capital_sim).
    res = eng.run_parallel("MaGeometry", profile, symbols, ms(WIN_START), ms(WIN_END))
    res["_raw_signals"] = stash.get("raw", [])
    res["_missing_real_syms"] = missing_real
    res["_n_symbols"] = len(symbols)
    try:
        json.dump(res, open(CACHE, "w"))
    except Exception as e:
        print("[replay] no se pudo cachear:", e)
    return res

def classify(real, bt, same_candle_tp_sl):
    """Devuelve (codigo, detalle) de la PRIMERA divergencia material."""
    if bt is None:
        return ("A", "produccion abrio; replay no genero señal ni trade para este simbolo/ventana")
    dpct = lambda a, b: abs(a - b) / b * 100 if b else 0.0
    # B timestamp
    if real["signal_ts_ms"] and abs(bt["open_time"] - real["signal_ts_ms"]) > 65 * 60 * 1000:
        return ("B", f"señal replay {datetime.utcfromtimestamp(bt['open_time']/1000)} vs real {datetime.utcfromtimestamp(real['signal_ts_ms']/1000)}")
    # C entry price
    if dpct(bt["entry"], real["entry"]) > 0.15:
        return ("C", f"entry replay {bt['entry']:.6g} vs real {real['entry']:.6g} ({dpct(bt['entry'], real['entry']):.2f}%)")
    # E SL/TP levels
    if real["sl"] and dpct(bt["sl"], real["sl"]) > 0.25:
        return ("E", f"SL replay {bt['sl']:.6g} vs real {real['sl']:.6g} ({dpct(bt['sl'], real['sl']):.2f}%)")
    if real["tp"] and dpct(bt["tp"], real["tp"]) > 0.25:
        return ("E", f"TP replay {bt['tp']:.6g} vs real {real['tp']:.6g} ({dpct(bt['tp'], real['tp']):.2f}%)")
    # reason mapping
    rmap = {"TP": "tp_hit", "SL": "sl_hit", "zombie_timeout": "timeout"}
    bt_reason = rmap.get(bt["close_reason"], bt["close_reason"])
    if bt_reason != real["exit_reason"]:
        if same_candle_tp_sl and {bt_reason, real["exit_reason"]} == {"tp_hit", "sl_hit"}:
            return ("F", f"misma vela toco TP y SL; replay resolvio {bt_reason}, real {real['exit_reason']}")
        return ("E", f"motivo de salida replay={bt_reason} vs real={real['exit_reason']}")
    # G funding
    if abs(real["funding"]) > 0.01:
        return ("G", f"funding real ${real['funding']:.4f}; replay no modela funding")
    # H fees
    real_fees = real["entry_fee"] + real["exit_fee"]
    if bt.get("_fees") is not None and abs(bt["_fees"] - real_fees) > 0.02:
        return ("H", f"fees replay ${bt['_fees']:.4f} vs real ${real_fees:.4f}")
    # I slippage / exit px
    if real["close"] and bt.get("_close_px") and dpct(bt["_close_px"], real["close"]) > 0.15:
        return ("I", f"precio de salida replay {bt['_close_px']:.6g} vs real {real['close']:.6g}")
    # PnL residual
    if real["pnl"] is not None and bt.get("pnl") is not None and abs(bt["pnl"] - real["pnl"]) > 0.75:
        return ("M", f"PnL replay ${bt['pnl']:.2f} vs real ${real['pnl']:.2f} sin causa unica identificada")
    return ("OK", "coincide dentro de tolerancia")

def main():
    profile = load_profile()
    print("=" * 78)
    print("CONFIG CONGELADA (leida de verge-db, sin modificar):")
    print(json.dumps({k: v for k, v in profile.items() if k != "patternParamsJson"}, indent=2))
    pj = json.loads(profile["patternParamsJson"])
    print("patternParams:", json.dumps(pj))
    print(f"  timeframe = {pj.get('timeframe')}")

    real = load_real()
    # OJO: en verge-db "Status" NO es open/closed. Status=1 = trade cerrado en
    # TP (ExitReason='tp_hit'); Status=2 = cerrado en SL o timeout. Los 113
    # trades TIENEN ExitReason terminal -> los 113 estan cerrados.
    real_closed = real  # todos cerrados
    print(f"\nREAL: {len(real)} trades ({len(real_closed)} cerrados). "
          f"rr_meta distinct={sorted(set(t['rr_meta'] for t in real if t['rr_meta']))[:6]} "
          f"sl_dist_pct_meta rango=[{min(t['sl_dist_pct_meta'] for t in real if t['sl_dist_pct_meta']):.4f},"
          f"{max(t['sl_dist_pct_meta'] for t in real if t['sl_dist_pct_meta']):.4f}]")

    print("\n[replay] corriendo motor real run_ma_geometry ...")
    res = run_replay(profile)
    bt_trades = res["trades"]                # aceptados tras capital-sim
    bt_raw = res["_raw_signals"]             # todas las señales antes de cupos
    # enriquecer bt con fees/close_px/pnl (capital-sim ya calculo t["pnl"])
    margin = profile["marginPerTrade"]
    for t in bt_trades:
        qty = margin / t["entry"]
        if t["close_reason"] == "TP": cpx = t["tp"]
        elif t["close_reason"] == "zombie_timeout": cpx = t.get("_zombie_close_price")
        else: cpx = t["sl"]
        t["_close_px"] = cpx
        t["_fees"] = (qty * t["entry"] + qty * (cpx or t["entry"])) * FEE_PER_SIDE
    print(f"[replay] {len(bt_raw)} señales crudas, {len(bt_trades)} aceptadas tras cupos ({profile['maxOpenPositions']} slots)")

    # ---- match por symbol + proximidad de tiempo de señal ----
    bt_by_sym = {}
    for t in bt_trades:
        bt_by_sym.setdefault(t["symbol"], []).append(t)
    raw_by_sym = {}
    for t in bt_raw:
        raw_by_sym.setdefault(t["symbol"], []).append(t)

    conn = sqlite3.connect(os.path.join(HERE, "..", "data", "binance_vision_clean.db"))
    def candle_5m(sym, ts_ms):
        r = conn.execute("SELECT open_time,open,high,low,close FROM klines_5m WHERE symbol=? AND interval='5m' "
                         "AND open_time<=? ORDER BY open_time DESC LIMIT 1", (sym, ts_ms)).fetchone()
        return r

    rows_out = []
    counts = {}
    used_bt = set()
    for rt in real:
        sym = rt["symbol"]
        cands = sorted(bt_by_sym.get(sym, []), key=lambda b: abs(b["open_time"] - (rt["signal_ts_ms"] or rt["opened_ms"])))
        match = None
        for c in cands:
            if id(c) in used_bt:
                continue
            if abs(c["open_time"] - (rt["signal_ts_ms"] or rt["opened_ms"])) <= 6 * 3600 * 1000:
                match = c; used_bt.add(id(c)); break
        # ¿hubo señal cruda (slot-rechazada) aunque no haya trade aceptado?
        had_raw = any(abs(x["open_time"] - (rt["signal_ts_ms"] or rt["opened_ms"])) <= 6*3600*1000 for x in raw_by_sym.get(sym, []))

        # deteccion de "misma vela 5m toca TP y SL" para clase F
        same_candle = False
        if match:
            k = candle_5m(sym, match["close_time"] - 1)
            if k and rt["sl"] and rt["tp"]:
                _, o, h, l, c = k
                same_candle = (l <= match["sl"] and h >= match["tp"])
        code, detail = classify(rt, match, same_candle)
        if code == "A" and had_raw:
            code, detail = ("L", "produccion abrio; replay SI genero la señal pero un cupo de capital la rechazo (estado de riesgo/slots distinto)")
        counts[code] = counts.get(code, 0) + 1
        rows_out.append({
            "symbol": sym, "real_signal": rt["opened_at"][:19], "dir": "LONG" if rt["side"] == 0 else "SHORT",
            "real_entry": rt["entry"], "bt_entry": match["entry"] if match else "",
            "real_sl": rt["sl"], "bt_sl": match["sl"] if match else "",
            "real_tp": rt["tp"], "bt_tp": match["tp"] if match else "",
            "real_exit_ts": rt["closed_at"][:19] if rt["closed_at"] else "",
            "bt_exit_ts": datetime.utcfromtimestamp(match["close_time"]/1000).isoformat() if match else "",
            "real_exit_px": rt["close"], "bt_exit_px": match["_close_px"] if match else "",
            "real_reason": rt["exit_reason"], "bt_reason": match["close_reason"] if match else "",
            "real_funding": rt["funding"], "real_fees": round(rt["entry_fee"]+rt["exit_fee"], 4),
            "bt_fees": round(match["_fees"], 4) if match else "",
            "real_pnl": round(rt["pnl"], 3) if rt["pnl"] is not None else "",
            "bt_pnl": round(match["pnl"], 3) if match else "",
            "diff_pnl": round((match["pnl"] - rt["pnl"]), 3) if (match and rt["pnl"] is not None) else "",
            "class": code, "explicacion": detail,
        })

    # trades del replay que NO matchean ningun trade real (produccion no abrio)
    unmatched_bt = [t for t in bt_trades if id(t) not in used_bt]
    for t in unmatched_bt:
        counts["A*"] = counts.get("A*", 0) + 1
        rows_out.append({
            "symbol": t["symbol"], "real_signal": "", "dir": "LONG" if t["side"] == 0 else "SHORT",
            "real_entry": "", "bt_entry": t["entry"], "real_sl": "", "bt_sl": t["sl"],
            "real_tp": "", "bt_tp": t["tp"], "real_exit_ts": "",
            "bt_exit_ts": datetime.utcfromtimestamp(t["close_time"]/1000).isoformat(),
            "real_exit_px": "", "bt_exit_px": t["_close_px"], "real_reason": "", "bt_reason": t["close_reason"],
            "real_funding": "", "real_fees": "", "bt_fees": round(t["_fees"], 4),
            "real_pnl": "", "bt_pnl": round(t["pnl"], 3), "diff_pnl": "",
            "class": "A*", "explicacion": "replay abrio un trade que produccion NO abrio (señal/estado divergente)",
        })

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)
    print(f"\ntabla trade-a-trade -> {OUT_CSV}  ({len(rows_out)} filas)")

    # ---------- 3. clasificacion de divergencias ----------
    LBL = {"OK":"coincide","A":"señal: prod abrio, replay no","A*":"señal: replay abrio, prod no",
           "B":"timestamp","C":"precio entrada","D":"fill/ejecucion","E":"SL/TP o motivo salida",
           "F":"ambiguedad intrabar TP&SL","G":"funding","H":"fees","I":"slippage salida",
           "J":"datos OHLCV","K":"config distinta","L":"estado/riesgo/cupos","M":"otra/UNKNOWN"}
    print("\n" + "=" * 78 + "\n3. CLASIFICACION DE DIVERGENCIAS\n" + "-" * 78)
    tot = sum(counts.values())
    for k in sorted(counts, key=lambda x: -counts[x]):
        print(f"  {k:3} {LBL.get(k,'?'):32} {counts[k]:4}  ({counts[k]/tot*100:4.1f}%)")
    matched = [r for r in rows_out if r["class"] not in ("A","A*","L")]
    n_ok = counts.get("OK", 0)
    print(f"\n  matcheados (real∩replay): {len(matched)}  | exactos dentro de tolerancia: {n_ok}")

    # ---------- 4. metricas agregadas REAL vs BACKTEST ----------
    def agg(trades, is_real):
        cl = list(trades)
        if is_real:
            pnl = [t["pnl"] for t in cl if t["pnl"] is not None]
            fees = sum((t["entry_fee"]+t["exit_fee"]) for t in cl)
            fund = sum(t["funding"] for t in cl)
            wins = [t for t in cl if t["exit_reason"] == "tp_hit"]
            longs = sum(1 for t in cl if t["side"] == 0); shorts = len(cl)-longs
        else:
            pnl = [t["pnl"] for t in cl]
            fees = sum(t["_fees"] for t in cl); fund = 0.0
            wins = [t for t in cl if t["close_reason"] == "TP"]
            longs = sum(1 for t in cl if t["side"] == 0); shorts = len(cl)-longs
        gross = sum(pnl) + fees + fund  # pnl real ya es neto de fees+funding
        pos = [p for p in pnl if p > 0]; neg = [p for p in pnl if p < 0]
        eq = 0; peak = 0; mdd = 0
        for p in pnl:
            eq += p; peak = max(peak, eq); mdd = min(mdd, eq - peak)
        return {
            "n": len(pnl), "win_rate": 100*len(wins)/len(pnl) if pnl else 0,
            "gross": gross, "fees": fees, "funding": fund, "net": sum(pnl),
            "pf": (sum(pos)/abs(sum(neg))) if neg else float("inf"),
            "avg": sum(pnl)/len(pnl) if pnl else 0,
            "median": sorted(pnl)[len(pnl)//2] if pnl else 0,
            "mdd": mdd, "long": longs, "short": shorts,
        }
    ra = agg(real, True)
    # para el agregado del replay, usar SOLO los bt que matchean un trade real
    # (comparacion like-for-like) y por separado el universo completo del replay
    bt_matched_ids = used_bt
    ba_match = agg([t for t in bt_trades if id(t) in bt_matched_ids], False)
    ba_all = agg(bt_trades, False)

    print("\n" + "=" * 78 + "\n4. METRICAS AGREGADAS\n" + "-" * 78)
    hdr = f"{'metrica':16} {'REAL':>12} {'BT(match)':>12} {'BT(todos)':>12} {'errAbs':>10} {'errRel%':>9}"
    print(hdr)
    def line(name, rv, bv, ba):
        ea = bv - rv
        er = (ea / rv * 100) if rv else float("nan")
        print(f"{name:16} {rv:12.3f} {bv:12.3f} {ba:12.3f} {ea:10.3f} {er:9.1f}")
    line("n trades", ra["n"], ba_match["n"], ba_all["n"])
    line("win rate %", ra["win_rate"], ba_match["win_rate"], ba_all["win_rate"])
    line("gross PnL", ra["gross"], ba_match["gross"], ba_all["gross"])
    line("fees", ra["fees"], ba_match["fees"], ba_all["fees"])
    line("funding", ra["funding"], ba_match["funding"], ba_all["funding"])
    line("net PnL", ra["net"], ba_match["net"], ba_all["net"])
    line("profit factor", ra["pf"], ba_match["pf"], ba_all["pf"])
    line("avg trade", ra["avg"], ba_match["avg"], ba_all["avg"])
    line("median trade", ra["median"], ba_match["median"], ba_all["median"])
    line("max drawdown", ra["mdd"], ba_match["mdd"], ba_all["mdd"])
    line("long / short", ra["long"], ba_match["long"], ba_all["long"])

    # distribucion por simbolo (top divergencias de PnL)
    print("\n  Top 12 divergencias de PnL por trade (|diff|):")
    dd = sorted([r for r in rows_out if r["diff_pnl"] != ""], key=lambda r: -abs(r["diff_pnl"]))[:12]
    for r in dd:
        print(f"   {r['symbol']:14} real ${r['real_pnl']:>8} vs bt ${r['bt_pnl']:>8}  diff ${r['diff_pnl']:>8}  [{r['class']}] {r['explicacion'][:60]}")

    # ---------- 5. TP/SL intrabar ----------
    print("\n" + "=" * 78 + "\n5. AUDITORIA TP/SL — AMBIGUEDAD INTRABAR\n" + "-" * 78)
    amb = []
    for r in rows_out:
        if r["class"] == "" or not r["bt_reason"] or r["real_reason"] == "":
            continue
        sym = r["symbol"]
        # buscar bt match
        bt = next((t for t in bt_trades if t["symbol"] == sym and
                   datetime.utcfromtimestamp(t["close_time"]/1000).isoformat() == r["bt_exit_ts"]), None)
        if not bt: continue
        k = candle_5m(sym, bt["close_time"] - 1)
        if not k: continue
        _, o, h, l, c = k
        touch_tp = h >= bt["tp"]; touch_sl = l <= bt["sl"]
        if touch_tp and touch_sl:
            amb.append((sym, r["bt_reason"], r["real_reason"], r["real_pnl"], r["bt_pnl"]))
    print(f"  velas 5m del replay que tocan TP y SL en la MISMA vela: {len(amb)}")
    print("  (el motor resuelve SIEMPRE TP primero -> sesgo optimista; linea engine.py:919-925)")
    for sym, btr, rr, rp, bp in amb:
        print(f"   {sym:14} replay={btr:4} real={rr:8} realPnL=${rp} btPnL=${bp}")
    if amb:
        opt = sum(1 for a in amb if a[1] == "TP" and a[2] != "tp_hit")
        print(f"  de esas, {opt} el replay las contó como TP pero en real NO fueron tp_hit "
              f"-> ganancia estructural del motor en {opt} trades")

    # ---------- 6. equivalencia de datos ----------
    print("\n" + "=" * 78 + "\n6. EQUIVALENCIA DE DATOS OHLCV\n" + "-" * 78)
    smp = [t["symbol"] for t in real_closed][:8]
    for sym in smp:
        rt = next(t for t in real_closed if t["symbol"] == sym)
        k = candle_5m(sym, rt["opened_ms"])
        if not k:
            print(f"   {sym:12} SIN vela 5m historica cerca de la entrada real"); continue
        ot, o, h, l, c = k
        drift = abs(c - rt["entry"]) / rt["entry"] * 100
        gap_min = (rt["opened_ms"] - ot) / 60000
        print(f"   {sym:12} entry real {rt['entry']:.6g} | close vela 5m previa {c:.6g} "
              f"(drift {drift:.3f}%, vela abre {gap_min:.0f} min antes de OpenedAt)")
    if res["_missing_real_syms"]:
        print(f"\n   SIMBOLOS con trade real y SIN historico: {res['_missing_real_syms']}")

    # ---------- like-for-like sobre los pares matcheados ----------
    pairs = [r for r in rows_out if r["class"] not in ("A", "A*", "L") and r["real_pnl"] != "" and r["bt_pnl"] != ""]
    lf_real = sum(r["real_pnl"] for r in pairs)
    lf_bt = sum(r["bt_pnl"] for r in pairs)
    print("\n" + "=" * 78 + "\n4b. LIKE-FOR-LIKE (solo los pares real∩replay que matchean)\n" + "-" * 78)
    print(f"  pares matcheados: {len(pairs)} de {len(real)} trades reales ({len(pairs)/len(real)*100:.0f}%)")
    print(f"  suma PnL real de esos pares : ${lf_real:8.2f}")
    print(f"  suma PnL replay de esos pares: ${lf_bt:8.2f}")
    print(f"  error absoluto: ${lf_bt - lf_real:8.2f}   error relativo: "
          f"{(lf_bt - lf_real)/abs(lf_real)*100 if lf_real else float('nan'):.0f}%")
    within = sum(1 for r in pairs if abs(r["diff_pnl"]) <= 0.75) if pairs else 0
    print(f"  pares con |ΔPnL| <= $0.75: {within}/{len(pairs)}")

    # ---------- signal inflation ----------
    n_raw = len(bt_raw)
    print("\n" + "=" * 78 + "\nINFLACION DE SEÑAL (replay vs realidad)\n" + "-" * 78)
    print(f"  señales crudas detectadas por el replay : {n_raw}")
    print(f"  trades realmente abiertos por produccion: {len(real)}")
    print(f"  ratio: el replay dispara {n_raw/len(real):.1f}x mas señales que las que produccion ejecuto")
    print(f"  trades aceptados por el replay tras cupos: {len(bt_trades)}  (vs {len(real)} reales)")

    # ---------- 7. GATE ----------
    print("\n" + "=" * 78 + "\n7. GATE — VEREDICTO\n" + "-" * 78)
    signal_match_rate = len(pairs) / len(real) * 100
    n_nodata = 25  # trades reales sobre simbolos sin historico (calculado aparte)
    print(f"  trades reales: {len(real)}  | con contraparte identificable en replay: {len(pairs)} ({signal_match_rate:.0f}%)")
    print(f"  de los no matcheados: {n_nodata} sobre simbolos SIN datos historicos (clase J, no reconstruibles)")
    print(f"  divergencia PnL like-for-like sobre los {len(pairs)} pares: "
          f"{(lf_bt - lf_real)/abs(lf_real)*100 if lf_real else float('nan'):.0f}%")
    print(f"  inflacion de señal: {n_raw/len(real):.1f}x")
    print(f"  clases dominantes: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x:-x[1])[:5]))
    print("\n  (veredicto interpretado con estos numeros en el informe)")

if __name__ == "__main__":
    main()
