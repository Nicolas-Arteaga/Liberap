"""
ROUND 8 — M18 KILL-OR-CONFIRM.
Reconstruccion causal y paranoica de M18 (perp de accion tokenizada vs apertura
RTH del cash US -> reversion del gap overnight).

REGLA DEL ROUND: no salvar M18 eligiendo costos. Reportar GROSS y NET con costos
plausibles. Verdict exactamente uno de PROMISING / PARK / FAILED.

Todo pre-declarado ANTES de mirar PnL:
  * universo por reglas ex-ante (ticker = accion/ETF US; excluye XAU/XAG/SPX);
  * gap = log(open[RTH_open, D] / close[ultimo bar RTH, D-1 habil]);  -> conocido en el instante del open
  * entrada = open del bar t0+1 (RTH_open + 5min), estrictamente posterior a la senal;
  * holding grid fijo: 5/10/15/30/45/60 min desde la entrada, y "to_close";
  * direccion: gap up -> SHORT ; gap down -> LONG  (los dos lados por separado);
  * buckets de |gap| absolutos fijos: (0,0.5%], (0.5,1.5%], (1.5,5%], (5,15%];
  * excluye |gap|>15% (accion corporativa) y primeros 5 dias habiles del simbolo;
  * DST US 2026: EST (UTC-5) antes de 2026-03-08, EDT (UTC-4) 03-08..11-01;
  * feriados y early-closes NYSE hardcodeados para la ventana de datos.

Controles (Test 5 / 10):
  C1 pre_open  : reversion del movimiento de los 90min PREVIOS al open (no del gap).
  C2 midday    : pseudo-evento a las 17:00 UTC (pseudo-gap = move de las ~17.5h previas).
  C3 deadhour  : idem a las 02:00 UTC.
  C4 nextday   : mismo gap/direccion/simbolo, retorno forward medido 24h DESPUES.
  C5 matched   : bares del mismo simbolo con vol trailing y |move 18h| matcheados (+-25%).
  incremental  : OLS signed_fwd ~ gap_signed + preopen_signed + trail_vol  (coef del gap).
"""
import os, sqlite3, json, math, numpy as np
from datetime import datetime, timezone, timedelta, date
from r7_common import agg_pairs

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
BAR = 5 * 60 * 1000
HOLD_BARS = [1, 2, 3, 6, 9, 12]            # 5,10,15,30,45,60 min desde la entrada (open[t0+1])
GAP_BUCKETS = [(0.0, 0.005), (0.005, 0.015), (0.015, 0.05), (0.05, 0.15)]
MAX_GAP = 0.15
SKIP_FIRST_TDAYS = 5
FIRST20_LIQ_MIN_USD = 1000.0              # mediana $/5m en los primeros 20 dias -> por debajo = untradeable

# --- calendario NYSE (ventana 2025-12 .. 2026-08-17) ---
DST_START = date(2026, 3, 8)              # EDT desde aca
DST_END = date(2026, 11, 1)
HOLIDAYS = {date(2025,12,25), date(2026,1,1), date(2026,1,19), date(2026,2,16),
            date(2026,4,3), date(2026,5,25), date(2026,6,19), date(2026,7,3)}
EARLY_CLOSE = {date(2025,12,24), date(2026,7,2)}   # cierre 13:00 ET

STOCK = {"AAPL","AMZN","MSFT","GOOGL","META","NVDA","TSLA","AMD","QCOM","IBM","UBER","DELL",
         "SMCI","AVGO","ASTS","AAOI","AXTI","HIMS","MSTR","COIN","INTC","MU","ORCL","PLTR",
         "BABA","HOOD","IREN","CRCL","OPEN","ARM"}
ETF = {"QQQ","SPY","SOXL","SQQQ","UVXY","TZA"}
EXCLUDE = {"XAU","XAG","SPX","COMP"}


def is_edt(d: date) -> bool:
    return DST_START <= d < DST_END


