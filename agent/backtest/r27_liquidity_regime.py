"""
ROUND 27 — LIQUIDITY REGIME -> ALPHA.

R26 encontro que 22:00 UTC es una hora de BAJA actividad (no alta), lo cual
sugiere que el efecto de R19-R21 podria ser un proxy imperfecto de un
fenomeno mas general: iliquidez temporal por simbolo. Este script
construye el regimen de iliquidez CAUSAL (percentil de volumen propio del
simbolo, no un promedio de mercado ni la hora del reloj) y prueba:
  - Estado solo (iliquido) -> forward return, direccion TRAIN-decidida.
  - Estado + evento (iliquido + movimiento extremo) -> forward return.
  - Modelo A (hora==22) vs B (iliquidez causal por simbolo) vs C
    (iliquidez cross-sectional, cuantos simbolos iliquidos a la vez).
  - Controles: BTC solo, majors, excluyendo la hora 22, volumen-only
    (el evento sin la condicion de iliquidez), volatilidad-only.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from r24_discovery_battery import freeze_direction_train, fwd, placebo, eval_frozen
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
MAJOR_SET = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
             "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT",
             "MATICUSDT", "BCHUSDT", "NEARUSDT", "ATOMUSDT", "UNIUSDT", "ETCUSDT",
             "APTUSDT", "FILUSDT"}
ILLIQ_PCTILE = 0.10   # decil mas bajo de volumen propio (causal)
EXTREME_LO, EXTREME_HI = 0.05, 0.95


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


def main():
    print("=== ROUND 27 — LIQUIDITY REGIME -> ALPHA ===\n")
    P, F = load_all()
    print(f"universo: {len(P)} simbolos")
    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")
    HZ = [("15m", 1), ("1h", HOR["1h"]), ("4h", HOR["4h"]), ("8h", HOR["4h"] * 2), ("24h", HOR["24h"])]

    # ---------------------------------------------------------------
    # cobertura de la feature de iliquidez
    # ---------------------------------------------------------------
    n_illiq_bars = 0; n_total_bars = 0
    for s, d in P.items():
        volp = F[s]["vol_pct"]
        ok = np.isfinite(volp)
        n_total_bars += ok.sum()
        n_illiq_bars += (ok & (volp <= ILLIQ_PCTILE)).sum()
    print(f"cobertura: {n_total_bars} barras validas de volp en {len(P)} simbolos; "
          f"{n_illiq_bars} ({n_illiq_bars/n_total_bars:.1%}) en estado iliquido (decil<=10%, esperado ~10%)\n")

    # =====================================================================
    print("#" * 70 + "\n PASO 3 — ESTADO SOLO (iliquido, sin evento) -> forward return\n" + "#" * 70)
    events_state = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        volp = F[s]["vol_pct"]; r1 = F[s]["r1"]
        illiq = np.isfinite(volp) & (volp <= ILLIQ_PCTILE)
        last = -999
        for i in np.where(illiq)[0]:
            if i < ROLL or i - last < 4 or i + 1 + HOR["24h"] >= n:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if (np.isfinite(r1[i]) and r1[i] > 0) else -1.0   # placeholder, direccion real se decide abajo
            events_state.append((s, i, dy, ev_sign))
    print(f"eventos 'estado iliquido' (sin evento de movimiento): {len(events_state)}")
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events_state, hb, seg)
        print(f"  [TRAIN] h={h_lbl}: cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
              f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
        eval_frozen(P, events_state, hb, mode, seg, f"ESTADO-solo h={h_lbl}")

    # =====================================================================
    print("\n" + "#" * 70 + "\n PASO 4/5 — ESTADO + EVENTO (iliquido + movimiento extremo) -> forward return\n" + "#" * 70)
    events_se = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        volp = f["vol_pct"]; r1p = f["ret1_pct"]; r1 = f["r1"]
        illiq = np.isfinite(volp) & (volp <= ILLIQ_PCTILE)
        extreme = np.isfinite(r1p) & ((r1p >= EXTREME_HI) | (r1p <= EXTREME_LO))
        mask = illiq & extreme
        last = -999
        for i in np.where(mask)[0]:
            if i < ROLL or i - last < 4 or i + 1 + HOR["24h"] >= n:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if r1[i] > 0 else -1.0
            events_se.append((s, i, dy, ev_sign))
    print(f"eventos 'iliquido + movimiento extremo': {len(events_se)}")
    chosen_modes = {}
    for h_lbl, hb in HZ:
        mode, Rc, Rr = freeze_direction_train(P, events_se, hb, seg)
        chosen_modes[h_lbl] = mode
        print(f"  [TRAIN] h={h_lbl}: cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
              f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
        eval_frozen(P, events_se, hb, mode, seg, f"ESTADO+EVENTO h={h_lbl}")

    # =====================================================================
    print("\n" + "#" * 70 + "\n CONTROL — MISMO EVENTO (movimiento extremo) SIN CONDICION DE ILIQUIDEZ (control volumen-only)\n" + "#" * 70)
    events_ctrl_vol = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
        volp = f["vol_pct"]; r1p = f["ret1_pct"]; r1 = f["r1"]
        extreme = np.isfinite(r1p) & ((r1p >= EXTREME_HI) | (r1p <= EXTREME_LO))
        not_illiq = np.isfinite(volp) & (volp > ILLIQ_PCTILE)
        mask = extreme & not_illiq
        last = -999
        for i in np.where(mask)[0]:
            if i < ROLL or i - last < 4 or i + 1 + HOR["24h"] >= n:
                continue
            last = i
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            ev_sign = 1.0 if r1[i] > 0 else -1.0
            events_ctrl_vol.append((s, i, dy, ev_sign))
    print(f"eventos control (movimiento extremo, SIN iliquidez): {len(events_ctrl_vol)}")
    for h_lbl, hb in (("4h", HOR["4h"]), ("24h", HOR["24h"])):
        mode = chosen_modes.get(h_lbl, "cont")
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd(P, s, i, hb, ev_sign if mode == "cont" else -ev_sign))
                     for (s, i, dy, ev_sign) in events_ctrl_vol if seg(dy) == sgv]
            pairs = [(s, r) for (s, r) in pairs if r is not None]
            if len(pairs) < 30:
                continue
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - COST) if R.get("mean_bp") is not None else None
            print(f"    CONTROL(sin iliquidez) h={h_lbl:>3s} [{mode}] {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp "
                  f"n={R.get('n')} ci_excl0={R.get('ci_excl_0')}")

    # =====================================================================
    print("\n" + "#" * 70 + "\n MODELO A vs B — HORA FIJA (22:00 UTC) vs ILIQUIDEZ CAUSAL, mismo evento base (movimiento extremo)\n" + "#" * 70)
    for label, filt in (("Modelo A: hora==22 UTC", lambda s, i: datetime.utcfromtimestamp(int(P[s]["t"][i]) / 1000).hour == 22),
                        ("Modelo B: iliquidez causal (decil<=10%)", lambda s, i: F[s]["vol_pct"][i] <= ILLIQ_PCTILE if np.isfinite(F[s]["vol_pct"][i]) else False)):
        evs = []
        for s, d in P.items():
            f = F[s]; c = d["c"]; t = d["t"]; n = len(c)
            r1p = f["ret1_pct"]; r1 = f["r1"]
            extreme = np.isfinite(r1p) & ((r1p >= EXTREME_HI) | (r1p <= EXTREME_LO))
            last = -999
            for i in np.where(extreme)[0]:
                if i < ROLL or i - last < 4 or i + 1 + HOR["24h"] >= n or not filt(s, i):
                    continue
                last = i
                dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                ev_sign = 1.0 if r1[i] > 0 else -1.0
                evs.append((s, i, dy, ev_sign))
        print(f"\n  -- {label} -- eventos: {len(evs)}")
        for h_lbl, hb in (("4h", HOR["4h"]), ("24h", HOR["24h"])):
            mode, Rc, Rr = freeze_direction_train(P, evs, hb, seg)
            print(f"    [TRAIN h={h_lbl}] cont={Rc.get('mean_bp')}bp(ci_excl0={Rc.get('ci_excl_0')})  "
                  f"rev={Rr.get('mean_bp')}bp(ci_excl0={Rr.get('ci_excl_0')})  -> elegido: {mode}")
            eval_frozen(P, evs, hb, mode, seg, f"    {label[:18]} h={h_lbl}")

    # =====================================================================
    print("\n" + "#" * 70 + "\n CONTROLES ADICIONALES sobre ESTADO+EVENTO (mejor horizonte visto arriba): BTC, majors, excluyendo hora 22\n" + "#" * 70)
    best_h_lbl, best_hb = "4h", HOR["4h"]
    mode_best = chosen_modes.get(best_h_lbl, "cont")
    for label, symfilt in (("BTC solo", lambda s: s == "BTCUSDT"),
                            ("Majors (20 grandes)", lambda s: s in MAJOR_SET),
                            ("Excluyendo hora 22 UTC", None)):
        evs = []
        for (s, i, dy, ev_sign) in events_se:
            if label == "Excluyendo hora 22 UTC":
                if datetime.utcfromtimestamp(int(P[s]["t"][i]) / 1000).hour == 22:
                    continue
            elif not symfilt(s):
                continue
            evs.append((s, i, dy, ev_sign))
        if len(evs) < 40:
            print(f"  {label}: eventos insuficientes ({len(evs)})")
            continue
        for sgv in ("train", "val", "oos"):
            pairs = [(s, fwd(P, s, i, best_hb, ev_sign if mode_best == "cont" else -ev_sign)) for (s, i, dy, ev_sign) in evs if seg(dy) == sgv]
            pairs = [(s, r) for (s, r) in pairs if r is not None]
            if len(pairs) < 30:
                continue
            R = agg_pairs(pairs)
            net = (R["mean_bp"] - COST) if R.get("mean_bp") is not None else None
            print(f"    {label:24s} {sgv:5s}: gross={R.get('mean_bp')}bp net={net}bp n={R.get('n')} ci_excl0={R.get('ci_excl_0')}")

    print("\nfin R27 discovery -- ver informe para sim economica si corresponde")


if __name__ == "__main__":
    main()
