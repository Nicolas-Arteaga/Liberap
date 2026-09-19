"""
ROUND 25, FASE A — reproducir el fenomeno de forma simple y transparente.

Pregunta central: ¿el "sesgo bajista" de R12/R13/R15/R18/R24 es un edge
ESPECIFICO del lado SHORT, o es simplemente que el universo entero (long Y
short) tiene un drift direccional -- en cuyo caso "shortear" no es una
estrategia, es apostar a la direccion del mercado, que es otra cosa?

Medicion sin condicionar en ningun evento: retorno forward NO ponderado
(LONG=+1, SHORT=-1) promediado cross-sectionalmente sobre TODO el universo,
en cada horizonte, TRAIN/VAL/OOS, comparado contra:
  - BTC/ETH (referencia de mercado)
  - "majors" (proxy de liquidez/antiguedad: simbolos con historia completa
    desde el inicio de TRAIN, ~duracion 14.5 meses)
  - el resto del universo (altcoins chicas/nuevas)
"""
import os, sys, math, numpy as np, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST = 24.0
MAJOR_SET = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
             "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT",
             "MATICUSDT", "BCHUSDT", "NEARUSDT", "ATOMUSDT", "UNIUSDT", "ETCUSDT",
             "APTUSDT", "FILUSDT"}


def main():
    print("=== ROUND 25 — FASE A: REPRODUCIR EL FENOMENO (LONG vs SHORT vs BTC/ETH vs MAJORS) ===\n")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d
    con.close()
    print(f"universo: {len(P)} simbolos")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")
    print(f"corte: TRAIN<={tcut}  VAL<={vcut}  OOS>{vcut}\n")

    # antiguedad: longitud de historia (proxy de liquidez/madurez del listing)
    lens = {s: len(P[s]["t"]) for s in P}
    max_len = max(lens.values())
    old_syms = {s for s, l in lens.items() if l >= 0.95 * max_len}   # cotizan desde (casi) el inicio del dataset
    new_syms = {s for s, l in lens.items() if l < 0.30 * max_len}    # listados bien avanzado el dataset
    print(f"'antiguos' (>=95% de la historia maxima): {len(old_syms)} simbolos")
    print(f"'nuevos' (<30% de la historia maxima, listados tarde): {len(new_syms)} simbolos")
    majors_present = MAJOR_SET & set(P.keys())
    print(f"majors presentes en el dataset: {len(majors_present)}/{len(MAJOR_SET)}\n")

    def fwd_all(symset, hbars, sgv, sample_step=4):
        """retorno forward (LONG) muestreado cada `sample_step` barras (para
        no reusar la misma ventana traslapada miles de veces) por simbolo,
        cross-sectional, para el segmento de fecha dado."""
        pairs = []
        for s in symset:
            if s not in P:
                continue
            d = P[s]; o = d["o"]; t = d["t"]; n = len(o)
            for i in range(ROLL, n - hbars - 1, sample_step):
                dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
                if seg(dy) != sgv:
                    continue
                r = math.log(o[i + 1 + hbars] / o[i + 1])
                pairs.append((s, r))
        return pairs

    universe_syms = set(P.keys())
    minor_syms = universe_syms - old_syms

    print("#" * 70)
    print(" RETORNO FORWARD LONG (no condicionado, muestreado c/4 barras=1h) POR GRUPO Y HORIZONTE")
    print("#" * 70)
    for h_lbl, hb in HOR.items():
        print(f"\n  -- horizonte {h_lbl} --")
        for label, symset in (("UNIVERSO COMPLETO", universe_syms), ("MAJORS (top-20 cap)", majors_present),
                               ("ANTIGUOS (95%+ historia)", old_syms), ("NUEVOS (<30% historia)", new_syms),
                               ("BTC solo", {"BTCUSDT"} & universe_syms), ("ETH solo", {"ETHUSDT"} & universe_syms)):
            for sgv in ("train", "val", "oos"):
                pairs = fwd_all(symset, hb, sgv)
                if len(pairs) < 40:
                    continue
                R = agg_pairs(pairs)
                print(f"    {label:26s} {sgv:5s}: LONG_gross={R.get('mean_bp'):+8.2f}bp  n={R.get('n'):>7d}  "
                      f"ci={R.get('ci_bp')}  ci_excl0={R.get('ci_excl_0')}")

    print("\nfin FASE A")


if __name__ == "__main__":
    main()