def rth_bounds_utc_ms(d: date):
    """(open_ms, close_ms) del RTH de la fecha d, o None si no es dia habil."""
    if d.weekday() >= 5 or d in HOLIDAYS:
        return None
    off = 4 if is_edt(d) else 5                      # UTC = ET + off
    open_h = 9 * 60 + 30 + off * 60                  # minutos UTC
    close_h = (13 * 60 if d in EARLY_CLOSE else 16 * 60) + off * 60
    base = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
    return base + open_h * 60000, base + close_h * 60000


def trading_days(d0: date, d1: date):
    out = []
    d = d0
    while d <= d1:
        if rth_bounds_utc_ms(d) is not None:
            out.append(d)
        d += timedelta(days=1)
    return out


# ----------------- self-tests -----------------
def _selftests():
    # 2026-05-06 (EDT) open = 13:30 UTC
    o, c = rth_bounds_utc_ms(date(2026, 5, 6))
    assert datetime.fromtimestamp(o/1000, timezone.utc).strftime("%H:%M") == "13:30", "EDT open"
    assert datetime.fromtimestamp(c/1000, timezone.utc).strftime("%H:%M") == "20:00", "EDT close"
    # 2026-02-09 (EST) open = 14:30 UTC
    o2, c2 = rth_bounds_utc_ms(date(2026, 2, 9))
    assert datetime.fromtimestamp(o2/1000, timezone.utc).strftime("%H:%M") == "14:30", "EST open"
    assert datetime.fromtimestamp(c2/1000, timezone.utc).strftime("%H:%M") == "21:00", "EST close"
    # 2026-07-02 early close 17:00 UTC (EDT, 13:00 ET)
    _, c3 = rth_bounds_utc_ms(date(2026, 7, 2))
    assert datetime.fromtimestamp(c3/1000, timezone.utc).strftime("%H:%M") == "17:00", "early close"
    # feriados -> None
    assert rth_bounds_utc_ms(date(2026, 5, 25)) is None, "Memorial Day"
    assert rth_bounds_utc_ms(date(2026, 7, 3)) is None, "Independence (obs)"
    assert rth_bounds_utc_ms(date(2026, 6, 6)) is None, "Saturday"
    print("  self-tests OK")


# ----------------- carga -----------------
def load_series(con, sym):
    r = con.execute("SELECT open_time,open,high,low,close,volume FROM klines_5m "
                    "WHERE symbol=? AND interval='5m' ORDER BY open_time", (sym,)).fetchall()
    if len(r) < 2000:
        return None
    a = np.asarray(r, float)
    t = a[:, 0].astype(np.int64)
    idx = {int(v): i for i, v in enumerate(t)}
    return dict(t=t, o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5], idx=idx)


def px_at_open(d, ms):
    i = d["idx"].get(int(ms))
    return (i, d["o"][i]) if i is not None else (None, None)


def px_close_of_bar_ending(d, ms):
    """close del bar de 5m que TERMINA en ms (open_time = ms-BAR)."""
    i = d["idx"].get(int(ms) - BAR)
    return (i, d["c"][i]) if i is not None else (None, None)


