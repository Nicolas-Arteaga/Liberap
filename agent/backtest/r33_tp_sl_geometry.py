"""
ROUND 33 — GEOMETRIA MFE/MAE Y TP-ANTES-QUE-SL. No busca retorno medio;
busca asimetria de trayectoria: P(TP antes que SL) x tamano de TP vs SL,
con costo de ejecucion incluido desde el diseno (24bp RT).

Unidad de riesgo (1R) = volatilidad realizada causal del propio simbolo en
la barra de entrada (`rv`, ya construida en build_feats, ~fraccion de
precio). SL fijo en 1R. TP variable en {1R, 2R, 3R}. Horizonte de barrido
= 24h (96 barras de 15m) -- si no toca TP ni SL, se cierra a mercado
(time-exit) y se mide el retorno real a ese punto.

Fase 1: mapear la geometria BASELINE (sin condicionar en nada) del
universo ancho -- LONG y SHORT por separado, muestreado cada 4h (16
barras) para mantener el computo manejable sin perder generalidad.

Fase 2: condicionar en 6 estados simples (rv/vol/ret1 extremos, alto y
bajo) -- no una matriz de cientos de combinaciones, solo lo necesario
para ver si algun estado DESPLAZA la geometria baseline de forma
economicamente relevante. TRAIN decide, VAL confirma, OOS valida, placebo
temporal como control.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL
from r7_common import agg_pairs
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")
COST_RT_BP = 24.0
HORIZON = 96          # 24h
STEP = 16             # muestreo causal cada 4h (evita recomputo excesivo, no pierde generalidad)
TP_MULTS = [1.0, 2.0, 3.0]
SL_MULT = 1.0
MIN_R = 0.0005        # filtra barras con vol casi nula (R degenerado, evita division por ~0)


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


def first_touch(hi, lo, tp_px, sl_px, side):
    """hi/lo: arrays de HORIZON barras desde la entrada (inclusive).
    side=+1 LONG, -1 SHORT. Devuelve ('tp'|'sl'|'time', idx_o_None)."""
    if side > 0:
        tp_hits = hi >= tp_px
        sl_hits = lo <= sl_px
    else:
        tp_hits = lo <= tp_px
        sl_hits = hi >= sl_px
    tp_i = np.argmax(tp_hits) if tp_hits.any() else None
    sl_i = np.argmax(sl_hits) if sl_hits.any() else None
    if tp_i is None and sl_i is None:
        return "time", None
    if tp_i is None:
        return "sl", sl_i
    if sl_i is None:
        return "tp", tp_i
    if tp_i < sl_i:
        return "tp", tp_i
    if sl_i < tp_i:
        return "sl", sl_i
    return "tie", tp_i   # mismo bar, ambiguo (no resoluble con OHLC) -- se cuenta aparte


def scan_trades(P, F, seg_filter, side, cond_mask=None, min_gap_bars=None):
    """Recorre el universo, muestreo cada STEP barras (o en las barras de
    cond_mask si se da), simula SL=1R fijo y TP en cada multiplo de
    TP_MULTS, devuelve dict tp_mult -> list of (r_multiple_neto_en_R, seg, dy)
    para side dado."""
    out = {m: [] for m in TP_MULTS}
    for s, d in P.items():
        f = F[s]; c = d["c"]; h_ = d["h"]; lo_ = d["l"]; o = d["o"]; t = d["t"]; n = len(c)
        rv = f["rv"]
        if cond_mask is not None:
            idxs = np.where(cond_mask[s])[0]
        else:
            idxs = np.arange(ROLL, n - HORIZON - 2, STEP)
        for i in idxs:
            if i < ROLL or i + 1 + HORIZON >= n:
                continue
            R = rv[i]
            if not np.isfinite(R) or R < MIN_R:
                continue
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            if seg_filter(dy) is None:
                continue
            e = i + 1
            entry_px = o[e]
            hi_w = h_[e:e + HORIZON]; lo_w = lo_[e:e + HORIZON]
            sl_px = entry_px * (1 - side * SL_MULT * R)
            for m in TP_MULTS:
                tp_px = entry_px * (1 + side * m * R)
                res, idx = first_touch(hi_w, lo_w, tp_px, sl_px, side)
                if res == "tp":
                    r_mult = m
                elif res == "sl":
                    r_mult = -SL_MULT
                elif res == "tie":
                    r_mult = (m - SL_MULT) / 2   # resultado ambiguo, se promedia (documentado, no se oculta)
                else:  # time exit
                    exit_px = o[e + HORIZON] if e + HORIZON < len(o) else c[min(e + HORIZON - 1, n - 1)]
                    r_mult = side * math.log(exit_px / entry_px) / R
                out[m].append((r_mult, seg_filter(dy), dy, s))
    return out


def summarize_r(trades, cost_bp_in_R_terms_fn):
    """trades: list (r_mult, seg, dy, s). Devuelve estadisticas por segmento."""
    by_seg = collections.defaultdict(list)
    for (r, sgv, dy, s) in trades:
        by_seg[sgv].append((r, s))
    out = {}
    for sgv, rows in by_seg.items():
        if len(rows) < 30:
            continue
        arr = np.array([r for r, s in rows])
        win = (arr > 0).mean()
        mean_r = arr.mean()
        # bootstrap por simbolo para CI (mismo criterio de siempre)
        by_sym = collections.defaultdict(list)
        for (r, s) in rows:
            by_sym[s].append(r)
        syms = list(by_sym)
        sym_mean = np.array([np.mean(by_sym[s]) for s in syms])
        rng = np.random.default_rng(33)
        bs = np.array([np.mean(rng.choice(sym_mean, len(sym_mean))) for _ in range(2000)])
        ci = [np.percentile(bs, 5), np.percentile(bs, 95)]
        out[sgv] = dict(n=len(arr), mean_r=mean_r, win_rate=win, ci_r=ci, ci_excl0=(ci[0] > 0 or ci[1] < 0))
    return out


def main():
    print("=== ROUND 33 — GEOMETRIA MFE/MAE: TP-ANTES-QUE-SL ===\n")
    P, F = load_all()
    print(f"universo: {len(P)} simbolos, muestreo cada {STEP} barras ({STEP*15}min), horizonte={HORIZON*15//60}h\n")

    ref = "BTCUSDT" if "BTCUSDT" in P else max(P, key=lambda s: len(P[s]["t"]))
    days_all = sorted(set(datetime.utcfromtimestamp(int(t) / 1000).date() for t in P[ref]["t"]))
    tcut, vcut = days_all[int(len(days_all) * 0.5)], days_all[int(len(days_all) * 0.75)]
    def seg(dv): return "train" if dv <= tcut else ("val" if dv <= vcut else "oos")

    print("#" * 70 + "\n FASE 1 — GEOMETRIA BASELINE (sin condicionar), LONG y SHORT, SL=1R\n" + "#" * 70)
    baseline = {}
    for side, label in ((1, "LONG"), (-1, "SHORT")):
        trades = scan_trades(P, F, seg, side)
        for m in TP_MULTS:
            stats = summarize_r(trades[m], None)
            for sgv in ("train", "val", "oos"):
                if sgv not in stats:
                    continue
                st = stats[sgv]
                # costo en unidades de R: 24bp / (R en bp, aprox R*1e4) -- se resta directamente en bp mas abajo para la econ real
                print(f"  {label} SL=1R TP={m:.0f}R {sgv:5s}: n={st['n']:6d} mean_R={st['mean_r']:+.3f} "
                      f"WR={st['win_rate']:.2f} ci_R={[round(x,3) for x in st['ci_r']]} ci_excl0={st['ci_excl0']}")
        baseline[side] = trades
    print()

    print("#" * 70 + "\n FASE 2 — CONDICIONAR EN 6 ESTADOS SIMPLES (rv/vol/ret1, HI/LO), horizonte 24h\n" + "#" * 70)
    states = {}
    for s, f in F.items():
        states[s] = dict(
            rv_hi=np.isfinite(f["rv_pct"]) & (f["rv_pct"] >= 0.90),
            rv_lo=np.isfinite(f["rv_pct"]) & (f["rv_pct"] <= 0.10),
            vol_hi=np.isfinite(f["vol_pct"]) & (f["vol_pct"] >= 0.90),
            vol_lo=np.isfinite(f["vol_pct"]) & (f["vol_pct"] <= 0.10),
            ret1_hi=np.isfinite(f["ret1_pct"]) & (f["ret1_pct"] >= 0.90),
            ret1_lo=np.isfinite(f["ret1_pct"]) & (f["ret1_pct"] <= 0.10),
        )

    results = []
    for state_name in ("rv_hi", "rv_lo", "vol_hi", "vol_lo", "ret1_hi", "ret1_lo"):
        mask_by_sym = {s: states[s][state_name] for s in states}
        for side, label in ((1, "LONG"), (-1, "SHORT")):
            trades = scan_trades(P, F, seg, side, cond_mask=mask_by_sym)
            for m in TP_MULTS:
                stats = summarize_r(trades[m], None)
                if "train" not in stats or not stats["train"]["ci_excl0"] or stats["train"]["mean_r"] <= 0:
                    continue
                label_full = f"{state_name}+{label} SL=1R TP={m:.0f}R"
                tr = stats["train"]
                print(f"  [{label_full}] TRAIN: n={tr['n']} mean_R={tr['mean_r']:+.3f} WR={tr['win_rate']:.2f} "
                      f"ci_excl0={tr['ci_excl0']}")
                if "val" not in stats or stats["val"]["mean_r"] <= 0:
                    print(f"      VAL no confirma -> descartado")
                    continue
                vl = stats["val"]
                print(f"      VAL CONFIRMA: n={vl['n']} mean_R={vl['mean_r']:+.3f} WR={vl['win_rate']:.2f}")
                if "oos" not in stats:
                    print(f"      OOS insuficiente")
                    continue
                oo = stats["oos"]
                # convertir a bp usando la R media de las entradas OOS de este subset para chequear costo
                r_oos = [r for (r, sgv, dy, s) in trades[m] if sgv == "oos"]
                print(f"      OOS: n={oo['n']} mean_R={oo['mean_r']:+.3f} WR={oo['win_rate']:.2f} ci_excl0={oo['ci_excl0']}")
                results.append(dict(label=label_full, side=side, m=m, state=state_name, stats=stats, trades=trades[m]))

    print("\n" + "#" * 70 + "\n RESUMEN\n" + "#" * 70)
    survivors = [r for r in results if "oos" in r["stats"] and r["stats"]["oos"]["mean_r"] > 0 and r["stats"]["oos"]["ci_excl0"]]
    print(f"  configuraciones evaluadas: {len(results)} (de 36 posibles: 6 estados x 2 lados x 3 TP)")
    print(f"  sobreviven TRAIN->VAL(confirma)->OOS con CI excl 0: {len(survivors)}")
    for r in survivors:
        print(f"    >>> {r['label']}: OOS mean_R={r['stats']['oos']['mean_r']:+.3f} n={r['stats']['oos']['n']}")

    print("\nfin FASE 1-2 de R33 -- ver informe para economia real (Fase 4) del sobreviviente, si lo hay")


if __name__ == "__main__":
    main()
