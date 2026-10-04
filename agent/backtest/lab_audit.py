"""Auditoría genérica del Laboratorio: integridad M1b y severidad fija.

No conoce la estrategia. Recibe un ``Adapter`` ya normalizado y conserva las
fórmulas históricas de ``lab_m1_ma3_audit.py`` sin cambios.
"""
from __future__ import annotations

import random
from collections import defaultdict

import lab_core as C
import lab_integrity as I


WHY = {
    'ENTRADA': 'El intervalo incluye valores negativos y positivos: la señal no demuestra por sí sola que anticipe el movimiento.',
    'COSTOS': 'La diferencia entre bruto y neto muestra cuánto margen pierde la estrategia antes de poder ejecutar un trade real.',
    'PAYOFF': 'La comparación con el equilibrio muestra si el tamaño de ganadores compensa la frecuencia de pérdidas.',
    'SALIDA': 'Una ganancia flotante que vuelve a pérdida no paga el resultado final; aquí se cuantifica ese desperdicio.',
    'SL': 'El contrafactual separa un stop protector de uno que corta ganadores que habrían alcanzado el objetivo.',
    'TIMEOUT': 'El retorno de las posiciones que expiran indica si el tiempo está cerrando riesgo útil o capital estancado.',
}


def mean(x):
    return sum(x) / len(x) if x else None


def pct(n, d):
    return 100 * n / d if d else None


def fmt(x):
    return 'n/a' if x is None else f'{x:.2f}'


def headline(net, gross, cost, main, severity):
    if net >= 0:
        return f'La estrategia GANA {fmt(net)} % neto por trade, pero es frágil: el edge bruto ({fmt(gross)} %) apenas supera el costo ({fmt(cost)} %). ' + (f'El daño más alto medido es {main} ({severity[main]}/100).' if severity[main] >= 20 else 'Ninguna causa domina con el umbral de severidad actual.')
    return f'La estrategia PIERDE {fmt(net)} % neto por trade. La causa de mayor severidad medida es {main} ({severity[main]}/100).'


def severity_scores(fwd24, gross, cost, breakeven, win_rate, gave_back_pct, sl_cf_pct, timeout_pct, timeout_mean):
    """Escala fija 0..100; M3 considera grave un puntaje desde 20."""
    cost_deficit = max(0.0, cost - (gross or 0.0))
    return {
        'ENTRADA': min(100, round(max(0, -(fwd24 or 0)) * 20)),
        'COSTOS': min(100, round(100 * cost_deficit / max(cost, 1e-12))),
        'PAYOFF': min(100, round(max(0, (breakeven or 0) - (win_rate or 0)))),
        'SALIDA': round(gave_back_pct or 0),
        'SL': round(sl_cf_pct or 0),
        'TIMEOUT': min(100, round((timeout_pct or 0) * max(0, -(timeout_mean or 0)))),
    }


def day_block_ci(rows, horizon, rounds=1000):
    by_day = defaultdict(list)
    for row in rows:
        value = row['fwd'][horizon]
        if value is not None:
            by_day[row['day']].append(value)
    days = sorted(by_day)
    if not days:
        return {'mean': None, 'lo': None, 'hi': None, 'n_days': 0, 'n': 0}
    rng = random.Random(20260926 + horizon)
    samples = []
    for _ in range(rounds):
        selected = [days[rng.randrange(len(days))] for _ in days]
        values = [v for day in selected for v in by_day[day]]
        samples.append(mean(values))
    samples.sort()
    return {
        'mean': mean([v for values in by_day.values() for v in values]),
        'lo': samples[int(.025 * (rounds - 1))],
        'hi': samples[int(.975 * (rounds - 1))],
        'n_days': len(days),
        'n': sum(map(len, by_day.values())),
    }


