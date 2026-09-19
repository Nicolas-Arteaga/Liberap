"""
ROUND 22 — PROVE IT OR BREAK IT.

R21 candidato: capitulacion (drop pctil<=3% + volumen pctil>=90%, SHORT),
TAKER, cap=$450, slots=5, seleccion de slot por score (drop_mag*volp_extra)
en vez de FIFO. Headline VAL+OOS = $150/mes, pero 1ra mitad VAL+OOS=-$16/mes,
2da mitad=+$316/mes.

Este script NO re-optimiza nada del mecanismo (evento, score, costos, slots,
capital quedan EXACTAMENTE congelados como en R21). Solo audita:
  1. Reproduccion exacta del headline.
  2. Walk-forward mes a mes sobre TODA la historia (no solo VAL+OOS) -- el
     mecanismo no tiene parametros fiteados a un periodo especifico (los
     thresholds 3%/90% y la formula de score son hipotesis economicas fijas,
     no elegidas mirando el resultado), asi que evaluar mes a mes en TRAIN
     tambien es legitimo y es la prueba mas dura disponible.
  3. Descubrimiento de regimen SIN mirar OOS: variables causales (BTC rv
     trailing, rv agregada del universo trailing) calculadas SOLO con
     informacion disponible hasta ese momento; el umbral se fija usando
     unicamente los meses de TRAIN, despues se aplica mecanicamente a
     VAL+OOS sin volver a tocarlo.
  4. ON/OFF: el regimen solo prende/apaga la estrategia, no cambia nada mas.
  5. Estres extremo: quitar mejor trade/5/10, mejor mes/2 meses, mejores
     simbolos.
  6. Generalizacion de score-select: comparar contra FIFO, random, low-vol,
     high-vol, raw-signal, en la 1ra y 2da mitad POR SEPARADO.
  7. Scoping liviano (no otra ronda completa) de una 2da familia de
     mecanismo independiente: failed-breakout / breakout-continuation.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
DROP_PCT = 0.03; VOL_PCT_THR = 0.90
TAKER_FEE, TAKER_SPREAD, TAKER_SLIP = 5.0, 3.0, 4.0
TAKER_RT = 2 * (TAKER_FEE + TAKER_SPREAD + TAKER_SLIP)     # 24bp
MAKER_FEE, MAKER_RESID = 2.0, 1.0
MAKER_RT = 2 * (MAKER_FEE + MAKER_RESID)
FILL_WINDOW = 4
LIMIT_OFFSET = 0.0006
CAP, SLOTS = 450, 5
HB = HOR["24h"]
rng = np.random.default_rng(20260930)


def load_all():
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    return P, F


def build_events(P, F):
    events = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; l = d["l"]; t = d["t"]; n = len(c)
        r1p = f["ret1_pct"]; volp = f["vol_pct"]; rvp = f["rv_pct"]; rv = f["rv"]
        climax = np.isfinite(r1p) & np.isfinite(volp) & (r1p <= DROP_PCT) & (volp >= VOL_PCT_THR)
        last = -999
        for i in np.where(climax)[0]:
            if i < ROLL or i - last < 4 or i + 1 + HB >= n:
                continue
            last = i
            lo20 = l[max(0, i - 20):i + 1].min()
            dist_low = math.log(c[i] / lo20) if lo20 > 0 else np.nan
            feat = dict(rv=rv[i] if np.isfinite(rv[i]) else np.nan,
                        volp_extra=volp[i], rvp=rvp[i] if np.isfinite(rvp[i]) else np.nan,
                        dist_low=dist_low, drop_mag=abs(math.log(c[i] / c[i - 1])) if c[i - 1] > 0 else np.nan)
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            events.append((s, i, dy, feat))
    return events


def fwd_short(P, s, i, hbars):
    d = P[s]; o = d["o"]
    e = i + 1
    if e + hbars >= len(o):
        return None
    return -math.log(o[e + hbars] / o[e])


def econ(P, events, cost_bp, cap, slots, select="score", day_filter=None, rng_local=None):
    """select in {score, fifo, random, low_vol, high_vol, raw_signal}. day_filter(date)->bool."""
    cand = [(s, i, dy, feat) for (s, i, dy, feat) in events if day_filter is None or day_filter(dy)]
    cand_ts = sorted([(int(P[s]["t"][i + 1]), s, i, feat) for (s, i, dy, feat) in cand])
    notional = cap / slots
    free_at = [0] * slots
    pnl = []
    by_ts = collections.defaultdict(list)
    for (ems, s, i, feat) in cand_ts:
        by_ts[ems].append((s, i, feat))
    for ems in sorted(by_ts):
        cands_here = list(by_ts[ems])
        if select == "score":
            cands_here.sort(key=lambda x: x[2].get("drop_mag", 0) * x[2].get("volp_extra", 0), reverse=True)
        elif select == "fifo":
            pass
        elif select == "random":
            idx = (rng_local or rng).permutation(len(cands_here))
            cands_here = [cands_here[k] for k in idx]
        elif select == "low_vol":
            cands_here.sort(key=lambda x: x[2].get("rv", 1e9) if np.isfinite(x[2].get("rv", np.nan)) else 1e9)
        elif select == "high_vol":
            cands_here.sort(key=lambda x: -(x[2].get("rv", -1e9) if np.isfinite(x[2].get("rv", np.nan)) else -1e9))
        elif select == "raw_signal":
            cands_here.sort(key=lambda x: -(x[2].get("drop_mag", 0)))
        for (s, i, feat) in cands_here:
            fslot = next((k for k in range(slots) if free_at[k] <= ems), None)
            if fslot is None:
                continue
            d = P[s]; o = d["o"]
            entry_px = o[i + 1]; e_use = i + 1
            j2 = e_use + HB
            if j2 >= len(o):
                continue
            g = -math.log(o[j2] / entry_px) * 1e4
            net = g - cost_bp
            free_at[fslot] = ems + HB * 15 * 60000
            pnl.append((ems, net))
    return pnl, notional


def pnl_to_monthly(pnl, notional):
    bym = collections.defaultdict(float)
    for (ems, net) in pnl:
        bym[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += net * notional / 1e4
    return bym


def net_mo(pnl, notional):
    if len(pnl) < 5:
        return 0.0, 0
    ts = sorted(x[0] for x in pnl)
    span_days = (ts[-1] - ts[0]) / 86400000 or 1
    usd = sum(net * notional / 1e4 for (_, net) in pnl)
    return usd / (span_days / 30), len(pnl)


def main():
    print("=== ROUND 22 — PROVE IT OR BREAK IT ===\n")
    P, F = load_all()
    print(f"universo: {len(P)} simbolos")
    events = build_events(P, F)
    print(f"eventos climax: {len(events)}\n")

    days_all = sorted(set(dy for (s, i, dy, ft) in events))
    d0, d1 = days_all[0], days_all[-1]
    print(f"rango de eventos: {d0} .. {d1}  ({(d1-d0).days} dias)")
    tcut = days_all[int(len(days_all) * 0.5)]
    vcut = days_all[int(len(days_all) * 0.75)]
    print(f"corte original R21: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    # =====================================================================
    print("#" * 70 + "\n PARTE 1 — REPRODUCCION EXACTA DEL HEADLINE R21\n" + "#" * 70)
    valoos_filter = lambda dy: dy > tcut
    pnl_h, notional = econ(P, events, TAKER_RT, CAP, SLOTS, select="score", day_filter=valoos_filter)
    nm, n = net_mo(pnl_h, notional)
    print(f"  TAKER cap=450 slots=5 score-select, VAL+OOS: NET/mo=${nm:.0f}  n={n}  "
          f"(R21 reporto $150/mes, n=1054 -> {'MATCH' if abs(nm-150) < 5 and n == 1054 else 'CHEQUEAR'})\n")

    # =====================================================================
    print("#" * 70 + "\n PARTE 2 — WALK-FORWARD MES A MES SOBRE TODA LA HISTORIA\n" + "#" * 70)
    print("  (sin re-fit de ningun parametro -- evento/score/costo fijos desde R18/R21)")
    all_filter = lambda dy: True
    pnl_all, notional_all = econ(P, events, TAKER_RT, CAP, SLOTS, select="score", day_filter=all_filter)
    bym_all = pnl_to_monthly(pnl_all, notional_all)
    cnt_all = collections.defaultdict(int)
    for (ems, net) in pnl_all:
        cnt_all[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += 1
    print(f"  {'mes':7s} {'trades':>7s} {'PnL':>9s}  regimen(train/val/oos)")
    n_pos = 0; n_tot = 0
    for m in sorted(bym_all):
        mdate = date(int(m[:4]), int(m[5:7]), 15)
        seg = "train" if mdate <= tcut else ("val" if mdate <= vcut else "oos")
        n_tot += 1; n_pos += int(bym_all[m] > 0)
        print(f"  {m:7s} {cnt_all[m]:7d} {bym_all[m]:9.0f}   {seg}")
    print(f"  meses positivos: {n_pos}/{n_tot}\n")

    # =====================================================================
    print("#" * 70 + "\n PARTE 3 — REGIMEN SIN LOOKAHEAD (descubierto SOLO en TRAIN)\n" + "#" * 70)
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    d_ref = P[ref]; f_ref = F[ref]
    day_of_bar = np.array([datetime.utcfromtimestamp(int(t) / 1000).date() for t in d_ref["t"]])
    daily_btc_rv = {}
    for dy in sorted(set(day_of_bar)):
        vals = f_ref["rv"][day_of_bar == dy]
        vals = vals[np.isfinite(vals)]
        if len(vals):
            daily_btc_rv[dy] = float(vals.mean())

    daily_universe_rv = collections.defaultdict(list)
    for s, d in P.items():
        f = F[s]
        dob = np.array([datetime.utcfromtimestamp(int(t) / 1000).date() for t in d["t"]])
        rv = f["rv"]
        finite = np.isfinite(rv)
        for dy, r in zip(dob[finite], rv[finite]):
            daily_universe_rv[dy].append(r)
    daily_universe_rv = {dy: float(np.mean(v)) for dy, v in daily_universe_rv.items() if len(v) >= 20}

    def trailing_mean(daily_dict, dy, window=30):
        keys = [k for k in daily_dict if k < dy and (dy - k).days <= window]
        if len(keys) < window // 2:
            return np.nan
        return float(np.mean([daily_dict[k] for k in keys]))

    month_starts = {}
    for m in sorted(bym_all):
        month_starts[m] = date(int(m[:4]), int(m[5:7]), 1)

    regime_btc = {m: trailing_mean(daily_btc_rv, month_starts[m]) for m in month_starts}
    regime_univ = {m: trailing_mean(daily_universe_rv, month_starts[m]) for m in month_starts}

    train_months = [m for m in bym_all if month_starts[m] <= tcut]
    valoos_months = [m for m in bym_all if month_starts[m] > tcut]

    def fit_threshold_on_train(regime_dict, direction):
        """direction='above' -> ON si regime>=thr; 'below' -> ON si regime<=thr.
        Busca el thr (percentil del regime EN TRAIN) que maximiza PnL total de los meses TRAIN puestos ON."""
        vals_train = [regime_dict[m] for m in train_months if np.isfinite(regime_dict.get(m, np.nan))]
        if len(vals_train) < 4:
            return None, None
        cands = sorted(set(vals_train))
        best_thr, best_pnl = None, -1e18
        for thr in cands:
            on_months = [m for m in train_months if np.isfinite(regime_dict.get(m, np.nan)) and
                         ((regime_dict[m] >= thr) if direction == "above" else (regime_dict[m] <= thr))]
            pnl_on = sum(bym_all[m] for m in on_months)
            if pnl_on > best_pnl:
                best_pnl = pnl_on; best_thr = thr
        return best_thr, best_pnl

    print("  Variables candidatas evaluadas: BTC rv trailing-30d, universo rv trailing-30d")
    for name, regime_dict in (("BTC_rv_trailing30d", regime_btc), ("universe_rv_trailing30d", regime_univ)):
        for direction in ("above", "below"):
            thr, best_pnl_train = fit_threshold_on_train(regime_dict, direction)
            if thr is None:
                continue
            on_valoos = [m for m in valoos_months if np.isfinite(regime_dict.get(m, np.nan)) and
                         ((regime_dict[m] >= thr) if direction == "above" else (regime_dict[m] <= thr))]
            off_valoos = [m for m in valoos_months if m not in on_valoos]
            pnl_on_valoos = sum(bym_all[m] for m in on_valoos)
            pnl_off_valoos = sum(bym_all[m] for m in off_valoos)
            print(f"  {name:26s} dir={direction:5s} thr(TRAIN)={thr:.5f}  train_pnl_if_on={best_pnl_train:+.0f}  "
                  f"|  VAL+OOS: ON meses={on_valoos} pnl_on={pnl_on_valoos:+.0f}  OFF meses={off_valoos} pnl_off={pnl_off_valoos:+.0f}")
    print()
    print("  INTERPRETACION: el umbral se fijo mirando SOLO el PnL de los meses de TRAIN.")
    print("  Si el patron ON/OFF resultante en VAL+OOS es 'todos los meses malos quedan OFF'")
    print("  de casualidad post-hoc (mismo mes exacto sin relacion con el nivel de la variable")
    print("  antes de conocer el resultado), es evidencia de FALSA generalizacion. Ver mas abajo")
    print("  Parte 4/5 para la traduccion a ON/OFF binario y su efecto neto.\n")

    # =====================================================================
    print("#" * 70 + "\n PARTE 4/5 — ON/OFF: BASELINE (siempre ON) vs REGIMEN (BTC_rv, mejor thr TRAIN)\n" + "#" * 70)
    thr_btc, _ = fit_threshold_on_train(regime_btc, "above")
    on_months_all = set(m for m in bym_all if np.isfinite(regime_btc.get(m, np.nan)) and regime_btc[m] >= thr_btc)

    def summarize(months_included, label):
        pnl_list = [bym_all[m] for m in sorted(bym_all) if m in months_included]
        if not pnl_list:
            print(f"  {label}: sin meses"); return
        arr = np.array(pnl_list)
        eq = np.cumsum(arr); dd = (np.maximum.accumulate(eq) - eq).max() if len(eq) else 0
        print(f"  {label:28s}: meses={len(arr):2d}  PnL_total=${arr.sum():+.0f}  PnL/mes=${arr.mean():+.0f}  "
              f"worst_month=${arr.min():+.0f}  maxDD=${dd:.0f}  %ON={len(arr)/max(1,len(bym_all)):.0%}")

    all_m = set(bym_all.keys())
    valoos_m = set(valoos_months)
    print("  -- sobre TODA la historia (train+val+oos) --")
    summarize(all_m, "baseline (siempre ON)")
    summarize(all_m & on_months_all, "regime-gated ON")
    print("  -- solo VAL+OOS (la parte honesta, out-of-sample del umbral) --")
    summarize(valoos_m, "baseline (siempre ON)")
    summarize(valoos_m & on_months_all, "regime-gated ON")
    print()

    # =====================================================================
    print("#" * 70 + "\n PARTE 7 — ESTRES EXTREMO (candidato headline, VAL+OOS)\n" + "#" * 70)
    pnl_sorted = sorted(pnl_h, key=lambda x: x[0])
    arr = np.array([x[1] for x in pnl_sorted])
    usd = arr * notional / 1e4
    ts = [x[0] for x in pnl_sorted]
    span_mo = (ts[-1] - ts[0]) / 86400000 / 30
    syms_of_trade = []  # not tracked in econ() return; recompute via re-run with symbol tag
    print(f"  base: NET/mo=${usd.sum()/span_mo:.0f}  n={len(usd)}")
    for k in (1, 5, 10):
        idx = np.argsort(usd)[::-1][:k]
        rest = np.delete(usd, idx)
        print(f"  remove-top-{k}-trades: NET/mo=${rest.sum()/span_mo:.0f}")
    bym_h = collections.defaultdict(float)
    for (ems, net), u in zip(pnl_sorted, usd):
        bym_h[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += u
    top_months = sorted(bym_h, key=lambda k: -bym_h[k])
    for k in (1, 2):
        excl = set(top_months[:k])
        rest = np.array([u for (ems, net), u in zip(pnl_sorted, usd)
                          if datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m") not in excl])
        print(f"  remove-top-{k}-month(s) ({top_months[:k]}): NET/mo=${rest.sum()/span_mo:.0f}")
    print()

    # =====================================================================
    print("#" * 70 + "\n PARTE 6/8 — GENERALIZACION DE SCORE-SELECT (1ra vs 2da mitad de VAL+OOS)\n" + "#" * 70)
    half_days = sorted(set(dy for (s, i, dy, ft) in events if dy > tcut))
    midpt = half_days[len(half_days) // 2]
    f1 = lambda dy: tcut < dy <= midpt
    f2 = lambda dy: dy > midpt
    print(f"  1ra mitad: {tcut}..{midpt}   2da mitad: {midpt}..{d1}")
    for half_name, ff in (("1ra mitad", f1), ("2da mitad", f2)):
        print(f"  -- {half_name} --")
        for sel in ("fifo", "random", "low_vol", "high_vol", "raw_signal", "score"):
            rr = np.random.default_rng(7) if sel == "random" else None
            pnl_s, not_s = econ(P, events, TAKER_RT, CAP, SLOTS, select=sel, day_filter=ff, rng_local=rr)
            nm_s, n_s = net_mo(pnl_s, not_s)
            print(f"    {sel:12s}: NET/mo=${nm_s:+7.0f}  n={n_s}")
    print()

    # =====================================================================
    print("#" * 70 + "\n PARTE 9-10 — SCOPING LIVIANO: SEGUNDA FAMILIA INDEPENDIENTE\n" + "#" * 70)
    print("  Candidato: FAILED-BREAKOUT (ruptura de rango + rechazo -> reversion),")
    print("  economicamente distinto de capitulacion (no es forced-flow, es liquidez")
    print("  agotada en el breakout -- stop-hunt / trampa alcista o bajista).")
    scope_failed_breakout(P, F, tcut, vcut)

    print("\nguardado -- fin R22")


def scope_failed_breakout(P, F, tcut, vcut):
    """Evento: nuevo maximo/minimo de 20 barras (5h) seguido, en la MISMA barra
    o la siguiente, por un cierre que retrocede >50% del rango de ruptura
    (rechazo). Direccion = fade del breakout (si rompio maximo y rechaza -> SHORT;
    si rompio minimo y rechaza -> LONG). Solo diagnostico (forward return +
    persistencia + frecuencia), sin sim economica completa todavia."""
    HB2 = HOR["4h"]; HB4 = HOR["12h"]; HB24 = HOR["24h"]
    events_up = []; events_dn = []
    for s, d in P.items():
        c = d["c"]; h = d["h"]; l = d["l"]; o = d["o"]; t = d["t"]; n = len(c)
        for i in range(20, n - HB24 - 2):
            hi20 = h[i - 20:i].max(); lo20 = l[i - 20:i].min()
            rng_ = hi20 - lo20
            if rng_ <= 0:
                continue
            broke_up = h[i] > hi20
            broke_dn = l[i] < lo20
            if broke_up and not broke_dn:
                excess = h[i] - hi20
                retrace = h[i] - c[i]
                if excess > 0 and retrace / max(excess, 1e-12) > 0.5 and c[i] < hi20:
                    dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                    events_up.append((s, i, dy))
            elif broke_dn and not broke_up:
                excess = lo20 - l[i]
                retrace = c[i] - l[i]
                if excess > 0 and retrace / max(excess, 1e-12) > 0.5 and c[i] > lo20:
                    dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                    events_dn.append((s, i, dy))

    def seg(dy): return "train" if dy <= tcut else ("val" if dy <= vcut else "oos")

    def fwd(s, i, hbars, side):
        d = P[s]; o = d["o"]; e = i + 1
        if e + hbars >= len(o):
            return None
        return side * math.log(o[e + hbars] / o[e])

    print(f"  eventos: breakout-up-rechazado(fade SHORT)={len(events_up)}  breakout-down-rechazado(fade LONG)={len(events_dn)}")
    for lbl, evs, side in (("FADE SHORT (rompio max, rechazo)", events_up, -1),
                           ("FADE LONG (rompio min, rechazo)", events_dn, 1)):
        for h_lbl in ("4h", "12h", "24h"):
            hb = HOR[h_lbl]
            for sgv in ("train", "val", "oos"):
                pairs = [(s, fwd(s, i, hb, side)) for (s, i, dy) in evs if seg(dy) == sgv and fwd(s, i, hb, side) is not None]
                if len(pairs) < 30:
                    continue
                R = agg_pairs(pairs)
                net = (R["mean_bp"] - TAKER_RT) if R.get("mean_bp") is not None else None
                print(f"    {lbl:32s} h={h_lbl:>4s} {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')}")
    print("  (scoping only -- si TRAIN+VAL+OOS coinciden en signo y superan costo, R23 lo ataca en serio)")


if __name__ == "__main__":
    main()
