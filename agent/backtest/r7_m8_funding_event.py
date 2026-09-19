"""
ROUND 7 — EXPERIMENTO 3 — M8: FUNDING COMO EVENTO DISCRETO (crowd unwind).

funding_rate NO como filtro continuo (eso fue H10/H16 y falló) sino como
EVENTO en el reloj del exchange (settlement 00/08/16 UTC, y 4h para algunos
perps). Dos sub-hipótesis:

  M8a — EXTREMO: en el settlement, |funding| en su decil extremo significa que
        un lado paga MUY caro por mantener la posición -> ese lado está crowdeado
        y es frágil. Predicción: en las 8-24 h siguientes el precio se mueve
        CONTRA el lado que paga (funding muy positivo = longs pagan = crowd long
        -> fwd DOWN ; funding muy negativo = shorts pagan = crowd short -> fwd UP
        = squeeze).

  M8b — FLIP DE SIGNO: el funding de un símbolo cruza de + a - (o - a +) entre
        dos settlements consecutivos = cambio de régimen de posicionamiento.
        Predicción (momentum de posicionamiento): tras un flip a NEGATIVO (los
        shorts empiezan a dominar / pagar), fwd DOWN 8-24 h ; simétrico.

DATOS: klines.db funding_rates (media ~22 d/símbolo, 498 símbolos) ⋈ klines_clean
15m de binance_vision para el retorno forward. Overlap temporal: el histórico
limpio de funding arranca ~2026-07-11, klines_clean termina 2026-08-17 -> ~37 d
de solape. MUESTRA CORTA -> cualquier resultado es como máximo PARK/UNKNOWN
(no alcanza para afirmar estabilidad temporal); un flat sí puede cerrar FAILED.

ENTRADA: open del primer bar de 15m >= funding_time + 5min (settlement ya
conocido). Horizontes 8/16/24 h. Dirección evaluada = a favor de la hipótesis.
CONTROLES: placebo (mismo símbolo, ventana +48 h); matched (settlements con
funding en su rango central |z|<=0.5) para M8a.
"""
import os, sqlite3, json, numpy as np
from datetime import datetime, timezone
from r7_common import agg_pairs, zscore_causal

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
KL = os.path.join(HERE, "..", "data", "klines.db")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
BAR = 15 * 60 * 1000
H_HOURS = [8, 16, 24]
PLACEBO_MS = 48 * 3600 * 1000
COST_RT_BP = 16.0
EXTREME_Q = 0.90       # |funding| por encima de su p90 causal (mín 12 pts previos)


