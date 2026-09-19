"""
PHASE 2 §F — auditoría del sesgo intrabar TP/SL para estrategias de SL/TP ajustado.

Pregunta: cuando una misma vela toca TP y SL, el motor resuelve TP primero
(engine.py:_run_generic / run_ma_geometry_global -> chequea hit_tp antes que
hit_sl). ¿Ese sesgo optimista es material para FVG / scalping?

Método (ground truth = trades reales): para cada trade real con SL/TP, recorrer
las velas históricas de 5 m entre OpenedAt y ClosedAt y contar cuántas "abarcan
ambos" niveles. En esas, comparar lo que el motor contaría (TP) con lo que
realmente pasó (ExitReason real). Cuantificar el DPnL si el motor cuenta TP y
la realidad fue SL. Repetir a 15 m para mostrar por qué 5 m ayuda pero no cierra.

Clasifica por familia: NEGLIGIBLE / MATERIAL / UNKNOWN.
No usa una estimación favorable a producción: cuenta TODA vela que abarque ambos.
"""
import os, sys, csv, sqlite3
from datetime import datetime, timezone
from collections import defaultdict

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CSV = os.path.join(ROOT, "scratch_intrabar_trades.csv")


def pms(s):
    if not s:
        return None
    s = s.strip().replace("T", " ").replace("Z", "")
    for x in ("+00:00", "+00"):
        if s.endswith(x):
            s = s[:-len(x)].strip()
    if "." in s:
        h, fr = s.split("."); s = h + "." + (fr + "000000")[:6]
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    else:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def main():
    conn = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    rows = list(csv.DictReader(open(CSV, encoding="utf-8", errors="replace")))

    def klines(sym, interval, a, b):
        tbl = "klines_5m" if interval == "5m" else "klines_clean"
        return conn.execute(
            f"SELECT open_time,high,low FROM {tbl} WHERE symbol=? AND interval=? AND open_time>=? AND open_time<=? ORDER BY open_time",
            (sym, interval, a, b)).fetchall()

    def has_any(sym, interval):
        tbl = "klines_5m" if interval == "5m" else "klines_clean"
        return conn.execute(f"SELECT 1 FROM {tbl} WHERE symbol=? AND interval=? LIMIT 1", (sym, interval)).fetchone() is not None

    stats = {}
    for interval in ("5m", "15m"):
        fam = defaultdict(lambda: {"n": 0, "no_data": 0, "too_short": 0, "with_candle": 0,
                                   "span_trades": 0, "span_and_real_sl": 0,
                                   "dpnl_optimistic": 0.0, "gross_abs": 0.0})
        for r in rows:
            name = r["Name"]
            f = fam[name]
            f["n"] += 1
            sym = r["Symbol"]
            side = int(r["Side"])
            try:
                entry = float(r["EntryPrice"]); sl = float(r["SlPrice"]); tp = float(r["TpPrice"])
                pnl = float(r["RealizedPnl"] or 0)
            except Exception:
                continue
            a, b = pms(r["OpenedAt"]), pms(r["ClosedAt"])
            if not a or not b:
                f["no_data"] += 1; continue
            ks = klines(sym, interval, a, b)
            if not ks:
                if has_any(sym, interval):
                    f["too_short"] += 1   # trade mas corto que una vela: no aplica el sesgo
                else:
                    f["no_data"] += 1
                continue
            f["with_candle"] += 1
            f["gross_abs"] += abs(pnl)
            spanning = 0
            for _ot, h, l in ks:
                if side == 0:   # LONG: tp>entry>sl
                    if h >= tp and l <= sl:
                        spanning += 1
                else:            # SHORT: sl>entry>tp
                    if l <= tp and h >= sl:
                        spanning += 1
            if spanning:
                f["span_trades"] += 1
                real_was_sl = "sl" in (r["ExitReason"] or "").lower() or "stop" in (r["ExitReason"] or "").lower()
                if real_was_sl:
                    f["span_and_real_sl"] += 1
                    # DPnL si el motor cuenta TP en vez del SL real:
                    qty = 150.0 / entry  # margin fijo 150, lev 1
                    tp_pnl = qty * (tp - entry) if side == 0 else qty * (entry - tp)
                    sl_pnl = qty * (sl - entry) if side == 0 else qty * (entry - sl)
                    fee = (qty * entry + qty * tp) * 0.0004
                    f["dpnl_optimistic"] += (tp_pnl - fee) - (sl_pnl - fee)
        stats[interval] = fam

    print("=" * 92)
    print("PHASE 2 §F — SESGO INTRABAR TP/SL (motor resuelve TP primero)")
    print("=" * 92)
    for interval in ("5m", "15m"):
        print(f"\n### granularidad {interval} (el motor camina en 5m; 15m = referencia de backtest naive)")
        print(f"{'familia':22}{'trades':>8}{'no data':>8}{'2short':>7}{'w/candle':>9}{'span both':>10}{'->realSL':>9}{'%span':>7}{'DPnL':>9}{'%gross':>8}")
        for name, f in sorted(stats[interval].items()):
            wc = f["with_candle"]
            pct_span = 100 * f["span_trades"] / wc if wc else 0
            pct_gross = 100 * f["dpnl_optimistic"] / f["gross_abs"] if f["gross_abs"] else 0
            print(f"{name:22}{f['n']:>8}{f['no_data']:>8}{f['too_short']:>7}{wc:>9}{f['span_trades']:>10}{f['span_and_real_sl']:>9}"
                  f"{pct_span:>6.1f}%{f['dpnl_optimistic']:>9.1f}{pct_gross:>7.1f}%")

    print("\n### Clasificacion (regla pre-fijada: NEGLIGIBLE si %span<3 y |DPnL|<5% del gross entre")
    print("    trades con >=1 vela; MATERIAL si supera cualquiera; UNKNOWN si 'no data' > 20% de la familia)")
    f5 = stats["5m"]
    for name, f in sorted(f5.items()):
        if f["no_data"] / f["n"] > 0.20:
            verd = f"UNKNOWN (no data {100*f['no_data']/f['n']:.0f}%)"
        elif f["with_candle"] == 0:
            verd = "UNKNOWN (todos los trades mas cortos que una vela de 5m)"
        else:
            pct_span = 100 * f["span_trades"] / f["with_candle"]
            pct_gross = abs(100 * f["dpnl_optimistic"] / f["gross_abs"]) if f["gross_abs"] else 0
            verd = "NEGLIGIBLE" if (pct_span < 3 and pct_gross < 5) else f"MATERIAL (%span={pct_span:.1f}, DPnL={pct_gross:.1f}% gross)"
        print(f"  {name:22} -> {verd}   (n con vela={f['with_candle']}, too_short={f['too_short']})")


if __name__ == "__main__":
    main()