def audit_adapter(adapter, entries=None, progress=None, execution_variant=None):
    """Produce el ``result.json`` y el informe M1b para cualquier Adapter.

    ``progress(processed, total, symbols_done, symbols_total)`` es opcional y
    no interviene en cálculos ni en el resultado.
    """
    entries = adapter.entries() if entries is None else list(entries)
    by = defaultdict(list)
    for trade in entries:
        by[trade['symbol']].append(trade)
    rows, integrity = [], []
    for symbol_index, (symbol, trades) in enumerate(by.items(), 1):
        candles = adapter.candles(symbol)
        opens = [row[0] for row in candles]
        hours = C.hourly_series(candles)
        hour_starts = [row[0] for row in hours]
        for trade in trades:
            audit = C.audit_trade(candles, opens, adapter.bar_ms, trade,
                                  C.atr_before(hours, hour_starts, trade['open_ms']),
                                  adapter.split_of(trade['open_ms']), adapter.cost_pct)
            if execution_variant:
                px, reason = C.simulate(candles, opens, adapter.bar_ms, trade,
                                        execution_variant, 'unconditional', -2.0,
                                        C.atr_before(hours, hour_starts, trade['open_ms']))
                audit['ret'] = C.pct(trade['side'], trade['entry'], px) - adapter.cost_pct
                audit['reason'] = reason
            rows.append(audit)
            integrity.append(I.check_trade(adapter, trade, candles, audit))
        if progress and (symbol_index % 25 == 0 or symbol_index == len(by)):
            progress(len(rows), len(entries), symbol_index, len(by))
    wins = [row for row in rows if row['ret'] > 0]
    losses = [row for row in rows if row['ret'] <= 0]
    fwd = {horizon: day_block_ci(rows, horizon) for horizon in C.FWD_HOURS}
    integrity_report = I.summarize(adapter, integrity, rows)
    gross = mean([row['ret'] + adapter.cost_pct for row in rows])
    net = mean([row['ret'] for row in rows])
    win_rate = pct(len(wins), len(rows))
    avg_win = mean([row['ret'] for row in wins])
    avg_loss = abs(mean([row['ret'] for row in losses]))
    breakeven = 100 * avg_loss / (avg_loss + avg_win) if avg_win and avg_loss else None
    reached = [row for row in rows if row['mfe'] >= 2]
    gave_back = sum(row['ret'] < 0 for row in reached)
    sl = [row for row in rows if row['reason'] == 'SL']
    sl_cf = sum(bool(row['cf_sl_reaches_tp']) for row in sl)
    timeout = [row for row in rows if row['reason'].startswith('timeout')]
    reasons = {
        key: {'n': len(group), 'pct': pct(len(group), len(rows)),
              'mean_return': mean([row['ret'] for row in group])}
        for key, group in ((key, [row for row in rows if row['reason'] == key])
                           for key in sorted(set(row['reason'] for row in rows)))
    }
    timeout_mean = mean([row['ret'] for row in timeout])
    severity = severity_scores(fwd[24]['mean'], gross, adapter.cost_pct, breakeven,
                               win_rate, pct(gave_back, len(reached)), pct(sl_cf, len(sl)),
                               pct(len(timeout), len(rows)), timeout_mean)
    main_area = max(severity, key=severity.get)
    # Fase C decide exclusivamente con TRAIN/VALIDATION. OOS queda presente
    # como evidencia separada y no interviene en la elección de variante.
    split_metrics = {}
    for split in ('TRAIN', 'VALIDATION', 'OOS'):
        subset = [row for row in rows if row['split'] == split]
        subset_wins = [row for row in subset if row['ret'] > 0]
        subset_losses = [row for row in subset if row['ret'] <= 0]
        subset_avg_win = mean([row['ret'] for row in subset_wins])
        subset_avg_loss = abs(mean([row['ret'] for row in subset_losses])) if subset_losses else None
        subset_be = (100 * subset_avg_loss / (subset_avg_loss + subset_avg_win)
                     if subset_avg_win and subset_avg_loss else None)
        subset_reached = [row for row in subset if row['mfe'] >= 2]
        subset_sl = [row for row in subset if row['reason'] == 'SL']
        subset_timeout = [row for row in subset if row['reason'].startswith('timeout')]
        subset_timeout_mean = mean([row['ret'] for row in subset_timeout])
        split_metrics[split] = {
            'n': len(subset),
            'net_expectancy_pct': mean([row['ret'] for row in subset]),
            'gross_edge_pct': mean([row['ret'] + adapter.cost_pct for row in subset]),
            'severity': severity_scores(
                mean([row['fwd'][24] for row in subset if row['fwd'][24] is not None]),
                mean([row['ret'] + adapter.cost_pct for row in subset]), adapter.cost_pct,
                subset_be, pct(len(subset_wins), len(subset)),
                pct(sum(row['ret'] < 0 for row in subset_reached), len(subset_reached)),
                pct(sum(bool(row['cf_sl_reaches_tp']) for row in subset_sl), len(subset_sl)),
                pct(len(subset_timeout), len(subset)), subset_timeout_mean),
        }
    result = {
        'valid': integrity_report['valid'], 'integrity': integrity_report, 'n': len(rows),
        'forward_return_pct_day_block_ci': fwd, 'gross_edge_pct': gross,
        'cost_pct': adapter.cost_pct, 'net_expectancy_pct': net, 'win_rate_pct': win_rate,
        'break_even_win_rate_pct': breakeven, 'avg_win_pct': avg_win, 'avg_loss_pct': avg_loss,
        'reached_2pct_n': len(reached), 'reached_2pct_ended_loss_pct': pct(gave_back, len(reached)),
        'sl_n': len(sl), 'sl_cf_reaches_tp_pct': pct(sl_cf, len(sl)),
        'timeout_n': len(timeout), 'timeout_pct': pct(len(timeout), len(rows)),
        'timeout_mean_return_pct': timeout_mean, 'reasons': reasons, 'severity': severity,
        'severity_formula': 'ENTRADA=max(0,-media_24h*20); COSTOS=max(0,-edge_bruto*20); PAYOFF=max(0,win_equilibrio-win_real); SALIDA=porcentaje que llegó a +2% y terminó en pérdida; SL=porcentaje contrafactual que habría llegado al TP; TIMEOUT=porcentaje_timeout*max(0,-retorno_timeout). Frecuencia sin daño no suma. Todo limitado a 0..100.',
        'main_area': main_area, 'fidelity': adapter.fidelity_result,
        'split_metrics': split_metrics,
    }
    facts = {
        'ENTRADA': 'Retorno medio 1/4/12/24/48h con IC bootstrap por día: ' + ', '.join(f'{h}h={fmt(fwd[h]["mean"])}% [{fmt(fwd[h]["lo"])}, {fmt(fwd[h]["hi"])}], n={fwd[h]["n"]}, días={fwd[h]["n_days"]}' for h in C.FWD_HOURS),
        'COSTOS': f'Bruto {fmt(gross)}% y costo {adapter.cost_pct:.2f}%',
        'PAYOFF': f'Win rate {fmt(win_rate)}% vs equilibrio {fmt(breakeven)}%',
        'SALIDA': f'{len(reached)} llegaron a +2%; {fmt(pct(gave_back, len(reached)))}% terminaron perdiendo',
        'SL': f'{len(sl)} SL; {fmt(pct(sl_cf, len(sl)))}% habría llegado a TP sin SL',
        'TIMEOUT': f'{len(timeout)} timeout ({fmt(pct(len(timeout), len(rows)))}%), retorno {fmt(timeout_mean)}%',
    }
    lines = [f'# Auditoría {adapter.definition.display_name} — {len(rows)} trades', '## Chequeos de integridad']
    lines += [f'- {name}: {data["status"]}.' for name, data in integrity_report['checks'].items()]
    if not integrity_report['valid']:
        lines += ['', '**INFORME INVÁLIDO: falló un chequeo de integridad; no se publican veredictos.**']
    else:
        lines += ['## TITULAR', headline(net, gross, adapter.cost_pct, main_area, severity), '## Resultado simple', f'- Win rate {fmt(win_rate)} %; equilibrio {fmt(breakeven)} %; ganancia media {fmt(avg_win)} % y pérdida media {fmt(avg_loss)} %.', '## Hallazgos']
        for key in severity:
            lines += [f'### [{key}] — severidad {severity[key]}/100', f'QUÉ PASA: {facts[key]}.', f'POR QUÉ IMPORTA: {WHY[key]}', f'EVIDENCIA: n={len(rows)}, `result.json`.', 'CONFIANZA: BAJA; no son selecciones reales de producción.', 'Qué NO se puede concluir: no prueba que cambiar solo esta regla mejore producción.']
        lines += ['## Motivos de salida', '| Motivo | N | % | Retorno medio |', '|---|---:|---:|---:|'] + [f'| {key} | {value["n"]} | {fmt(value["pct"])} | {fmt(value["mean_return"])} |' for key, value in reasons.items()] + ['## Qué no se pudo evaluar', adapter.fidelity_note, '## Qué haría alguien no técnico con esto', '- No cambiaría la estrategia en producción a partir de este informe.', '- Vigilaría las ganancias que superan +2 % porque muchas terminan en pérdida.', '- Esperaría la validación contra el ledger antes de modificar la salida.']
    return result, '\n'.join(lines), [row['ret'] for row in rows]
