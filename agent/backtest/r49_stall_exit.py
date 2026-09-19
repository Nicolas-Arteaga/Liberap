"""
ROUND 49 -- test de la idea del usuario: "no esperes al TP completo, si la
ganancia se estanca (deja de hacer nuevo maximo) despues de superar un
umbral en USD, cerrala manualmente ahi". Ejemplo real que dio el pie:
Band Touch 15m, TPs de 60-80 USD que el usuario corto a mano en +40.

Es una regla de SALIDA (igual que Trail-1/BE/Partial de R36), NO una
entrada nueva -- no se toca ninguna estrategia, se simula la MISMA
trayectoria real contrafactualmente. Aplicado a TODOS los perfiles
(transversal, como pidio el usuario -- "no importa si estan o no
activas"), no solo a Band Touch 15m.

Regla "stall-exit": una vez que la ganancia flotante supera `arm_usd`
por primera vez, se arma un contador. Si pasan `patience_bars` barras de
15m SIN que la ganancia flotante haga un nuevo maximo, se cierra TODO al
close de esa barra (causal: no se conoce el pico de antemano, solo se
detecta el estancamiento con `patience_bars` de retraso).
"""
import os, sys, math, json, sqlite3, collections
import numpy as np
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
CAP_BARS = 2880
FEE_PER_TRADE = 0.12


