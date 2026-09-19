"""
ROUND 7 — EXPERIMENTO 1 — M10: TAKER ABSORPTION (evento de una sola barra).

MECANISMO: en una barra 15m entra agresion taker MASIVA y unilateral, pero el
precio realizado de esa barra es ~CERO. Alguien pasivo (iceberg / vendedor
grande institucional / MM con inventario) ABSORBIO todo el flujo agresivo sin
mover el precio. Ese participante pasivo es un actor con informacion o con
obligacion de ejecutar tamano. Cuando termina de absorber, el precio se libera.

Dos hipotesis RIVALES (se testean las dos, no se asume cual):
  H-informed : el absorbedor esta informado -> el precio CONTINUA en su
               direccion (absorb-up = absorbedor VENDE -> fwd DOWN).
  H-release  : agotado el absorbedor, la presion reprimida gana ->
               (absorb-up -> fwd UP).

EVENTO:
  tbr[t]   = taker_buy_quote / quote_volume            (fraccion de compra agresiva)
  z_tbr[t] = zscore_causal(tbr, ROLL)                  (30 d)
  barret[t]= log(close[t]/open[t])
  absret   = |barret| normalizado por su media rolling causal (30 d)
  absorb_up = z_tbr >= +ZK  AND absret <= QUIET       (compradores absorbidos por un vendedor)
  absorb_dn = z_tbr <= -ZK  AND absret <= QUIET       (vendedores absorbidos por un comprador)

ENTRADA: open[t+1]. Horizontes 1/2/4/8 barras (15/30/60/120 min), open->open.
Direccion evaluada = signo del retorno *a favor de H-release* (absorb_up -> long).
Se reporta tal cual; el signo dice cual hipotesis (si alguna) es cierta.

CONTROLES ADVERSARIALES:
  placebo   : mismo evento, indices +PLACEBO barras.
  quiet_only: barras con absret <= QUIET pero z_tbr NEUTRO (|z|<=0.5) ->
              aisla "reversion de barra tranquila" pura (sin flujo). Si quiet_only
              ya explica el efecto -> NO es absorcion, es low-vol mean-reversion.
  matched   : mismo |z_tbr|>=ZK pero absret >= 1.0 (flujo unilateral que SI movio
              el precio) -> si este control tiene el mismo signo, el driver es el
              flujo, no la absorcion.

VEREDICTO PROMISING (todo debe cumplirse en algun horizonte):
  |after_cost_bp| >= 4  ; CI excl 0 ; halves_same_sign ;
  frac_sym_pos >= 0.55 ; top5_conc <= 0.60 ;
  |placebo| < 0.4*|efecto| ; |quiet_only| < 0.5*|efecto| ;
  el signo NO coincide con 'matched' (o lo supera claramente en magnitud).
Si supera costo en algun horizonte con CI excl 0 pero falla otro criterio -> PARK.
Si nada supera costo -> FAILED.
"""
import os, sqlite3, json, numpy as np
from datetime import datetime, timezone
from r7_common import zscore_causal, roll_mean_causal, agg_pairs

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
TOP_N = 150
ROLL = 2880
ZK = 2.0
QUIET = 0.35
PLACEBO = 96
HORIZONS = [1, 2, 4, 8]
COST_RT_BP = 16.0


def liquid_symbols(con):
    rows = con.execute(
        "SELECT symbol, COUNT(*) n, AVG(quote_volume) av FROM taker_flow "
        "WHERE interval='15m' GROUP BY symbol HAVING n > ? ORDER BY av DESC LIMIT ?",
        (ROLL + 400, TOP_N)).fetchall()
    return [r[0] for r in rows]


def load(con, sym):
    r = con.execute(
        "SELECT k.open_time,k.open,k.close,t.quote_volume,t.taker_buy_quote "
        "FROM klines_clean k JOIN taker_flow t "
        "ON k.symbol=t.symbol AND k.interval=t.interval AND k.open_time=t.open_time "
        "WHERE k.symbol=? AND k.interval='15m' ORDER BY k.open_time", (sym,)).fetchall()
    if len(r) < ROLL + 400:
        return None
    a = np.array(r, float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]  # t, o, c, qv, tbq


