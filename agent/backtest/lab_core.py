"""Núcleo de la máquina de diagnóstico (Fase 3): simulador unificado, agregación y veredicto.

Diagnóstico solamente. No modela selección de producción, sizing ni PnL en dólares.
Todo resultado es HIPÓTESIS sobre la población que entregue el adaptador.

El simulador unificado reproduce, bit a bit, `fase2_ma3_broad_matrix.exit_trade` (variantes
baseline/tp_short_50/giveback_*/break_even_1r/trailing_2r) y `fase2b_ma3_exit_variants.exit_new`
(sl_atr_*/time_*); `lab_diagnose.py --selftest` lo verifica contra ambos.
"""
from __future__ import annotations

import bisect

HOUR = 3_600_000
ATR_PERIOD = 14
CEILING_H = 720
TIMEOUT_H = 48

SCENARIOS = (("unconditional", -2.0), ("unconditional", 2.0), ("conditional", -2.0), ("conditional", 2.0))
SCEN_KEYS = tuple(f"{mode}|tp_bias_{bias:+.0f}" for mode, bias in SCENARIOS)

DIRECTION_VARIANTS = ("inverted",)
EXIT_VARIANTS = ("tp_short_50", "giveback_10", "giveback_25", "giveback_50", "break_even_1r",
                 "trailing_2r", "time_exit_12h", "time_exit_24h", "time_exit_36h", "time_stop_24h_if_losing")
SL_VARIANTS = ("sl_atr_1.0", "sl_atr_1.5", "sl_atr_2.0")
ALL_VARIANTS = ("baseline",) + DIRECTION_VARIANTS + EXIT_VARIANTS + SL_VARIANTS
NON_BASELINE = ALL_VARIANTS[1:]

# Mínimo de señales OOS para permitir la etiqueta CORREGIBLE-ROBUSTO / INVERTIDA-ROBUSTA.
MIN_OOS_FOR_ROBUST = 200


def pct(side: int, entry: float, price: float) -> float:
    """side 1 = short (gana si el precio baja), side 0 = long."""
    return (entry - price) / entry * 100.0 if side == 1 else (price - entry) / entry * 100.0


def trade_side(trade, variant):
    """Lado efectivo con el que se mide el retorno de la variante (la invertida opera el lado contrario)."""
    return 1 - trade["side"] if variant == "inverted" else trade["side"]


# ----------------------------------------------------------------------------- velas / ATR
def hourly_series(rows):
    """Agrega velas de cualquier tamaño a velas 1h: (bucket_start, high, low, close)."""
    out, cur = [], None
    for ot, high, low, close in rows:
        bucket = ot - (ot % HOUR)
        if cur is None or cur[0] != bucket:
            if cur is not None:
                out.append(tuple(cur))
            cur = [bucket, high, low, close]
        else:
            if high > cur[1]:
                cur[1] = high
            if low < cur[2]:
                cur[2] = low
            cur[3] = close
    if cur is not None:
        out.append(tuple(cur))
    return out


def atr_before(hours, hour_starts, open_ms):
    """Media simple de los últimos 14 True Range de velas 1h cerradas antes de open_ms (criterio de producción)."""
    end = bisect.bisect_right(hour_starts, open_ms - HOUR)
    if end < ATR_PERIOD + 1:
        return None
    trs = []
    for i in range(end - ATR_PERIOD, end):
        _, high, low, _ = hours[i]
        prev_close = hours[i - 1][3]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / ATR_PERIOD