def main():
    fk = sqlite3.connect(f"file:{KL}?mode=ro", uri=True)
    frows = fk.execute(
        "SELECT symbol,funding_time,funding_rate FROM funding_rates "
        "WHERE funding_time>1700000000000 AND funding_rate IS NOT NULL ORDER BY symbol,funding_time").fetchall()
    fk.close()
    bysym = {}
    for s, t, r in frows:
        bysym.setdefault(s, []).append((int(t), float(r)))

    bv = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)

    def klines(sym, t0, t1):
        r = bv.execute("SELECT open_time,open,close FROM klines_clean WHERE symbol=? AND interval='15m' "
                       "AND open_time BETWEEN ? AND ? ORDER BY open_time", (sym, int(t0), int(t1))).fetchall()
        return np.array(r, float) if r else None

    B = {k: {h: [] for h in H_HOURS} for k in
         ("a_real", "a_plac", "a_match", "b_real", "b_plac")}
    n_a = n_b = 0
    syms_with_kl = 0
    for sym, seq in bysym.items():
        if len(seq) < 15:
            continue
        seq.sort()
        ts = np.array([x[0] for x in seq]); fr = np.array([x[1] for x in seq])
        # ¿hay klines para este símbolo?
        span = klines(sym, ts[0], ts[-1] + 3 * 86400000)
        if span is None or len(span) < 200:
            continue
        syms_with_kl += 1
        kt = span[:, 0].astype(np.int64); ko = span[:, 1]

        def fwd(entry_t, hours):
            j = np.searchsorted(kt, entry_t)
            if j >= len(kt):
                return None
            k2 = np.searchsorted(kt, kt[j] + hours * 3600 * 1000)
            if k2 >= len(kt):
                return None
            return np.log(ko[k2] / ko[j])

        # causal p90 de |funding|
        af = np.abs(fr)
        for i in range(12, len(seq)):
            past = af[:i]
            thr = np.quantile(past, EXTREME_Q)
            cen = np.quantile(past, 0.5)
            settle_t = ts[i]
            entry_t = settle_t + 5 * 60 * 1000
            # M8a extremo
            if af[i] >= thr and af[i] > 0:
                sgn = -np.sign(fr[i])   # funding + (longs pagan) -> apostamos DOWN -> sgn=-1
                n_a += 1
                for h in H_HOURS:
                    v = fwd(entry_t, h)
                    if v is not None:
                        B["a_real"][h].append((sym, sgn * v))
                    vp = fwd(entry_t + PLACEBO_MS, h)
                    if vp is not None:
                        B["a_plac"][h].append((sym, sgn * vp))
            # matched (rango central)
            elif af[i] <= cen:
                sgn = -np.sign(fr[i]) if fr[i] != 0 else 1.0
                for h in H_HOURS:
                    v = fwd(entry_t, h)
                    if v is not None:
                        B["a_match"][h].append((sym, sgn * v))
            # M8b flip de signo
            if i >= 1 and np.sign(fr[i]) != 0 and np.sign(fr[i - 1]) != 0 and np.sign(fr[i]) != np.sign(fr[i - 1]):
                sgn = np.sign(fr[i])   # flip a negativo -> shorts dominan -> fwd DOWN -> sgn=-1
                n_b += 1
                for h in H_HOURS:
                    v = fwd(entry_t, h)
                    if v is not None:
                        B["b_real"][h].append((sym, sgn * v))
                    vp = fwd(entry_t + PLACEBO_MS, h)
                    if vp is not None:
                        B["b_plac"][h].append((sym, sgn * vp))
    bv.close()

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "symbols_with_klines": syms_with_kl, "n_extreme_events": n_a, "n_flip_events": n_b,
           "params": dict(H_HOURS=H_HOURS, EXTREME_Q=EXTREME_Q, COST_RT_BP=COST_RT_BP,
                          note="funding history ~22d median/symbol; overlap w/ klines ~37d -> data-limited"),
           "M8a_extreme": {}, "M8b_flip": {}}
    print(f"símbolos con klines={syms_with_kl} · extreme events={n_a} · flip events={n_b}")

    print("\n=== M8a  FUNDING EXTREMO -> contra el lado que paga ===")
    for h in H_HOURS:
        R = agg_pairs(B["a_real"][h]); P = agg_pairs(B["a_plac"][h]); M = agg_pairs(B["a_match"][h])
        after = round(R["mean_bp"] - np.sign(R["mean_bp"]) * COST_RT_BP, 2) if "mean_bp" in R else None
        out["M8a_extreme"][h] = {"real": R, "placebo": P, "matched": M, "after_cost_bp": after}
        print(f"  h={h:>2}h real={R.get('mean_bp')} bp CI{R.get('ci_bp')} excl0={R.get('ci_excl_0')} "
              f"halves=({R.get('half1_bp')},{R.get('half2_bp')}) symPos={R.get('frac_sym_pos')} n={R.get('n')}  "
              f"placebo={P.get('mean_bp')} matched={M.get('mean_bp')} after_cost={after}")

    print("\n=== M8b  FLIP DE SIGNO -> momentum de posicionamiento ===")
    for h in H_HOURS:
        R = agg_pairs(B["b_real"][h]); P = agg_pairs(B["b_plac"][h])
        after = round(R["mean_bp"] - np.sign(R["mean_bp"]) * COST_RT_BP, 2) if "mean_bp" in R else None
        out["M8b_flip"][h] = {"real": R, "placebo": P, "after_cost_bp": after}
        print(f"  h={h:>2}h real={R.get('mean_bp')} bp CI{R.get('ci_bp')} excl0={R.get('ci_excl_0')} "
              f"halves=({R.get('half1_bp')},{R.get('half2_bp')}) symPos={R.get('frac_sym_pos')} n={R.get('n')}  "
              f"placebo={P.get('mean_bp')} after_cost={after}")

    path = os.path.join(ROOT, "scratch_r7_m8_funding_event.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(f"\nguardado {path}")


if __name__ == "__main__":
    main()
