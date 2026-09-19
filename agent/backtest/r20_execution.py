"""
ROUND 20 — EXECUTION ALPHA + REALISTIC FILL ATTACK.

Ataca el hallazgo de R19 (hora UTC + compresión previa, el único que el
placebo NO reprodujo) con ejecución realista: descompone el piso de 24bp,
modela maker con fill mecánico (no asumido) + adverse selection, prueba
timing de entrada/salida, y corre la sim económica con capital real.

COSTO — DESCOMPUESTO (Fase 1, estrategia direccional de 1 pata, NO el modelo
de 2 patas de R16/R17 que es para carry delta-neutral):
  TAKER: fee 5bp + spread-cross 3bp + impacto/slippage 4bp = 12bp/lado
         -> 24bp round-trip (entrada+salida taker).
  MAKER: fee 2bp + spread-cross 0bp (por definición, no cruza) + residual 1bp
         = 3bp/lado -> 6bp round-trip SI llena. Pero el fill NO se asume:
         se modela mecánicamente (ver abajo) + escenarios de sensibilidad.
"""
import os, sys, json, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL
from datetime import datetime, timezone, date

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")

TAKER_FEE, TAKER_SPREAD, TAKER_SLIP = 5.0, 3.0, 4.0
TAKER_RT = 2 * (TAKER_FEE + TAKER_SPREAD + TAKER_SLIP)     # 24bp
MAKER_FEE, MAKER_RESID = 2.0, 1.0
MAKER_RT = 2 * (MAKER_FEE + MAKER_RESID)                    # 6bp si llena ambos lados
HOR_BARS = {"30m": 2, "1h": 4, "2h": 8, "4h": 16}
FILL_WINDOW = 4       # barras (1h) para intentar el fill del limit
LIMIT_OFFSET = 0.0006  # 6bp de mejora sobre el precio de señal (retroceso exigido)
HOURS_TO_TEST = [20, 21, 22, 23, 0, 1]
rng = np.random.default_rng(20260924)