def main():
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    syms = liquid_symbols(con)
    buckets = {k: {h: [] for h in HORIZONS} for k in
               ("up_real", "up_plac", "up_quiet", "up_match",
                "dn_real", "dn_plac", "dn_quiet", "dn_match")}
    n_ev = {"up": 0, "dn": 0}
    tmin = tmax = None
    used = 0
    for sym in syms:
        d = load(con, sym)
        if d is None:
            continue
        t, o, c, qv, tbq = d
        n = len(c)
        if tmin is None:
            tmin, tmax = t[0], t[-1]
        else:
            tmin, tmax = min(tmin, t[0]), max(tmax, t[-1])
        used += 1
        tbr = np.divide(tbq, qv, out=np.full(n, np.nan), where=qv > 0)
        z_tbr = zscore_causal(tbr, ROLL)
        barret = np.log(c / o)
        absb = np.abs(barret)
        absnorm = absb / np.where(roll_mean_causal(absb, ROLL) > 0, roll_mean_causal(absb, ROLL), np.nan)

        base_up = (z_tbr >= ZK) & (absnorm <= QUIET)
        base_dn = (z_tbr <= -ZK) & (absnorm <= QUIET)
        quiet_up = (np.abs(z_tbr) <= 0.5) & (absnorm <= QUIET) & (barret <= 0)   # "quiet" split por signo de barret
        quiet_dn = (np.abs(z_tbr) <= 0.5) & (absnorm <= QUIET) & (barret > 0)
        match_up = (z_tbr >= ZK) & (absnorm >= 1.0)
        match_dn = (z_tbr <= -ZK) & (absnorm >= 1.0)

        maxh = max(HORIZONS)
        for tag, mask, sgn in (("up", base_up, +1), ("dn", base_dn, -1)):
            idx = np.where(mask)[0]
            idx = idx[(idx >= ROLL) & (idx + 1 + maxh + PLACEBO < n)]
            # de-solapar: >=1 barra entre eventos del mismo símbolo/lado
            keep = []
            last = -999
            for i in idx:
                if i - last >= 1:
                    keep.append(i); last = i
            idx = np.array(keep, int)
            n_ev[tag] += len(idx)
            e = idx + 1
            for h in HORIZONS:
                rr = sgn * np.log(o[e + h] / o[e])          # a favor de H-release
                for s_, v_ in zip([sym] * len(rr), rr):
                    buckets[f"{tag}_real"][h].append((s_, v_))
                rp = sgn * np.log(o[e + PLACEBO + h] / o[e + PLACEBO])
                for v_ in rp:
                    buckets[f"{tag}_plac"][h].append((sym, v_))
        for tag, mask, sgn in (("up", quiet_up, +1), ("dn", quiet_dn, -1)):
            idx = np.where(mask)[0]
            idx = idx[(idx >= ROLL) & (idx + 1 + maxh < n)]
            idx = idx[::3]                                   # submuestreo, hay muchísimas
            e = idx + 1
            for h in HORIZONS:
                rr = sgn * np.log(o[e + h] / o[e])
                for v_ in rr:
                    buckets[f"{tag}_quiet"][h].append((sym, v_))
        for tag, mask, sgn in (("up", match_up, +1), ("dn", match_dn, -1)):
            idx = np.where(mask)[0]
            idx = idx[(idx >= ROLL) & (idx + 1 + maxh < n)]
            e = idx + 1
            for h in HORIZONS:
                rr = sgn * np.log(o[e + h] / o[e])
                for v_ in rr:
                    buckets[f"{tag}_match"][h].append((sym, v_))
    con.close()

    months = (tmax - tmin) / (30 * 86400000)
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "symbols_used": used, "span_months": round(months, 1),
           "params": dict(TOP_N=TOP_N, ROLL=ROLL, ZK=ZK, QUIET=QUIET, PLACEBO=PLACEBO,
                          HORIZONS=HORIZONS, COST_RT_BP=COST_RT_BP),
           "n_events": n_ev, "sides": {}}
    print(f"universo {used} sym · ~{months:.1f} meses · eventos: up={n_ev['up']} dn={n_ev['dn']}")

    for side in ("up", "dn"):
        lbl = "absorb_up (compradores absorbidos)" if side == "up" else "absorb_dn (vendedores absorbidos)"
        print(f"\n===== {lbl} =====  (signo + = a favor de H-release)")
        blk = {}
        for h in HORIZONS:
            R = agg_pairs(buckets[f"{side}_real"][h])
            P = agg_pairs(buckets[f"{side}_plac"][h])
            Q = agg_pairs(buckets[f"{side}_quiet"][h])
            M = agg_pairs(buckets[f"{side}_match"][h])
            after = round(R.get("mean_bp", 0.0) - np.sign(R.get("mean_bp", 0.0)) * COST_RT_BP, 2) if "mean_bp" in R else None
            blk[h] = {"real": R, "placebo": P, "quiet_only": Q, "matched_flow_moved": M,
                      "after_cost_bp": after}
            rm = R.get("mean_bp"); ci = R.get("ci_bp")
            print(f"  h={h*15:>3}m  real={rm} bp  CI{ci} excl0={R.get('ci_excl_0')}  "
                  f"halves=({R.get('half1_bp')},{R.get('half2_bp')})  symPos={R.get('frac_sym_pos')}  "
                  f"conc={R.get('top5_conc')}  n={R.get('n')}")
            print(f"          placebo={P.get('mean_bp')}  quiet_only={Q.get('mean_bp')}  matched(movió)={M.get('mean_bp')}  after_cost={after}")
        out["sides"][side] = blk

    path = os.path.join(ROOT, "scratch_r7_m10_absorption.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()