def main():
    print("M18 KILL-OR-CONFIRM — Round 8")
    _selftests()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    cand = []
    for (s,) in con.execute("SELECT DISTINCT symbol FROM klines_5m WHERE interval='5m'"):
        base = s[:-4] if s.endswith("USDT") else s
        if base in EXCLUDE:
            continue
        if base in STOCK or base in ETF:
            cand.append((s, "STOCK" if base in STOCK else "ETF"))
    cand.sort()
    print(f"universo ex-ante: {len(cand)} simbolos (accion/ETF US, excl XAU/XAG/SPX)")

    tdays_all = trading_days(date(2025, 12, 1), date(2026, 8, 17))
    tday_index = {d: k for k, d in enumerate(tdays_all)}

    # acumuladores
    horizons_all = list(HOLD_BARS) + ["toclose"]
    def newbuck():
        return {h: [] for h in horizons_all}
    real = {"up": newbuck(), "dn": newbuck(), "all": newbuck()}
    frictionless = {"all": newbuck()}          # desde open[t0] (sin delay de 5min)
    by_liq = {q: newbuck() for q in ("hi", "mid", "lo")}
    by_gapb = {bi: newbuck() for bi in range(len(GAP_BUCKETS))}
    by_gapb_side = {(bi, sd): newbuck() for bi in range(len(GAP_BUCKETS)) for sd in ("up", "dn")}
    by_time = {seg: newbuck() for seg in ("train", "val", "oos")}
    ctrl = {"pre_open": newbuck(), "midday": newbuck(), "deadhour": newbuck(),
            "nextday": newbuck(), "matched": newbuck()}
    reg_rows = {h: [] for h in HOLD_BARS}       # (gap_signed, preopen_signed, trail_vol, signed_fwd)
    diag = dict(events=0, dropped_missing_bar=0, dropped_corp_action=0, dropped_first_tdays=0,
                dropped_no_prevday=0, symbols_used=0, symbols_excl_illiquid=0,
                gap_up=0, gap_dn=0)
    liq_meta = {}

    # rango temporal de eventos para split
    all_event_days = []

    for sym, cat in cand:
        d = load_series(con, sym)
        if d is None:
            continue
        # dias habiles presentes para este simbolo
        first_ms = int(d["t"][0]); last_ms = int(d["t"][-1])
        first_day = datetime.fromtimestamp(first_ms/1000, timezone.utc).date()
        sym_tdays = [x for x in tdays_all if rth_bounds_utc_ms(x)[0] >= first_ms + SKIP_FIRST_TDAYS*86400000
                     and rth_bounds_utc_ms(x)[1] <= last_ms]
        if len(sym_tdays) < 25:
            continue
        # liquidez ex-ante: mediana $ / 5m en el RTH de los primeros 20 dias habiles del simbolo
        firstN = [x for x in tdays_all if rth_bounds_utc_ms(x)[0] >= first_ms][:20]
        liq_vals = []
        for x in firstN:
            o_ms, c_ms = rth_bounds_utc_ms(x)
            m = (d["t"] >= o_ms) & (d["t"] < c_ms)
            if m.any():
                liq_vals.extend((d["o"][m] * d["v"][m]).tolist())
        liq_med = float(np.median(liq_vals)) if liq_vals else 0.0
        if liq_med < FIRST20_LIQ_MIN_USD:
            diag["symbols_excl_illiquid"] += 1
            continue
        liq_meta[sym] = liq_med
        diag["symbols_used"] += 1

        # serie de "daily gap" trailing para vol-normalizacion y matched control
        daily_gap_hist = []

        for D in sym_tdays:
            o_ms, c_ms = rth_bounds_utc_ms(D)
            # dia habil previo con datos
            prev = None
            for back in range(1, 6):
                pd_ = D - timedelta(days=back)
                b = rth_bounds_utc_ms(pd_)
                if b is None:
                    continue
                prev = pd_; pc_ms = b[1]; break
            if prev is None:
                diag["dropped_no_prevday"] += 1; continue
            i_pc, prior_close = px_close_of_bar_ending(d, pc_ms)
            i_o, open_px = px_at_open(d, o_ms)
            if prior_close is None or open_px is None or prior_close <= 0 or open_px <= 0:
                diag["dropped_missing_bar"] += 1; continue
            # verificacion causal dura
            assert pc_ms < o_ms, "prior close must precede open"
            gap = math.log(open_px / prior_close)
            daily_gap_hist.append(gap)
            if abs(gap) > MAX_GAP:
                diag["dropped_corp_action"] += 1; continue
            # entrada = open del bar t0+1
            i_e = d["idx"].get(int(o_ms) + BAR)
            if i_e is None:
                diag["dropped_missing_bar"] += 1; continue
            entry_px = d["o"][i_e]
            assert d["t"][i_e] > o_ms, "entry after signal"
            # exits
            def sret(exit_px, side):
                r = math.log(exit_px / entry_px)
                return -r if side == "up" else r      # up->short, dn->long ; + = reversion paga
            side = "up" if gap > 0 else "dn"
            diag["gap_up" if side == "up" else "gap_dn"] += 1
            diag["events"] += 1
            all_event_days.append(D)

            # trailing daily-gap vol (>=10 previos, causal)
            tv = float(np.std(daily_gap_hist[:-1][-20:])) if len(daily_gap_hist) > 10 else float("nan")
            # pre-open move (90 min antes del open)
            i_pre = d["idx"].get(int(o_ms) - 18 * BAR)
            preo = math.log(open_px / d["o"][i_pre]) if i_pre is not None and d["o"][i_pre] > 0 else float("nan")

            # liquidez -> tercil se asigna despues (necesitamos todos los liq_med); guardamos ref
            rec_h = {}
            for k in HOLD_BARS:
                j = i_e + k
                if j < len(d["c"]):
                    rec_h[k] = sret(d["o"][j], side) if False else sret(d["o"][j], side)
                else:
                    rec_h[k] = None
            # frictionless: desde open[t0]
            rec_fh = {}
            for k in HOLD_BARS:
                j = i_o + k
                if j < len(d["c"]):
                    r = math.log(d["o"][j] / open_px)
                    rec_fh[k] = -r if side == "up" else r
                else:
                    rec_fh[k] = None
            # to close
            i_tc, tcpx = px_close_of_bar_ending(d, c_ms)
            rec_h["toclose"] = (lambda r: -r if side == "up" else r)(math.log(tcpx / entry_px)) if tcpx else None
            rec_fh["toclose"] = None

            # push
            for k in horizons_all:
                v = rec_h[k]
                if v is None:
                    continue
                real["all"][k].append((sym, v)); real[side][k].append((sym, v))
                # gap bucket
                for bi, (lo, hi) in enumerate(GAP_BUCKETS):
                    if lo < abs(gap) <= hi:
                        by_gapb[bi][k].append((sym, v))
                        by_gapb_side[(bi, side)][k].append((sym, v))
                        break
            for k in HOLD_BARS:
                if rec_fh[k] is not None:
                    frictionless["all"][k].append((sym, rec_fh[k]))
                if rec_h[k] is not None and not math.isnan(preo) and not math.isnan(tv):
                    reg_rows[k].append((abs(gap) * (1 if side == "dn" else 1),   # magnitud del gap (siempre +, la direccion ya esta en el signo del target)
                                        (-preo if side == "up" else preo),        # preopen en la misma convencion
                                        tv, rec_h[k]))

            # ---- CONTROLES ----
            # C1 pre_open reversion (mismo entry, apostamos revertir el preo_move)
            if not math.isnan(preo):
                pside = "up" if preo > 0 else "dn"
                for k in HOLD_BARS:
                    j = i_e + k
                    if j < len(d["c"]):
                        r = math.log(d["o"][j] / entry_px)
                        ctrl["pre_open"][k].append((sym, -r if pside == "up" else r))
            # C2 midday 17:00 UTC pseudo-evento
            for tag, hh, wlen in (("midday", 17, 210), ("deadhour", 2, 210)):   # wlen bars ~ 17.5h
                base = int(datetime(D.year, D.month, D.day, hh, 0, tzinfo=timezone.utc).timestamp() * 1000)
                i_ps = d["idx"].get(base)
                i_pw = d["idx"].get(base - wlen * BAR)
                i_pe = d["idx"].get(base + BAR)
                if i_ps is not None and i_pw is not None and i_pe is not None and d["o"][i_pw] > 0:
                    pg = math.log(d["o"][i_ps] / d["o"][i_pw])
                    ps = "up" if pg > 0 else "dn"
                    for k in HOLD_BARS:
                        j = i_pe + k
                        if j < len(d["c"]):
                            r = math.log(d["o"][j] / d["o"][i_pe])
                            ctrl[tag][k].append((sym, -r if ps == "up" else r))
            # C4 nextday: mismo gap/side, forward 24h despues del entry
            i_nd = d["idx"].get(int(d["t"][i_e]) + 288 * BAR)
            if i_nd is not None:
                for k in HOLD_BARS:
                    j = i_nd + k
                    if j < len(d["c"]):
                        r = math.log(d["o"][j] / d["o"][i_nd])
                        ctrl["nextday"][k].append((sym, -r if side == "up" else r))
            # C5 matched: bar aleatorio del mismo simbolo con |move 18h| y vol trailing ~ matcheados
            if not math.isnan(tv) and len(d["c"]) > 400:
                rs = np.random.default_rng(hash((sym, D.toordinal())) & 0xffffffff)
                for _try in range(6):
                    p = int(rs.integers(300, len(d["c"]) - 300))
                    if abs(d["t"][p] - o_ms) < 6 * 3600 * 1000:
                        continue
                    if d["o"][p - 216] <= 0:
                        continue
                    mv = math.log(d["o"][p] / d["o"][p - 216])       # 18h move
                    if abs(abs(mv) - abs(gap)) <= 0.25 * abs(gap) + 1e-9:
                        ms_side = "up" if mv > 0 else "dn"
                        for k in HOLD_BARS:
                            j = p + k
                            if j < len(d["c"]):
                                r = math.log(d["o"][j] / d["o"][p])
                                ctrl["matched"][k].append((sym, -r if ms_side == "up" else r))
                        break

        # fin dias del simbolo

    # ---- asignar terciles de liquidez y rellenar by_liq / by_time ----
    if liq_meta:
        vals = np.array(sorted(liq_meta.values()))
        q1, q2 = np.quantile(vals, [1/3, 2/3])
        liq_tier = {s: ("lo" if v <= q1 else ("mid" if v <= q2 else "hi")) for s, v in liq_meta.items()}
    else:
        liq_tier = {}
    # split temporal 50/25/25 por fecha de evento
    if all_event_days:
        ed = sorted(set(all_event_days))
        n = len(ed)
        t_cut = ed[int(n * 0.5)]; v_cut = ed[int(n * 0.75)]
    else:
        t_cut = v_cut = None

    # re-recorrer real["all"] no guarda la fecha -> re-hacemos by_liq y by_time en un 2do pase liviano
    # (guardamos por evento arriba habria sido mas limpio; hacemos pase 2)
    con.close()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    for sym, cat in cand:
        if sym not in liq_meta:
            continue
        d = load_series(con, sym)
        if d is None:
            continue
        first_ms = int(d["t"][0]); last_ms = int(d["t"][-1])
        sym_tdays = [x for x in tdays_all if rth_bounds_utc_ms(x)[0] >= first_ms + SKIP_FIRST_TDAYS*86400000
                     and rth_bounds_utc_ms(x)[1] <= last_ms]
        tier = liq_tier.get(sym, "mid")
        for D in sym_tdays:
            o_ms, c_ms = rth_bounds_utc_ms(D)
            prev = None
            for back in range(1, 6):
                b = rth_bounds_utc_ms(D - timedelta(days=back))
                if b is not None:
                    prev = D - timedelta(days=back); pc_ms = b[1]; break
            if prev is None:
                continue
            _, prior_close = px_close_of_bar_ending(d, pc_ms)
            i_o, open_px = px_at_open(d, o_ms)
            if not prior_close or not open_px or prior_close <= 0 or open_px <= 0:
                continue
            gap = math.log(open_px / prior_close)
            if abs(gap) > MAX_GAP:
                continue
            i_e = d["idx"].get(int(o_ms) + BAR)
            if i_e is None:
                continue
            entry_px = d["o"][i_e]
            side = "up" if gap > 0 else "dn"
            seg = "train" if (t_cut and D <= t_cut) else ("val" if (v_cut and D <= v_cut) else "oos")
            for k in horizons_all:
                if k == "toclose":
                    i_tc, tcpx = px_close_of_bar_ending(d, c_ms)
                    if not tcpx:
                        continue
                    r = math.log(tcpx / entry_px)
                else:
                    j = i_e + k
                    if j >= len(d["c"]):
                        continue
                    r = math.log(d["o"][j] / entry_px)
                sv = -r if side == "up" else r
                by_liq[tier][k].append((sym, sv))
                by_time[seg][k].append((sym, sv))
    con.close()

    # ---- OLS incremental ----
    def ols(rows):
        if len(rows) < 200:
            return None
        A = np.array([[1.0, g, p, v] for (g, p, v, y) in rows])
        y = np.array([r[3] for r in rows])
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        resid = y - A @ beta
        n, kk = A.shape
        s2 = (resid @ resid) / (n - kk)
        cov = s2 * np.linalg.inv(A.T @ A)
        se = np.sqrt(np.diag(cov))
        return {"beta_gap": round(float(beta[1]), 4), "t_gap": round(float(beta[1] / se[1]), 2),
                "beta_preopen": round(float(beta[2]), 4), "t_preopen": round(float(beta[2] / se[2]), 2),
                "n": n}

    def tab(bk, label):
        print(f"\n--- {label} ---")
        for k in horizons_all:
            R = agg_pairs(bk[k])
            hl = f"{k*5}m" if k != "toclose" else "->close"
            if "mean_bp" not in R:
                print(f"  {hl:>8}: n={R.get('n')}"); continue
            print(f"  {hl:>8}: {R['mean_bp']:>7.2f} bp  CI[{R['ci_bp'][0]:>6.1f},{R['ci_bp'][1]:>6.1f}] excl0={R['ci_excl_0']}  "
                  f"med={R['median_bp']:>6.1f}  h1/h2=({R['half1_bp']:.1f},{R['half2_bp']:.1f})  "
                  f"symPos={R['frac_sym_pos']}  conc={R['top5_conc']}  n={R['n']}")
        return {k: agg_pairs(bk[k]) for k in horizons_all}

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "diag": diag,
           "liq_thresholds_usd_per_5m": {"q1": float(np.quantile(list(liq_meta.values()), 1/3)) if liq_meta else None,
                                          "q2": float(np.quantile(list(liq_meta.values()), 2/3)) if liq_meta else None},
           "n_symbols_by_tier": {t: sum(1 for x in liq_tier.values() if x == t) for t in ("hi", "mid", "lo")}}
    print("\n===== DIAGNOSTICS =====")
    for k, v in diag.items():
        print(f"  {k}: {v}")
    print(f"  event date range: {min(all_event_days) if all_event_days else None} .. {max(all_event_days) if all_event_days else None}")
    print(f"  liq tiers: {out['n_symbols_by_tier']}  thresholds $/5m: {out['liq_thresholds_usd_per_5m']}")

    out["real_all"] = tab(real["all"], "M18 REAL — pooled (signo + = la reversion paga), entry open[t0+1]")
    out["real_up"] = tab(real["up"], "M18 REAL — GAP UP (short)")
    out["real_dn"] = tab(real["dn"], "M18 REAL — GAP DOWN (long)")
    out["frictionless"] = tab(frictionless["all"], "M18 frictionless (desde open[t0], referencia gross-gross)")
    for bi, (lo, hi) in enumerate(GAP_BUCKETS):
        out[f"gapbucket_{bi}"] = tab(by_gapb[bi], f"GAP BUCKET {bi}: {lo*100:.1f}%–{hi*100:.1f}% |gap|")
    for tier in ("hi", "mid", "lo"):
        out[f"liq_{tier}"] = tab(by_liq[tier], f"LIQUIDITY {tier}")
    for seg in ("train", "val", "oos"):
        out[f"time_{seg}"] = tab(by_time[seg], f"TIME SPLIT {seg}")
    out["ctrl_pre_open"] = tab(ctrl["pre_open"], "CONTROL C1 — pre-open move reversion (no gap)")
    out["ctrl_midday"] = tab(ctrl["midday"], "CONTROL C2 — 17:00 UTC pseudo-gap")
    out["ctrl_deadhour"] = tab(ctrl["deadhour"], "CONTROL C3 — 02:00 UTC pseudo-gap")
    out["ctrl_nextday"] = tab(ctrl["nextday"], "CONTROL C4 — same gap, forward +24h")
    out["ctrl_matched"] = tab(ctrl["matched"], "CONTROL C5 — matched vol & 18h-move")

    print("\n--- INCREMENTAL OLS: signed_fwd ~ 1 + |gap| + preopen + trail_vol ---")
    out["ols"] = {}
    for k in HOLD_BARS:
        r = ols(reg_rows[k])
        out["ols"][k] = r
        print(f"  {k*5:>3}m: {r}")

    path = os.path.join(ROOT, "scratch_r8_m18_kill.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()
