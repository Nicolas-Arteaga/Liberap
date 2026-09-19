"""
Diagnostico: para cada trade real REPLAYABLE de MA Slope Caso 2, reproducir el
momento exacto de la señal y ver POR QUE el replay no lo abre.
Clasifica: no_pattern | veto:<code> | btc_block | daily_change | flash_crash |
           traded_before | blackout | OK(abre) .
"""
import os, sys, csv, json, subprocess
from datetime import datetime, timezone
from collections import Counter

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
ROOT = os.path.join(HERE, "..", "..")

from engine import BacktestEngine, BASE_INTERVAL, ARG_OFFSET_MS  # noqa
from setup_validator import validate_pre_trade  # noqa

REAL_CSV = os.path.join(ROOT, "scratch_ma2_real.csv")
ALL_CSV = os.path.join(ROOT, "scratch_all_trades_window.csv")


def ms(iso):
    s = iso.strip().replace("T", " ").replace("Z", "")
    for sep in ("+00:00", "+00"):
        if s.endswith(sep):
            s = s[:-len(sep)].strip()
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


def main():
    prof = load_profile()
    interval = json.loads(prof["patternParamsJson"]).get("timeframe", "1h")
    real = list(csv.DictReader(open(REAL_CSV, encoding="utf-8", errors="replace")))
    tb = {}
    for r in csv.DictReader(open(ALL_CSV, encoding="utf-8", errors="replace")):
        t = ms(r["OpenedAt"])
        if t:
            tb.setdefault(r["Symbol"], []).append(t)
    for s in tb:
        tb[s].sort()

    eng = BacktestEngine()
    avail = set(eng.available_symbols())
    btcf = eng.btc_filter

    cats = Counter()
    detail = []
    for row in real:
        sym = row["Symbol"]
        try:
            dj = json.loads(row["AgentDecisionJson"]) if row["AgentDecisionJson"] else {}
        except Exception:
            dj = {}
        cap = dj.get("captured_at_utc") or row["OpenedAt"]
        t = ms(cap)
        if sym not in avail:
            cats["UNREPLAYABLE_symbol"] += 1
            continue

        eng.fetcher.set_active_symbol(sym, intervals=(BASE_INTERVAL, interval))
        # probar en una ventana de +-2 velas de 5m alrededor de la señal real
        best = None
        for off in range(-6, 7):
            tt = t + off * 5 * 60 * 1000
            eng.fetcher.set_now(tt)
            geo = eng.ma_agent._read_ma_geometry(sym, interval=interval)
            if not geo:
                continue
            cand = eng.ma_agent._evaluate_ma_geometry_profile(prof, geo)
            if cand:
                best = (tt, cand)
                break
        if not best:
            cats["no_pattern"] += 1
            detail.append((sym, cap[:16], "no_pattern"))
            continue

        tt, cand = best
        eng.fetcher.set_now(tt)
        # traded_before cross-strategy
        day_iso = datetime.utcfromtimestamp((tt - ARG_OFFSET_MS) / 1000).date().isoformat()
        lst = tb.get(sym, [])
        earlier = [x for x in lst if x < tt and
                   datetime.utcfromtimestamp((x - ARG_OFFSET_MS) / 1000).date().isoformat() == day_iso]
        if earlier:
            cats["traded_before_cross"] += 1
            detail.append((sym, cap[:16], f"traded_before ({len(earlier)} earlier, first by other strat)"))
            continue

        # BTC block
        btcf._regime_cache = None; btcf._flash_crash_cache = None
        fc = btcf.is_flash_crash()
        reg = btcf.get_regime()
        if fc:
            cats["btc_flash_crash"] += 1
            detail.append((sym, cap[:16], "btc_flash_crash"))
            continue
        if int(cand.get("side", 0)) == 0 and reg == "DUMPING":
            cats["btc_block_dumping"] += 1
            detail.append((sym, cap[:16], "btc_block_dumping"))
            continue

        # daily change veto (inyectar y correr validate_pre_trade)
        rows_b, times_b = eng.fetcher._active_by_interval.get(BASE_INTERVAL, (None, None))
        dch = None
        if rows_b:
            import bisect
            hi = bisect.bisect_right(times_b, tt - 5 * 60 * 1000)
            if hi >= 2:
                lo = bisect.bisect_left(times_b, times_b[hi - 1] - 24 * 3600 * 1000)
                if lo < hi - 1 and rows_b[lo][4]:
                    dch = (rows_b[hi - 1][4] - rows_b[lo][4]) / rows_b[lo][4] * 100
        if dch is not None:
            cand["historical_daily_change_pct"] = dch
        px = cand.get("price_at_signal") or cand.get("current_price")
        v_ok, v_code, _ = validate_pre_trade(cand, px, profile=prof, btc_filter=None, btc_corr=None)
        if not v_ok:
            cats[f"veto:{v_code}"] += 1
            detail.append((sym, cap[:16], f"veto:{v_code} (daily_change={dch:.1f}%)" if dch is not None else f"veto:{v_code}"))
            continue

        risk = eng.risk_manager._calculate_position_nexus_style(sym, cand, 10000.0, prof)
        if not risk:
            cats["risk_none"] += 1
            detail.append((sym, cap[:16], "risk_none"))
            continue

        cats["OK_would_open"] += 1
        detail.append((sym, cap[:16], "OK_would_open"))

    print("=" * 70)
    print("POR QUE EL REPLAY NO ABRE CADA TRADE REAL REPLAYABLE (MA Slope Caso 2)")
    print("=" * 70)
    for k, v in cats.most_common():
        print(f"  {v:4}  {k}")
    print(f"\n  total real: {len(real)}")
    print("\nprimeras 40 filas:")
    for s, when, why in detail[:40]:
        print(f"  {s:14} {when:17} {why}")


if __name__ == "__main__":
    main()