def main():
    print("=== ROUND 20 — EXECUTION ALPHA + REALISTIC FILL ATTACK ===")
    print(f"TAKER RT = {TAKER_RT}bp (fee {2*TAKER_FEE} + spread {2*TAKER_SPREAD} + slip {2*TAKER_SLIP})")
    print(f"MAKER RT = {MAKER_RT}bp SI llena ambos lados (fee {2*MAKER_FEE} + residual {2*MAKER_RESID}) -- fill NO asumido, modelado abajo\n")

    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()
    print(f"universo: {len(P)} símbolos")

    days_all = []
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    for t in P[ref]["t"]:
        days_all.append(datetime.utcfromtimestamp(int(t) / 1000).date())
    days_all = sorted(set(days_all))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}")

    # ---------- construir eventos (hora H + compresión), entrada causal open[t+1] ----------
    def build_events(H):
        ev = []
        for s, d in P.items():
            f = F[s]; c = d["c"]; o = d["o"]; h = d["h"]; l = d["l"]; t = d["t"]; n = len(c)
            for i in range(ROLL, n - max(HOR_BARS.values()) - FILL_WINDOW - 2):
                hh = datetime.utcfromtimestamp(int(t[i]) / 1000).hour
                if hh != H or not (np.isfinite(f["rv_pct"][i]) and f["rv_pct"][i] < 0.25):
                    continue
                dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                ev.append((s, i, dy))
        return ev

    # ---------- FASE 12: familia horaria -- direccion fijada en TRAIN, testeada en VAL+OOS ----------
    print("\n" + "#" * 70 + "\n# FAMILIA HORARIA — hora H + compresión, dirección fijada en TRAIN\n" + "#" * 70)
    hour_dir = {}
    hour_events = {}
    for H in HOURS_TO_TEST:
        ev = build_events(H)
        hour_events[H] = ev
        train_rets = []
        for (s, i, dy) in ev:
            if seg(dy) != "train":
                continue
            d = P[s]; e = i + 1
            if e + 4 >= len(d["o"]):
                continue
            train_rets.append(math.log(d["o"][e + 4] / d["o"][e]))
        if len(train_rets) < 30:
            print(f"  H={H:02d}: TRAIN insuficiente, se omite"); continue
        # dirección = sign(mean_train): apostar EN el sentido del retorno crudo medio en TRAIN
        # (si TRAIN cae, side=-1=SHORT; position_pnl = side*price_return > 0 en TRAIN por construcción)
        hour_dir[H] = np.sign(np.mean(train_rets)) or 1
        vr, orr = [], []
        for (s, i, dy) in ev:
            d = P[s]; e = i + 1
            if e + 4 >= len(d["o"]):
                continue
            r = hour_dir[H] * math.log(d["o"][e + 4] / d["o"][e])
            if seg(dy) == "val":
                vr.append((s, r))
            elif seg(dy) == "oos":
                orr.append((s, r))
        Rv = agg_pairs(vr); Ro = agg_pairs(orr)
        print(f"  H={H:02d} dir={'LONG' if hour_dir[H]>0 else 'SHORT'} (fijada en TRAIN, n_train={len(train_rets)}): "
              f"VAL={Rv.get('mean_bp')}bp(n={Rv.get('n')})  OOS={Ro.get('mean_bp')}bp(n={Ro.get('n')})")

    H_BEST = 22
    print(f"\n>>> se profundiza con H={H_BEST} (hallazgo de R19), dirección={'SHORT' if hour_dir.get(H_BEST,-1)<0 else 'LONG'}")
    events = hour_events[H_BEST]
    side = hour_dir.get(H_BEST, -1)

    # ---------- FASE 2: TAKER baseline por horizonte, TRAIN/VAL/OOS ----------
    print("\n" + "#" * 70 + "\n# TAKER BASELINE (entrada open[t+1], costo 24bp RT)\n" + "#" * 70)
    def fwd(s, i, hbars):
        d = P[s]; e = i + 1
        if e + hbars >= len(d["o"]):
            return None
        return side * math.log(d["o"][e + hbars] / d["o"][e])
    for h_lbl, hb in HOR_BARS.items():
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd(s, i, hb)) for (s, i, dy) in events if seg(dy) == sgv and fwd(s, i, hb) is not None]
            R = agg_pairs(pairs)
            gross = R.get("mean_bp")
            net = (gross - TAKER_RT) if gross is not None else None
            print(f"  h={h_lbl:>3} {sgv:5s}: gross={gross}bp  net_taker={net}bp  n={R.get('n')}")

    # ---------- FASE 3-5: MAKER con fill mecánico + adverse selection ----------
    print("\n" + "#" * 70 + f"\n# MAKER — fill mecánico (limit {LIMIT_OFFSET*1e4:.0f}bp mejor, ventana {FILL_WINDOW} barras) + adverse selection\n" + "#" * 70)
    hb = HOR_BARS["1h"]
    maker_filled = []; maker_missed = 0; taker_all = []
    for (s, i, dy) in events:
        d = P[s]; o = d["o"]; h = d["h"]; l = d["l"]
        sig_px = o[i + 1]           # precio de referencia al momento de la señal (open[t+1], igual que taker)
        if side < 0:   # SHORT -> limit SELL por encima del precio de señal
            limit_px = sig_px * (1 + LIMIT_OFFSET)
            filled_i = None
            for k in range(1, FILL_WINDOW + 1):
                j = i + 1 + k
                if j >= len(h):
                    break
                if h[j] >= limit_px:
                    filled_i = j; break
        else:          # LONG -> limit BUY por debajo
            limit_px = sig_px * (1 - LIMIT_OFFSET)
            filled_i = None
            for k in range(1, FILL_WINDOW + 1):
                j = i + 1 + k
                if j >= len(l):
                    break
                if l[j] <= limit_px:
                    filled_i = j; break
        rt = fwd(s, i, hb)
        if rt is not None:
            taker_all.append((s, rt))
        if filled_i is None:
            maker_missed += 1
            continue
        e2 = filled_i
        if e2 + hb >= len(o):
            continue
        r_maker = side * math.log(o[e2 + hb] / limit_px)
        maker_filled.append((s, r_maker))
    n_total = len(events)
    fill_rate_mech = 1 - maker_missed / max(1, n_total)
    Rt = agg_pairs(taker_all); Rm = agg_pairs(maker_filled)
    print(f"  eventos totales={n_total}  fill mecánico observado={fill_rate_mech:.2%}  (missed={maker_missed})")
    print(f"  TAKER  (todos):        gross={Rt.get('mean_bp')}bp  net={Rt.get('mean_bp')-TAKER_RT if Rt.get('mean_bp') is not None else None}bp  n={Rt.get('n')}")
    print(f"  MAKER  (solo llenados): gross={Rm.get('mean_bp')}bp  net={Rm.get('mean_bp')-MAKER_RT if Rm.get('mean_bp') is not None else None}bp  n={Rm.get('n')}")
    print("  -> ADVERSE SELECTION: comparar gross MAKER-filled vs gross TAKER-todos. Si MAKER-filled < TAKER-todos,")
    print("     los fills ocurren preferentemente en el peor subconjunto de casos (selección adversa real).")

    print("\n  Escenarios de fill-rate (conservador→optimista), NET esperado combinando missed=0-PnL:")
    for fr_scenario, lbl in ((0.25, "conservador 25%"), (0.50, "base 50%"), (0.75, "optimista 75%"), (0.90, "90%"), (1.00, "100% (NO asumido como caso base)")):
        # EV ponderado: fr_scenario * (maker net si llena) + (1-fr_scenario) * 0 (trade perdido, sin costo ni PnL)
        if Rm.get("mean_bp") is not None:
            net_maker = Rm["mean_bp"] - MAKER_RT
            ev_bp = fr_scenario * net_maker
            print(f"    fill={fr_scenario:.0%} ({lbl}): net esperado por señal = {ev_bp:+.2f}bp  (vs taker net fijo = {Rt.get('mean_bp')-TAKER_RT:+.2f}bp por señal, 100% ejecutable)")

    # ---------- FASE 7-8: timing de entrada (ventanas alrededor de la hora) ----------
    print("\n" + "#" * 70 + "\n# TIMING DE ENTRADA — ventanas alrededor de la señal horaria\n" + "#" * 70)
    OFFSETS = {"-15m": -1, "-5m": 0, "0(señal)": 1, "+5m": 1, "+15m": 2, "+30m": 3}
    # nota: a 15m de grid, -15m=1 barra antes, +15m=1 barra despues, +30m=2 barras despues
    OFFSETS = {"t-1(−15m)": -1, "t(señal, open[t+1])": 0, "t+1(+15m tarde)": 1, "t+2(+30m tarde)": 2}
    for lbl, off in OFFSETS.items():
        pairs = []
        for (s, i, dy) in events:
            d = P[s]; o = d["o"]
            e = i + 1 + off
            j = e + hb
            if e < 0 or j >= len(o):
                continue
            pairs.append((s, side * math.log(o[j] / o[e])))
        R = agg_pairs(pairs)
        net = (R.get("mean_bp") - TAKER_RT) if R.get("mean_bp") is not None else None
        print(f"  entrada {lbl:22s}: gross={R.get('mean_bp')}bp  net_taker={net}bp  n={R.get('n')}")

    # ---------- FASE 9: salida -- horizonte fijo vs TP/SL desde percentiles de TRAIN ----------
    print("\n" + "#" * 70 + "\n# SALIDA — horizonte fijo vs TP/SL (percentiles de MFE/MAE en TRAIN, aplicado a VAL+OOS)\n" + "#" * 70)
    from r18_discovery import mfe_mae
    train_mm = []
    for (s, i, dy) in events:
        if seg(dy) != "train":
            continue
        d = P[s]; e = i + 1
        r = mfe_mae(d["o"], d["h"], d["l"], e, hb, side)
        if r:
            train_mm.append(r)
    if train_mm:
        mfe_arr = np.array([x[1] for x in train_mm]); mae_arr = np.array([x[2] for x in train_mm])
        tp = float(np.percentile(mfe_arr, 60)); sl = float(np.percentile(mae_arr, 40))   # predeclarado, congelado en TRAIN
        print(f"  TP congelado (p60 MFE en TRAIN) = {tp*1e4:.0f}bp   SL congelado (p40 MAE en TRAIN) = {sl*1e4:.0f}bp")
        for sgv in ("val", "oos"):
            outs = []
            for (s, i, dy) in events:
                if seg(dy) != sgv:
                    continue
                d = P[s]; e = i + 1
                if e + hb >= len(d["o"]):
                    continue
                entry = d["o"][e]
                hit_tp = hit_sl = None
                for k in range(hb + 1):
                    j = e + k
                    if j >= len(d["o"]):
                        break
                    hi_, lo_ = d["h"][j], d["l"][j]
                    fav = math.log(hi_ / entry) if side > 0 else -math.log(lo_ / entry)
                    adv = math.log(lo_ / entry) if side > 0 else -math.log(hi_ / entry)
                    if fav >= tp:
                        hit_tp = k; break
                    if adv <= sl:
                        hit_sl = k; break
                if hit_tp is not None:
                    outs.append(tp)
                elif hit_sl is not None:
                    outs.append(sl)
                else:
                    j = e + hb
                    outs.append(side * math.log(d["o"][j] / entry))
            arr = np.array(outs) * 1e4
            print(f"    {sgv}: TP/SL gross_mean={arr.mean():+.1f}bp  net_taker={arr.mean()-TAKER_RT:+.1f}bp  WR={(arr>0).mean():.2f}  n={len(arr)}")

    # ---------- FASE 10-11: capital real, taker vs maker (fill mecánico), concurrencia ----------
    print("\n" + "#" * 70 + "\n# SIM ECONÓMICA — capital real (TAKER 100% ejecutable vs MAKER fill mecánico)\n" + "#" * 70)
    ev_sorted_taker = sorted([(int(P[s]["t"][i + 1]), s, i + 1) for (s, i, dy) in events if i + 1 + hb < len(P[s]["o"])])
    def econ(ev_list, cost_bp, cap, slots, use_maker=False):
        notional = cap / slots
        free_at = [0] * slots
        pnl = []
        for (ems, s, ei) in ev_list:
            fslot = next((k for k in range(slots) if free_at[k] <= ems), None)
            if fslot is None:
                continue
            d = P[s]; o = d["o"]
            if use_maker:
                sig_px = o[ei]
                h_, l_ = d["h"], d["l"]
                limit_px = sig_px * (1 + LIMIT_OFFSET) if side < 0 else sig_px * (1 - LIMIT_OFFSET)
                filled_i = None
                for k in range(1, FILL_WINDOW + 1):
                    j = ei + k
                    if j >= len(o):
                        break
                    if (side < 0 and h_[j] >= limit_px) or (side > 0 and l_[j] <= limit_px):
                        filled_i = j; break
                if filled_i is None:
                    continue   # missed, no ocupa slot ni genera PnL
                entry_px = limit_px; e_use = filled_i
            else:
                entry_px = o[ei]; e_use = ei
            j2 = e_use + hb
            if j2 >= len(o):
                continue
            g = side * math.log(o[j2] / entry_px) * 1e4
            net = g - cost_bp
            free_at[fslot] = ems + hb * 15 * 60000
            pnl.append((ems, net))
        return pnl

    for label, use_maker, cost_bp in (("TAKER", False, TAKER_RT), ("MAKER (fill mecánico)", True, MAKER_RT)):
        for cap in (150, 300, 450):
            for slots in (1, 2, 3, 5):
                pnl = econ(ev_sorted_taker, cost_bp, cap, slots, use_maker=use_maker)
                if len(pnl) < 10:
                    continue
                span_days = (pnl[-1][0] - pnl[0][0]) / 86400000 or 1
                arr = np.array([x[1] for x in pnl])
                notional = cap / slots
                usd = arr * notional / 1e4
                net_mo = usd.sum() / (span_days / 30)
                bym = collections.defaultdict(float)
                for (ems, net) in pnl:
                    bym[datetime.utcfromtimestamp(ems / 1000).strftime("%Y-%m")] += net * notional / 1e4
                months = np.array(sorted(bym.values()))
                eq = np.cumsum(usd); dd = (np.maximum.accumulate(eq) - eq).max()
                flag = "  <<< SUPERA 150" if net_mo >= 150 else ("  (near-PASS 75-149)" if 75 <= net_mo < 150 else "")
                if slots in (1, 5) or net_mo > 0:
                    print(f"  {label:22s} cap=${cap} slots={slots}: trades={len(pnl)} trades/mo={len(pnl)/(span_days/30):.0f} "
                          f"avg_net={arr.mean():+.1f}bp WR={(arr>0).mean():.2f} NET/mo=${net_mo:.0f} maxDD=${dd:.0f} "
                          f"m[min/med/max]=[{months.min():.0f}/{np.median(months):.0f}/{months.max():.0f}]{flag}")

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_events_H22": len(events)}
    json.dump(out, open(os.path.join(ROOT, "scratch_r20_execution.json"), "w"), indent=1, default=str)
    print("\nguardado scratch_r20_execution.json")


if __name__ == "__main__":
    main()
