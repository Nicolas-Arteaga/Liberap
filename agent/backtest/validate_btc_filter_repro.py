"""
GAP 1 - prueba reproducible: el BTCMacroFilter historico (engine.py::_HistBtcShim
+ btc_klines_1m) reproduce el regimen que produccion registro en
AgentDecisionJson.btc_context.regime para los 113 trades reales de MA Slope Caso 2.

PASS si el % de acuerdo es alto (>= 90%) y NO hay ningun caso en que produccion
diga DUMPING y el historico diga NEUTRAL/BULLISH (ese seria el error peligroso:
dejariamos pasar un LONG que produccion bloqueo).
"""
import os, sys, csv, json
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python-service"))
from engine import BacktestEngine  # noqa

REAL_CSV = os.path.join(HERE, "..", "..", "scratch_ma2_real.csv")


def ms(iso):
    s = iso.strip().replace("T", " ").replace("Z", "")
    for sep in ("+00:00", "+00"):
        if s.endswith(sep):
            s = s[:-len(sep)].strip()
    if "." in s:
        h, fr = s.split("."); s = h + "." + (fr + "000000")[:6]
        return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp() * 1000)
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def main():
    rows = list(csv.DictReader(open(REAL_CSV, encoding="utf-8", errors="replace")))
    eng = BacktestEngine()
    bf = eng.btc_filter
    eng.fetcher.set_active_symbol("BTCUSDT", intervals=())  # no hace falta; get_btc_klines usa btc_klines_1m
    agree = 0
    total = 0
    dangerous = []
    rowsout = []
    for r in rows:
        try:
            d = json.loads(r["AgentDecisionJson"])
        except Exception:
            continue
        prod_regime = (d.get("btc_context") or {}).get("regime")
        cap = d.get("captured_at_utc")
        if not prod_regime or not cap:
            continue
        t = ms(cap)
        eng.fetcher.set_now(t)
        bf._regime_cache = None
        bf._flash_crash_cache = None
        hist_regime = bf.get_regime()
        total += 1
        ok = (hist_regime == prod_regime)
        if ok:
            agree += 1
        # error peligroso: prod bloqueo (DUMPING) y el historico dejaria pasar
        if prod_regime == "DUMPING" and hist_regime != "DUMPING":
            dangerous.append((r["Symbol"], cap, prod_regime, hist_regime))
        rowsout.append((r["Symbol"], cap[:16], prod_regime, hist_regime, "ok" if ok else "DIFF"))

    print(f"comparados: {total}")
    print(f"acuerdo exacto: {agree}/{total} = {100*agree/total:.1f}%")
    from collections import Counter
    print("matriz (prod -> hist):", Counter((a[2], a[3]) for a in rowsout))
    print(f"errores PELIGROSOS (prod=DUMPING, hist!=DUMPING): {len(dangerous)}")
    for x in dangerous:
        print("  ", x)
    print("\nprimeras 15 filas:")
    for x in rowsout[:15]:
        print(f"  {x[0]:12} {x[1]:17} prod={x[2]:8} hist={x[3]:8} {x[4]}")
    diffs = [x for x in rowsout if x[4] == "DIFF"]
    print(f"\ntotal DIFF: {len(diffs)}")
    for x in diffs[:20]:
        print(f"  {x[0]:12} {x[1]:17} prod={x[2]:8} hist={x[3]:8}")

    verdict = "PASS" if (100*agree/total >= 90 and not dangerous) else (
        "PARTIAL" if not dangerous else "FAIL")
    print(f"\nGAP 1 reproducibilidad BTC filter: {verdict}")


if __name__ == "__main__":
    main()
