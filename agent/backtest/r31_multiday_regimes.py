"""
ROUND 31 — CAMBIO DE HORIZONTE: persistencia multi-dia (3/7/14/30d), no
scalping intradia. 8 familias predeclaradas, ranking cross-sectional,
rebalanceo diario, top/bottom-3 (calza directo con 3 slots reales).

Complejidad controlada: W=H (la ventana de score = el horizonte de
holding), solo 4 valores {3,7,14,30} por familia -> 4 variantes, no
cientos. Direccion (long-top vs long-bottom) SIEMPRE decidida en TRAIN.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r15_wide_discovery import universe, load_symbol
from r29_oi_sequences import feature_complete_universe, load_symbol_oi
from datetime import datetime, date

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST_RT = 24.0   # 1 entrada + 1 salida por ciclo de holding, taker, mismo modelo de siempre
CAP, SLOTS = 450, 3
WINDOWS = [3, 7, 14, 30]


def daily_close_series(d):
    """agrega 15m -> diario: close de la ultima barra de cada dia UTC, causal (no mira el futuro del dia)."""
    t = d["t"]; c = d["c"]
    days = np.array([datetime.utcfromtimestamp(int(x) / 1000).date() for x in t])
    uniq = sorted(set(days))
    close_by_day = {}
    open_by_day = {}
    for dy in uniq:
        idx = np.where(days == dy)[0]
        close_by_day[dy] = c[idx[-1]]
        open_by_day[dy] = d["o"][idx[0]]
    return uniq, close_by_day, open_by_day


def daily_oi_snapshot(d):
    """OI: primer valor disponible del dia (snapshot de apertura, causal)."""
    t = d["t"]; oi = d["oi"]
    days = np.array([datetime.utcfromtimestamp(int(x) / 1000).date() for x in t])
    uniq = sorted(set(days))
    oi_by_day = {}
    for dy in uniq:
        idx = np.where(days == dy)[0]
        vals = oi[idx]
        vals = vals[np.isfinite(vals)]
        oi_by_day[dy] = vals[0] if len(vals) else np.nan
    return oi_by_day


def load_wide_daily():
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    out = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        days, close_by_day, open_by_day = daily_close_series(d)
        out[s] = dict(days=days, close=close_by_day, open=open_by_day, dayidx={dy: i for i, dy in enumerate(days)})
    con.close()
    return out


def load_oi_daily():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    fc = feature_complete_universe(con)
    out = {}
    for s in fc:
        d = load_symbol_oi(con, s)
        if d is None:
            continue
        days, close_by_day, open_by_day = daily_close_series(d)
        oi_by_day = daily_oi_snapshot(d)
        out[s] = dict(days=days, close=close_by_day, open=open_by_day, oi=oi_by_day, dayidx={dy: i for i, dy in enumerate(days)})
    con.close()
    return out


def zscore(vals):
    arr = np.array(vals, float)
    m, s = np.nanmean(arr), np.nanstd(arr)
    if s <= 0 or not np.isfinite(s):
        return np.zeros_like(arr)
    return (arr - m) / s


def run_ranking_backtest(universe_daily, score_fn, W, seg, top=True, n_pick=3):
    """score_fn(entry_dict, day, W) -> score o None si no calculable.
    Rebalanceo DIARIO: cada dia se recalcula el ranking, se toman los
    n_pick de mayor (o menor) score, se mide forward return a W dias desde
    open del dia siguiente. Slots limitados a n_pick=3 (representa el
    sistema real: 3 posiciones)."""
    all_days = sorted(set().union(*[set(v["days"]) for v in universe_daily.values()]))
    day_idx = {dy: i for i, dy in enumerate(all_days)}
    pnl = []   # (day, ret_bp) por posicion tomada
    for i, dy in enumerate(all_days):
        if i + W >= len(all_days):
            break
        scores = []
        for s, v in universe_daily.items():
            sc = score_fn(v, dy, W)
            if sc is not None and np.isfinite(sc):
                scores.append((s, sc))
        if len(scores) < 10:
            continue
        scores.sort(key=lambda x: -x[1] if top else x[1])
        picks = scores[:n_pick]
        entry_day = all_days[i + 1] if i + 1 < len(all_days) else None
        exit_day = all_days[i + 1 + W] if i + 1 + W < len(all_days) else None
        if entry_day is None or exit_day is None:
            continue
        for (s, sc) in picks:
            v = universe_daily[s]
            if entry_day not in v["open"] or exit_day not in v["close"]:
                continue
            entry_px = v["open"][entry_day]; exit_px = v["close"][exit_day]
            if entry_px <= 0:
                continue
            r_bp = math.log(exit_px / entry_px) * 1e4
            pnl.append((dy, seg(dy), r_bp))
    return pnl


def summarize(pnl, seg_filter, cost_bp=COST_RT, notional=CAP / SLOTS):
    rows = [(dy, r) for (dy, sgv, r) in pnl if sgv == seg_filter]
    if len(rows) < 30:
        return None
    arr = np.array([r for (_, r) in rows])
    net = arr - cost_bp
    usd = net * notional / 1e4
    days_sorted = sorted(set(dy for (dy, _) in rows))
    span_days = (days_sorted[-1] - days_sorted[0]).days or 1
    net_mo = usd.sum() / (span_days / 30)
    return dict(n=len(arr), gross_mean=arr.mean(), net_mean=net.mean(), win_rate=(net > 0).mean(),
                net_mo=net_mo, span_days=span_days)


def main():
    print("=== ROUND 31 — CAMBIO DE HORIZONTE: PERSISTENCIA MULTI-DIA ===\n")
    wide = load_wide_daily()
    oi = load_oi_daily()
    print(f"universo wide (precio/volumen diario): {len(wide)} simbolos")
    print(f"universo OI (feature-complete, diario): {len(oi)} simbolos\n")

    ref_days = wide["BTCUSDT"]["days"] if "BTCUSDT" in wide else next(iter(wide.values()))["days"]
    tcut = ref_days[int(len(ref_days) * 0.5)]
    vcut = ref_days[int(len(ref_days) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    def mom_score(v, dy, W):
        i = v["dayidx"].get(dy)
        if i is None or i - W < 0:
            return None
        idx = v["days"]
        d0, d1 = idx[i - W], idx[i]
        if d0 not in v["close"] or d1 not in v["close"] or v["close"][d0] <= 0:
            return None
        return math.log(v["close"][d1] / v["close"][d0])

    def oi_chg_score(v, dy, W):
        i = v["dayidx"].get(dy)
        if i is None or i - W < 0:
            return None
        idx = v["days"]
        d0, d1 = idx[i - W], idx[i]
        o0, o1 = v["oi"].get(d0), v["oi"].get(d1)
        if o0 is None or o1 is None or not (np.isfinite(o0) and np.isfinite(o1)) or o0 <= 0:
            return None
        return (o1 - o0) / o0

    def combo_score(v, dy, W, mode):
        m = mom_score(v, dy, W); o = oi_chg_score(v, dy, W)
        if m is None or o is None:
            return None
        return (o + m) if mode == "align" else (o - m)

    families = {
        "A-momentum(long_top)": (wide, lambda v, dy, W: mom_score(v, dy, W), True),
        "B-reversal(long_bottom)": (wide, lambda v, dy, W: mom_score(v, dy, W), False),
        "C-OI_accum(long_top)": (oi, lambda v, dy, W: oi_chg_score(v, dy, W), True),
        "D-OI_distrib(long_bottom_OI)": (oi, lambda v, dy, W: oi_chg_score(v, dy, W), False),
        "E-OI+mom_align(long_top)": (oi, lambda v, dy, W: combo_score(v, dy, W, "align"), True),
        "F-OI+mom_disagree(long_top)": (oi, lambda v, dy, W: combo_score(v, dy, W, "disagree"), True),
    }

    print("#" * 70 + "\n BASELINES\n" + "#" * 70)
    if "BTCUSDT" in wide:
        btc = wide["BTCUSDT"]
        for sgv in ("train", "val", "oos"):
            days_seg = [dy for dy in btc["days"] if seg(dy) == sgv]
            if len(days_seg) < 30:
                continue
            d0, d1 = days_seg[0], days_seg[-1]
            ret = math.log(btc["close"][d1] / btc["close"][d0]) * 1e4
            span = (d1 - d0).days or 1
            print(f"  BTC buy&hold {sgv:5s}: total={ret:.0f}bp  ~{ret/ (span/30):.0f}bp/mes equivalente (sin costo, referencia)")
    rng = np.random.default_rng(31)
    rand_days = wide[next(iter(wide))]["days"]
    for sgv in ("train", "val", "oos"):
        picks_ret = []
        for dy in rand_days:
            if seg(dy) != sgv:
                continue
            syms = list(wide.keys())
            chosen = rng.choice(syms, 3, replace=False)
            for s in chosen:
                v = wide[s]
                i = v["dayidx"].get(dy)
                if i is not None:
                    if i + 7 < len(v["days"]):
                        d1 = v["days"][i + 7]
                        if dy in v["open"] and d1 in v["close"] and v["open"][dy] > 0:
                            picks_ret.append(math.log(v["close"][d1] / v["open"][dy]) * 1e4)
        if len(picks_ret) >= 30:
            arr = np.array(picks_ret)
            print(f"  Random 3-symbol basket (hold 7d) {sgv:5s}: gross_mean={arr.mean():.1f}bp n={len(arr)}")

    print("\n" + "#" * 70 + "\n FAMILIAS — TRAIN elige W y direccion, VAL confirma, OOS valida\n" + "#" * 70)
    best_overall = None
    for label, (uni, score_fn, top) in families.items():
        print(f"\n  -- {label} --")
        best_train = None
        for W in WINDOWS:
            pnl = run_ranking_backtest(uni, score_fn, W, seg, top=top)
            Rt = summarize(pnl, "train")
            if Rt is None:
                continue
            if best_train is None or Rt["net_mean"] > best_train[1]["net_mean"]:
                best_train = (W, Rt, pnl)
            print(f"    W={W:2d}d TRAIN: n={Rt['n']:4d} gross={Rt['gross_mean']:+.1f}bp net={Rt['net_mean']:+.1f}bp "
                  f"WR={Rt['win_rate']:.2f} NET/mes(${CAP})=${Rt['net_mo']:.0f}")
        if best_train is None:
            print("    sin datos suficientes en TRAIN")
            continue
        W, Rt, pnl = best_train
        Rv = summarize(pnl, "val")
        if Rv is None or Rv["net_mean"] <= 0:
            print(f"    [W={W}d elegido por TRAIN] VAL no confirma (net={Rv['net_mean'] if Rv else None}bp) -> DESCARTADO")
            continue
        Ro = summarize(pnl, "oos")
        if Ro is None:
            print(f"    [W={W}d] VAL confirma (net={Rv['net_mean']:+.1f}bp) pero OOS sin datos suficientes")
            continue
        print(f"    [W={W}d elegido por TRAIN] VAL net={Rv['net_mean']:+.1f}bp (CONFIRMA) -> "
              f"OOS: n={Ro['n']} gross={Ro['gross_mean']:+.1f}bp net={Ro['net_mean']:+.1f}bp WR={Ro['win_rate']:.2f} "
              f"NET/mes(${CAP})=${Ro['net_mo']:.0f}")
        if best_overall is None or (Ro["net_mo"] > best_overall[1]["net_mo"]):
            best_overall = (f"{label} W={W}d", Ro, Rv, Rt)

    print("\n" + "#" * 70 + "\n RESULTADO\n" + "#" * 70)
    if best_overall is None:
        print("  NINGUNA familia sobrevivio TRAIN->VAL(confirma)->OOS con datos suficientes.")
    else:
        label, Ro, Rv, Rt = best_overall
        print(f"  Mejor candidato: {label}")
        print(f"    TRAIN net/mes=${Rt['net_mo']:.0f}  VAL net={Rv['net_mean']:+.1f}bp  OOS net/mes=${Ro['net_mo']:.0f}  n_oos={Ro['n']}")

    print("\nfin R31 discovery")


if __name__ == "__main__":
    main()
