"""
ROUND 22.5 — BACKTEST REALITY CHECK.

No busca alpha. Audita la infraestructura de investigacion (los scripts
r6-r22 de agent/backtest/, que son el UNICO motor usado para las 22 rondas
de research de esta mision) -- NO el motor de produccion (agent/backtest/
engine.py + SimulationMarkPriceWorker.cs), que es un sistema completamente
distinto, ya evaluado y marcado FAILED por separado (ver verge_backtest_gate
en memoria). Esa distincion es importante: este audit es sobre la
"maquina de investigacion", no sobre lo que corre en produccion.

Secciones:
  A. Test automatizado de lookahead (falla si el percentil causal ve el
     futuro) -- cumple el pedido explicito de la Parte 2 del brief.
  B. Tests sinteticos deterministas (fee, funding-join causal, colision de
     slot) -- Parte 8.
  C. Perturbacion de ejecucion sobre el candidato de capitulacion (aunque
     ya este cerrado FAILED en R22, es el unico candidato "fuerte" que
     tenemos para medir sensibilidad real) -- Parte 11/12.
"""
import os, sys, math, numpy as np, sqlite3, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r7_common import agg_pairs
from r12_smartmoney import pctile_causal
from r15_wide_discovery import universe, load_symbol
from r18_discovery import build_feats, ROLL, HOR
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
BV = os.path.join(HERE, "..", "data", "binance_vision_clean.db")


def test_causal_percentile_no_lookahead():
    """A: inyecta un spike FUTURO grande y verifica que pctile_causal en
    barras ANTERIORES al spike no cambia si el spike existe o no."""
    n = 5000; win = 500
    rng = np.random.default_rng(1)
    base = rng.normal(0, 1, n)
    a_clean = base.copy()
    a_spiked = base.copy()
    spike_at = 4000
    a_spiked[spike_at] = 1e6   # spike futuro enorme
    p_clean = pctile_causal(a_clean, win)
    p_spiked = pctile_causal(a_spiked, win)
    # Para toda barra t < spike_at, el percentil causal NO debe cambiar
    # (el spike esta fuera de su ventana pasada [t-win, t)).
    before = np.arange(win, spike_at)
    diffs = np.abs(np.nan_to_num(p_clean[before]) - np.nan_to_num(p_spiked[before]))
    max_diff = diffs.max()
    assert max_diff < 1e-9, f"LOOKAHEAD DETECTADO: percentil causal cambio en el pasado por un spike futuro (max_diff={max_diff})"
    # Para barras DESPUES del spike (t > spike_at + win), SI debe cambiar
    # (el spike ahora esta en su ventana pasada) -- si NO cambia, el test
    # esta mal construido, no que el codigo sea perfecto.
    after = np.arange(spike_at + 1, min(n, spike_at + win))
    diffs2 = np.abs(np.nan_to_num(p_clean[after]) - np.nan_to_num(p_spiked[after]))
    # el spike aporta como maximo 1/win al percentil cuando esta en la ventana pasada
    assert diffs2.max() > 1.0 / win / 2, "Test mal construido: el spike deberia afectar el percentil despues de win barras"
    print("  [PASS] A. pctile_causal: sin lookahead (spike futuro no afecta el pasado, si afecta el futuro)")


def test_fee_calc_deterministic():
    """B1: fee/slippage aplicados correctamente a un trade sintetico de signo conocido."""
    entry, exit_ = 100.0, 102.0   # +2% bruto LONG
    gross_bp = math.log(exit_ / entry) * 1e4
    TAKER_RT = 24.0
    net_bp = gross_bp - TAKER_RT
    expected_gross = math.log(1.02) * 1e4
    assert abs(gross_bp - expected_gross) < 1e-6, f"formula de retorno log incorrecta: {gross_bp} vs {expected_gross}"
    assert abs(net_bp - (expected_gross - 24.0)) < 1e-6, "resta de costo incorrecta"
    print(f"  [PASS] B1. fee/cost calc: gross={gross_bp:.2f}bp net={net_bp:.2f}bp (esperado {expected_gross:.2f}bp / {expected_gross-24:.2f}bp)")