# ----------------------------------------------------------------------------- simulador
def simulate(rows, opens, bar_ms, trade, variant, mode, bias_pp, atr):
    """Devuelve (precio_de_salida, motivo). SL se evalúa antes que TP dentro de la misma vela."""
    entry, side, sl0, tp0 = trade["entry"], trade["side"], trade["sl"], trade["tp"]
    if variant == "inverted":
        side, sl0, tp0 = 1 - side, 2 * entry - sl0, 2 * entry - tp0
        variant = "baseline"
    risk = abs(entry - sl0)
    tp = tp0 if variant != "tp_short_50" else entry + (tp0 - entry) * 0.5
    sl = sl0
    if variant.startswith("sl_atr_") and atr:
        k = float(variant.split("_")[2])
        dist = min(abs(entry - sl0), k * atr)
        sl = entry + dist if side == 1 else entry - dist
    time_hours = {"time_exit_12h": 12, "time_exit_24h": 24, "time_exit_36h": 36}.get(variant)
    give = float(variant.split("_")[1]) if variant.startswith("giveback_") else None
    open_ms = trade["open_ms"]
    start = bisect.bisect_right(opens, open_ms)
    ceiling, timeout = CEILING_H * HOUR, TIMEOUT_H * HOUR
    max_fav = 0.0
    breakeven = False
    be_thresh = risk / entry * 100.0
    for ot, high, low, close in rows[start:]:
        age = ot + bar_ms - open_ms
        if age > ceiling:
            return close, "timeout_hard_720"
        fav = pct(side, entry, low if side == 1 else high)
        if fav > max_fav:
            max_fav = fav
        if variant == "break_even_1r" and max_fav >= be_thresh:
            breakeven = True
        eff_sl = entry if breakeven else sl
        if side == 1:
            if high >= eff_sl:
                return eff_sl, "break_even" if breakeven else "SL"
            if low <= tp:
                return tp * (1 - bias_pp / 100.0), "TP"
        else:
            if low <= eff_sl:
                return eff_sl, "break_even" if breakeven else "SL"
            if high >= tp:
                return tp * (1 + bias_pp / 100.0), "TP"
        if give is not None and max_fav > 0:
            if max_fav - pct(side, entry, close) >= max_fav * give / 100.0:
                return close, "giveback"
        if variant == "trailing_2r" and max_fav >= 2 * be_thresh:
            if max_fav - pct(side, entry, close) >= 2 * be_thresh:
                return close, "trailing"
        if time_hours and age >= time_hours * HOUR:
            return close, "time_exit"
        if variant == "time_stop_24h_if_losing" and age >= 24 * HOUR and pct(side, entry, close) < 0:
            return close, "time_stop"
        if age >= timeout:
            if mode == "unconditional" or pct(side, entry, close) < 0:
                return close, "timeout_48"
    return rows[-1][3], "nodata"


# ----------------------------------------------------------------------------- trayectoria
def path_metrics(rows, opens, bar_ms, trade):
    """MFE/MAE/giveback/tiempo a MFE en ventana de 48 h con velas COMPLETAS posteriores a la entrada."""
    entry, side, open_ms = trade["entry"], trade["side"], trade["open_ms"]
    start = bisect.bisect_right(opens, open_ms)
    end = bisect.bisect_right(opens, open_ms + TIMEOUT_H * HOUR - bar_ms)
    window = rows[start:end]
    if len(window) < 2:
        return None
    fav = [pct(side, entry, r[2] if side == 1 else r[1]) for r in window]
    adv = [pct(side, entry, r[1] if side == 1 else r[2]) for r in window]
    peak = max(range(len(fav)), key=fav.__getitem__)
    mfe = max(0.0, fav[peak])
    final = pct(side, entry, window[-1][3])
    t_mfe = (window[peak][0] + bar_ms - open_ms) / HOUR
    life = (window[-1][0] + bar_ms - open_ms) / HOUR
    return {"mfe": mfe, "mae": min(adv), "giveback": mfe - final, "t_mfe_h": t_mfe,
            "censored": t_mfe >= 0.9 * life}


# ----------------------------------------------------------------------------- estadística
def mean(values):
    return sum(values) / len(values) if values else None