def load_trades():
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Symbol","Side","EntryPrice","ClosePrice","SlPrice","TpPrice",
                   "OpenedAt","ClosedAt","ExitReason","RealizedPnl","StrategyProfileId","Amount"
                   FROM "SimulatedTrades" t
                   WHERE t."ExitReason" IN ('tp_hit','sl_hit') AND t."Symbol" NOT IN ('ONUSDT','BBUSDT')""")
    rows = cur.fetchall()
    conn.close()
    return rows


def load_symbol_klines(con, symbol):
    k = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_clean "
                     "WHERE symbol=? AND interval='15m' ORDER BY open_time", (symbol,)).fetchall()
    if len(k) < 500:
        return None
    t = np.array([r[0] for r in k], np.int64)
    h = np.array([r[2] for r in k], float); l = np.array([r[3] for r in k], float)
    c = np.array([r[4] for r in k], float)
    return dict(t=t, h=h, l=l, c=c)


def find_bar_index(t_arr, ts_ms):
    idx = np.searchsorted(t_arr, ts_ms, side="right") - 1
    return idx if idx >= 0 else None


def simulate_baseline(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size):
    n_bars = min(CAP_BARS, n - i_start)
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl0_px) if side > 0 else (hi >= sl0_px)
        if sl_hit:
            return (side * (sl0_px - entry_px) * size) - FEE_PER_TRADE, "sl", k
        tp_hit = (hi >= tp0_px) if side > 0 else (lo <= tp0_px)
        if tp_hit:
            return (side * (tp0_px - entry_px) * size) - FEE_PER_TRADE, "tp", k
    j_last = min(i_start + n_bars - 1, n - 1)
    exit_px = (h[j_last] + l[j_last]) / 2
    return (side * (exit_px - entry_px) * size) - FEE_PER_TRADE, "time_cap", n_bars


def simulate_stall(h, l, i_start, n, side, entry_px, sl0_px, tp0_px, size, arm_usd, patience_bars):
    n_bars = min(CAP_BARS, n - i_start)
    max_fav_usd = -1e18
    bars_since_new_high = 0
    armed = False
    for k in range(n_bars):
        j = i_start + k
        hi, lo = h[j], l[j]
        sl_hit = (lo <= sl0_px) if side > 0 else (hi >= sl0_px)
        if sl_hit:
            return (side * (sl0_px - entry_px) * size) - FEE_PER_TRADE, "sl", k
        tp_hit = (hi >= tp0_px) if side > 0 else (lo <= tp0_px)
        if tp_hit:
            return (side * (tp0_px - entry_px) * size) - FEE_PER_TRADE, "tp", k

        fav_px = hi if side > 0 else lo
        fav_usd = side * (fav_px - entry_px) * size
        if fav_usd > max_fav_usd:
            max_fav_usd = fav_usd
            bars_since_new_high = 0
        else:
            bars_since_new_high += 1

        if not armed and max_fav_usd >= arm_usd:
            armed = True
            bars_since_new_high = 0  # arranca a contar paciencia desde que se arma

        if armed and bars_since_new_high >= patience_bars:
            exit_px = (h[j] + l[j]) / 2  # close de la barra donde se detecta el estancamiento (causal)
            return (side * (exit_px - entry_px) * size) - FEE_PER_TRADE, "stall_exit", k

    j_last = min(i_start + n_bars - 1, n - 1)
    exit_px = (h[j_last] + l[j_last]) / 2
    return (side * (exit_px - entry_px) * size) - FEE_PER_TRADE, "time_cap", n_bars


VARIANTS = [
    ("Stall-30usd-4h(16b)", 30, 16),
    ("Stall-30usd-8h(32b)", 30, 32),
    ("Stall-30usd-12h(48b)", 30, 48),
    ("Stall-50usd-8h(32b)", 50, 32),
]


def main():
    print("=== ROUND 49 -- STALL-EXIT (idea del usuario: cerrar cuando se estanca, no esperar el TP completo) ===\n")
    trades = load_trades()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    syms = sorted(set(t[0] for t in trades))
    kdata = {}
    for s in syms:
        d = load_symbol_klines(con, s)
        if d is not None:
            kdata[s] = d
    con.close()
    print(f"trades tp/sl totales (excl ON/BB): {len(trades)}  simbolos con klines: {len(kdata)}/{len(syms)}")

    recs = []
    skipped = 0
    for (sym, side_raw, entry_px, close_px, sl_px, tp_px, opened, closed, reason, pnl_v, prof, amount) in trades:
        if sym not in kdata or sl_px is None or tp_px is None or amount is None:
            skipped += 1
            continue
        d = kdata[sym]
        ts_open = int(opened.timestamp() * 1000)
        i = find_bar_index(d["t"], ts_open)
        if i is None or i + 5 >= len(d["c"]):
            skipped += 1
            continue
        side = 1 if side_raw == 0 else -1
        entry_px = float(entry_px); sl_px = float(sl_px); tp_px = float(tp_px)
        size = float(amount) / entry_px
        # TP original en USD (para filtrar como pidio el usuario: TPs<30usd no hace falta tocarlos)
        tp_usd = side * (tp_px - entry_px) * size
        recs.append(dict(symbol=sym, side=side, entry_px=entry_px, sl0=sl_px, tp0=tp_px, size=size,
                          i=i + 1, opened=opened, closed=closed, orig_reason=reason,
                          orig_pnl=float(pnl_v) if pnl_v else 0.0, profile=str(prof), tp_usd=tp_usd, d=d))
    print(f"trades simulables: {len(recs)}  (descartados: {skipped})\n")

    dates_sorted = sorted(r["opened"] for r in recs)
    tcut = dates_sorted[int(len(dates_sorted) * 0.6)]
    vcut = dates_sorted[int(len(dates_sorted) * 0.8)]

    def seg(dt):
        return "TRAIN" if dt <= tcut else ("VAL" if dt <= vcut else "OOS")

    # baseline + cada variante, por trade
    all_results = collections.defaultdict(list)
    for r in recs:
        n = len(r["d"]["c"]); h, l = r["d"]["h"], r["d"]["l"]
        base_pnl, base_reason, base_bars = simulate_baseline(h, l, r["i"], n, r["side"], r["entry_px"], r["sl0"], r["tp0"], r["size"])
        all_results["baseline"].append((base_pnl, r["orig_pnl"], base_reason, r))
        for name, arm_usd, patience in VARIANTS:
            sp, sreason, sbars = simulate_stall(h, l, r["i"], n, r["side"], r["entry_px"], r["sl0"], r["tp0"], r["size"], arm_usd, patience)
            all_results[name].append((sp, r["orig_pnl"], sreason, r))

    calib = np.array([x[0] - x[1] for x in all_results["baseline"]])
    print(f"CALIBRACION baseline reconstruido vs RealizedPnl real: media=${calib.mean():.3f} mediana=${np.median(calib):.3f}\n")

    print("#" * 110)
    print(f"{'REGLA':26s} {'seg':6s} {'n':>5s} {'PnL':>10s} {'PnL/mes':>9s} {'vs_base':>9s} {'WR':>5s} "
          f"{'stall_exits':>11s} {'salvados':>9s} {'empeorados':>10s}")
    print("#" * 110)
    baseline_by_seg = {}
    for rname in ["baseline"] + [v[0] for v in VARIANTS]:
        rows_all = all_results[rname]
        for s in ("TRAIN", "VAL", "OOS"):
            rows = [x for x in rows_all if seg(x[3]["opened"]) == s]
            if len(rows) < 20:
                continue
            pnl = np.array([x[0] for x in rows]); orig = np.array([x[1] for x in rows])
            days_span = max(1, (max(x[3]["opened"] for x in rows) - min(x[3]["opened"] for x in rows)).days)
            pnl_mo = pnl.sum() / (days_span / 30)
            wr = (pnl > 0).mean()
            n_stall = sum(1 for x in rows if x[2] == "stall_exit")
            if rname == "baseline":
                baseline_by_seg[s] = pnl.sum()
            delta = pnl.sum() - baseline_by_seg.get(s, pnl.sum())
            saved = int(((orig < 0) & (pnl > orig)).sum())
            worsened = int(((orig > 0) & (pnl < orig)).sum())
            print(f"{rname:26s} {s:6s} {len(rows):5d} ${pnl.sum():9.1f} ${pnl_mo:8.1f} ${delta:8.1f} "
                  f"{wr:5.2f} {n_stall:11d} {saved:9d} {worsened:10d}")
        print()

    # ---- filtro pedido por el usuario: aplicar SOLO a trades cuyo TP original es >=30 USD ----
    print("#" * 110)
    print("MISMA TABLA, PERO SOLO EN TRADES CUYO TP ORIGINAL ES >= $30 (como pidio el usuario explicitamente)")
    print("#" * 110)
    for rname in ["baseline"] + [v[0] for v in VARIANTS]:
        rows_all = [x for x in all_results[rname] if x[3]["tp_usd"] >= 30]
        pnl = np.array([x[0] for x in rows_all]); orig = np.array([x[1] for x in rows_all])
        if len(rows_all) < 5:
            continue
        n_stall = sum(1 for x in rows_all if x[2] == "stall_exit")
        print(f"{rname:26s} n={len(rows_all):4d}  PnL_total=${pnl.sum():8.1f}  PnL_original_total=${orig.sum():8.1f}  "
              f"stall_exits={n_stall}")

    # ---- caso puntual: Band Touch 15m (el ejemplo real del usuario) ----
    print("\n" + "#" * 110)
    print("CASO ESPECIFICO: Band Touch 15m (todo el historial disponible de este perfil)")
    print("#" * 110)
    profiles_seen = set(x[3]["profile"] for x in all_results["baseline"])
    band_touch_id = None
    for pid in profiles_seen:
        sample = next(x for x in all_results["baseline"] if x[3]["profile"] == pid)
        if False:
            pass
    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    cur = conn.cursor()
    cur.execute("""SELECT "Id" FROM "StrategyProfiles" WHERE "Name"='Band Touch 15m'""")
    row = cur.fetchone()
    conn.close()
    bt_id = str(row[0]) if row else None
    print(f"StrategyProfileId de 'Band Touch 15m': {bt_id}")
    for rname in ["baseline"] + [v[0] for v in VARIANTS]:
        rows_bt = [x for x in all_results[rname] if x[3]["profile"] == bt_id]
        if not rows_bt:
            continue
        pnl = np.array([x[0] for x in rows_bt])
        n_stall = sum(1 for x in rows_bt if x[2] == "stall_exit")
        print(f"  {rname:26s} n={len(rows_bt):3d}  PnL_total=${pnl.sum():7.1f}  stall_exits={n_stall}")


if __name__ == "__main__":
    main()