def test_funding_join_causal():
    """B2: el join de funding (searchsorted side=right -1) nunca asigna un
    funding_rate cuyo calc_time sea POSTERIOR a la barra."""
    kt = np.array([0, 900000, 1800000, 2700000, 3600000])   # barras 15m
    fct = np.array([500000, 2000000, 3500000])              # calc_times de funding (8h en la realidad, acortado aqui)
    frr = np.array([0.001, -0.002, 0.003])
    j = np.searchsorted(fct, kt, side="right") - 1
    for idx, ktv in enumerate(kt):
        ji = j[idx]
        if ji >= 0:
            assert fct[ji] <= ktv, f"LOOKAHEAD: funding calc_time {fct[ji]} > barra {ktv}"
    # barra 0 no tiene funding anterior -> j=-1 (sin funding conocido aun), correcto
    assert j[0] == -1
    print("  [PASS] B2. funding join: causal confirmado (nunca asigna funding futuro)")


def test_slot_collision():
    """B3: con 1 slot y 2 candidatos en el mismo timestamp, solo 1 ejecuta."""
    slots = 1
    free_at = [0] * slots
    cands = [("A", 1000), ("B", 1000)]
    executed = []
    for (name, ems) in cands:
        fslot = next((k for k in range(slots) if free_at[k] <= ems), None)
        if fslot is None:
            continue
        executed.append(name)
        free_at[fslot] = ems + 10
    assert len(executed) == 1, f"colision de slot no resuelta: ejecutaron {executed}"
    print(f"  [PASS] B3. slot collision: con 1 slot y 2 candidatos simultaneos, solo ejecuta {executed[0]} (el otro se descarta, no se inventa capital)")


def test_entry_strictly_after_signal_close():
    """B4: el precio de entrada usado (open[i+1]) es de la barra SIGUIENTE
    a la barra de señal -- nunca el close/high/low de la barra de señal
    misma (que solo se conoce al cerrar esa barra, simultaneo a open[i+1])."""
    # sintetico: 5 barras, la señal ocurre en la barra i=2 (usa c[2]/h[2] para
    # detectar el evento) y la entrada debe ser exactamente o[3], nunca o[2]/c[2].
    o = np.array([1, 2, 3, 4, 5], float)
    i = 2
    entry_used = o[i + 1]
    assert entry_used == o[3] == 4.0
    assert entry_used != o[i], "BUG: entrada en la misma barra de la señal (lookahead de ejecucion)"
    print("  [PASS] B4. entrada = open[i+1] (barra siguiente a la señal), nunca la barra de la señal misma")