def median(values):
    if not values:
        return None
    s = sorted(values)
    return s[len(s) // 2]


def _diff(a, b):
    return None if a is None or b is None else a - b


def summarize_matrix(records, split_names, cost_pct):
    """records: iterable de (split, scen_key, variant, net_return). Devuelve dict por escenario/variante."""
    buckets = {}
    for split, scen, variant, net in records:
        buckets.setdefault(scen, {}).setdefault(variant, {}).setdefault(split, []).append(net)
    out = {}
    for scen in SCEN_KEYS:
        by_v = buckets.get(scen, {})
        base = by_v.get("baseline", {})
        base_means = {sp: mean(base.get(sp, [])) for sp in split_names}
        base_top = sorted(base.get("OOS", []), reverse=True)[3:]
        out[scen] = {}
        for variant in ALL_VARIANTS:
            per = by_v.get(variant, {})
            oos = per.get("OOS", [])
            top = sorted(oos, reverse=True)[3:]
            out[scen][variant] = {
                "n_oos": len(oos),
                "oos_mean": mean(oos),
                "oos_median": median(oos),
                "delta_vs_baseline": {sp: _diff(mean(per.get(sp, [])), base_means[sp]) for sp in split_names},
                "oos_without_top3_delta": _diff(mean(top), mean(base_top)),
                "oos_cost_plus_50_mean": _diff(mean(oos), cost_pct * 0.5),
            }
    return out


def passes_criterion(summary, variant):
    """Criterio preregistrado: en LOS CUATRO escenarios Δ OOS > 0, Δ OOS sin top-3 > 0 y Δ > 0 en ≥2 de 3 splits."""
    for scen in SCEN_KEYS:
        row = summary[scen][variant]
        d = row["delta_vs_baseline"]
        if not ((d.get("OOS") or 0) > 0 and (row["oos_without_top3_delta"] or 0) > 0
                and sum(1 for v in d.values() if (v or 0) > 0) >= 2):
            return False
    return True


def worse_everywhere(summary, variant):
    """Δ OOS < 0 y Δ VALIDATION < 0 en los cuatro escenarios."""
    for scen in SCEN_KEYS:
        d = summary[scen][variant]["delta_vs_baseline"]
        if not ((d.get("OOS") or 0) < 0 and (d.get("VALIDATION") or 0) < 0):
            return False
    return True


def verdicts(summary, trajectory, n_oos):
    """Veredicto por componente con reglas transparentes. Etiquetas permitidas:
    CORREGIBLE-ROBUSTO, NO-CORREGIBLE-CON-ESTAS-REGLAS, SIN-EVIDENCIA (más INVERTIDA-ROBUSTA / CORRECTA / INDICIO-DEBIL)."""
    robust_ok = n_oos >= MIN_OOS_FOR_ROBUST
    out = {}

    def label_pass(names):
        return ("CORREGIBLE-ROBUSTO" if robust_ok else "INDICIO-DEBIL (N OOS chico)") + f": {', '.join(names)}"

    # DIRECCIÓN
    if passes_criterion(summary, "inverted"):
        out["DIRECCION"] = "INVERTIDA-ROBUSTA" if robust_ok else "INDICIO-DEBIL: invertida (N OOS chico)"
    elif worse_everywhere(summary, "inverted"):
        out["DIRECCION"] = "CORRECTA (operarla al revés empeora OOS y VAL en los 4 escenarios)"
    else:
        out["DIRECCION"] = "SIN-EVIDENCIA"

    # SALIDA
    passing = [v for v in EXIT_VARIANTS if passes_criterion(summary, v)]
    oos = trajectory.get("OOS") or {}
    mfe_med, gb_med = oos.get("mfe_median"), oos.get("giveback_median")
    material_giveback = mfe_med is not None and gb_med is not None and mfe_med > 0 and gb_med >= 0.5 * mfe_med
    if passing:
        out["SALIDA"] = label_pass(passing)
    elif material_giveback:
        out["SALIDA"] = "NO-CORREGIBLE-CON-ESTAS-REGLAS (giveback material, ninguna regla simple lo corrige en OOS)"
    else:
        out["SALIDA"] = "SIN-EVIDENCIA (no hay giveback material que corregir)"

    # SL
    passing_sl = [v for v in SL_VARIANTS if passes_criterion(summary, v)]
    out["SL"] = label_pass(passing_sl) if passing_sl else "NO-CORREGIBLE-CON-ESTAS-REGLAS (SL por ATR no mejora OOS)"

    out["SELECCION"] = "NO EVALUABLE (falta ledger de escaneo para reproducir la selección de producción)"
    return out

# ----------------------------------------------------------------------------- auditoría (detalle por trade)
FWD_HOURS = (1, 4, 12, 24, 48)


def simulate_detail(rows, opens, bar_ms, trade, mode, atr, no_sl=False, no_tp=False):
    """Baseline (sin sesgo de fill) con detalle: motivo, edad, MFE/MAE hasta la salida (incluye la vela de salida).
    `no_sl` / `no_tp` son contrafactuales para responder "¿qué habría pasado sin ese nivel?"."""
    entry, side, sl, tp = trade["entry"], trade["side"], trade["sl"], trade["tp"]
    open_ms = trade["open_ms"]
    start = bisect.bisect_right(opens, open_ms)
    ceiling, timeout = CEILING_H * HOUR, TIMEOUT_H * HOUR
    max_fav, max_adv = 0.0, 0.0   # max_adv <= 0
    last = None
    for ot, high, low, close in rows[start:]:
        age = ot + bar_ms - open_ms
        fav = pct(side, entry, low if side == 1 else high)
        adv = pct(side, entry, high if side == 1 else low)
        if fav > max_fav:
            max_fav = fav
        if adv < max_adv:
            max_adv = adv
        last = (close, age)
        if age > ceiling:
            return {"px": close, "reason": "timeout_hard_720", "age_h": age / HOUR, "mfe": max_fav, "mae": max_adv}
        if side == 1:
            if not no_sl and high >= sl:
                return {"px": sl, "reason": "SL", "age_h": age / HOUR, "mfe": max_fav, "mae": max_adv}
            if not no_tp and low <= tp:
                return {"px": tp, "reason": "TP", "age_h": age / HOUR, "mfe": max_fav, "mae": max_adv}
        else:
            if not no_sl and low <= sl:
                return {"px": sl, "reason": "SL", "age_h": age / HOUR, "mfe": max_fav, "mae": max_adv}
            if not no_tp and high >= tp:
                return {"px": tp, "reason": "TP", "age_h": age / HOUR, "mfe": max_fav, "mae": max_adv}
        if age >= timeout:
            if mode == "unconditional" or pct(side, entry, close) < 0:
                return {"px": close, "reason": "timeout_48", "age_h": age / HOUR, "mfe": max_fav, "mae": max_adv}
    if last is None:
        return {"px": rows[-1][3], "reason": "nodata", "age_h": 0.0, "mfe": 0.0, "mae": 0.0}
    return {"px": rows[-1][3], "reason": "nodata", "age_h": last[1] / HOUR, "mfe": max_fav, "mae": max_adv}


def forward_returns(rows, opens, bar_ms, trade):
    """Retorno (en la dirección del trade, en %) a 1/4/12/24/48 h desde la entrada. None si no hay velas."""
    entry, side, open_ms = trade["entry"], trade["side"], trade["open_ms"]
    start = bisect.bisect_right(opens, open_ms)
    out = {}
    for h in FWD_HOURS:
        target = open_ms + h * HOUR
        i = bisect.bisect_right(opens, target - bar_ms) - 1
        # No sustituir un horizonte faltante por el último cierre viejo: eso
        # convierte, por ejemplo, un retorno a 4h en uno falsamente etiquetado
        # como retorno a 12h cuando hay un hueco de datos.
        out[h] = pct(side, entry, rows[i][3]) if i >= start and rows[i][0] + bar_ms >= target else None
    return out


def audit_trade(rows, opens, bar_ms, trade, atr, split, cost_pct):
    """Fila de auditoría: todo lo necesario para explicar POR QUÉ este trade ganó o perdió."""
    from datetime import datetime, timezone
    d = simulate_detail(rows, opens, bar_ms, trade, "unconditional", atr)
    entry, side = trade["entry"], trade["side"]
    ret = pct(side, entry, d["px"]) - cost_pct
    sl_dist = abs(entry - trade["sl"]) / entry * 100.0
    tp_dist = abs(entry - trade["tp"]) / entry * 100.0
    cf_tp = None
    if d["reason"] == "SL":   # ¿habría llegado al TP si el SL no existiera (misma vida máxima de 48 h)?
        cf = simulate_detail(rows, opens, bar_ms, trade, "unconditional", atr, no_sl=True)
        cf_tp = cf["reason"] == "TP"
    dt = datetime.fromtimestamp(trade["open_ms"] / 1000, tz=timezone.utc)
    return {"split": split, "symbol": trade["symbol"], "side": side, "day": dt.strftime("%Y-%m-%d"), "month": dt.strftime("%Y-%m"),
            "hour": dt.hour, "reason": d["reason"], "age_h": d["age_h"], "ret": ret, "mfe": d["mfe"], "mae": d["mae"],
            "sl_dist": sl_dist, "tp_dist": tp_dist, "cf_sl_reaches_tp": cf_tp,
            "fwd": forward_returns(rows, opens, bar_ms, trade), "open_ms": trade["open_ms"]}