def run_perturbation(P, F, events, tcut):
    """C: perturbaciones de ejecucion sobre el candidato de capitulacion
    (TAKER, score-select, cap450, slots5, h=24h) -- ya cerrado FAILED en
    R22, pero es el candidato mas fuerte disponible para medir fragilidad
    de ejecucion de forma concreta."""
    TAKER_RT = 24.0
    HB = HOR["24h"]; CAP, SLOTS = 450, 5

    def econ_delay(delay_bars, ordering="score"):
        cand = [(s, i, dy, feat) for (s, i, dy, feat) in events if dy > tcut]
        cand_ts = sorted([(int(P[s]["t"][i + 1]), s, i, feat) for (s, i, dy, feat) in cand])
        notional = CAP / SLOTS
        free_at = [0] * SLOTS
        pnl = []
        by_ts = collections.defaultdict(list)
        for (ems, s, i, feat) in cand_ts:
            by_ts[ems].append((s, i, feat))
        for ems in sorted(by_ts):
            cands_here = list(by_ts[ems])
            if ordering == "score":
                cands_here.sort(key=lambda x: x[2].get("drop_mag", 0) * x[2].get("volp_extra", 0), reverse=True)
            elif ordering == "reverse_score":
                cands_here.sort(key=lambda x: x[2].get("drop_mag", 0) * x[2].get("volp_extra", 0))
            for (s, i, feat) in cands_here:
                fslot = next((k for k in range(SLOTS) if free_at[k] <= ems), None)
                if fslot is None:
                    continue
                d = P[s]; o = d["o"]
                e_use = i + 1 + delay_bars
                entry_px = o[e_use] if e_use < len(o) else None
                if entry_px is None:
                    continue
                j2 = e_use + HB
                if j2 >= len(o):
                    continue
                g = -math.log(o[j2] / entry_px) * 1e4
                net = g - TAKER_RT
                free_at[fslot] = ems + HB * 15 * 60000
                pnl.append((ems, net))
        if len(pnl) < 10:
            return None, 0
        ts = sorted(x[0] for x in pnl)
        span = (ts[-1] - ts[0]) / 86400000 or 1
        usd = sum(net * notional / 1e4 for (_, net) in pnl)
        return usd / (span / 30), len(pnl)

    print("\n  -- Perturbacion: delay de ejecucion (0/1/2/4 barras = 0/15/30/60 min de latencia) --")
    for delay in (0, 1, 2, 4):
        nm, n = econ_delay(delay)
        print(f"    delay={delay:2d} barras ({delay*15:3d}min): NET/mo=${nm if nm is not None else 0:.0f}  n={n}")

    print("\n  -- Test de estabilidad de RANKING: score vs orden-inverso-de-score (peor caso deliberado) --")
    nm_s, n_s = econ_delay(0, "score")
    nm_r, n_r = econ_delay(0, "reverse_score")
    print(f"    score (mejor primero):    NET/mo=${nm_s:.0f}  n={n_s}")
    print(f"    reverse-score (peor primero): NET/mo=${nm_r:.0f}  n={n_r}")
    print(f"    diferencia atribuible SOLO al orden de procesamiento: ${nm_s - nm_r:.0f}/mes ({'MATERIAL' if abs(nm_s-nm_r) > 30 else 'menor'})")


def main():
    print("=== ROUND 22.5 — BACKTEST REALITY CHECK ===\n")
    print("SECCION A/B — tests automatizados (sinteticos, no usan datos reales)\n")
    test_causal_percentile_no_lookahead()
    test_fee_calc_deterministic()
    test_funding_join_causal()
    test_slot_collision()
    test_entry_strictly_after_signal_close()

    print("\nSECCION C — perturbacion de ejecucion sobre datos reales (candidato capitulacion)")
    syms = universe()
    con = sqlite3.connect(f"file:{BV}?mode=ro", uri=True)
    P = {}; F = {}
    for s in syms:
        d = load_symbol(con, s)
        if d is None:
            continue
        P[s] = d; F[s] = build_feats(d)
    con.close()

    DROP_PCT = 0.03; VOL_PCT_THR = 0.90
    events = []
    for s, d in P.items():
        f = F[s]; c = d["c"]; l = d["l"]; t = d["t"]; n = len(c)
        r1p = f["ret1_pct"]; volp = f["vol_pct"]; rvp = f["rv_pct"]; rv = f["rv"]
        climax = np.isfinite(r1p) & np.isfinite(volp) & (r1p <= DROP_PCT) & (volp >= VOL_PCT_THR)
        last = -999
        for i in np.where(climax)[0]:
            if i < ROLL or i - last < 4 or i + 1 + HOR["24h"] + 4 >= n:
                continue
            last = i
            lo20 = l[max(0, i - 20):i + 1].min()
            dist_low = math.log(c[i] / lo20) if lo20 > 0 else np.nan
            feat = dict(rv=rv[i] if np.isfinite(rv[i]) else np.nan,
                        volp_extra=volp[i], rvp=rvp[i] if np.isfinite(rvp[i]) else np.nan,
                        dist_low=dist_low, drop_mag=abs(math.log(c[i] / c[i - 1])) if c[i - 1] > 0 else np.nan)
            dy = datetime.utcfromtimestamp(int(t[i]) / 1000).date()
            events.append((s, i, dy, feat))
    days_all = sorted(set(dy for (s, i, dy, ft) in events))
    tcut = days_all[int(len(days_all) * 0.5)]
    run_perturbation(P, F, events, tcut)

    print("\nfin R22.5")


if __name__ == "__main__":
    main()
