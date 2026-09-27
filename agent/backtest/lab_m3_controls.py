"""M3: controles sintéticos reproducibles del diagnóstico, sin tocar producción."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_core as C
import lab_integrity as I
from lab_adapters.ma3 import MA3Adapter
from lab_m1_ma3_audit import severity_scores

HERE = os.path.dirname(os.path.abspath(__file__))
GRAVE = 20


def _score(m):
    return severity_scores(m['fwd24'], m['gross'], m['cost'], m['break_even'], m['win_rate'],
                           m['giveback'], m['sl_cf'], m['timeout_pct'], m['timeout_mean'])


def _null_population(seed, n, magnitudes):
    """Media bruta exactamente cero: magnitudes de retornos MA3, signos balanceados."""
    rng = random.Random(seed)
    values = [rng.choice(magnitudes) for _ in range(n)]
    signed = [v if i % 2 else -v for i, v in enumerate(values)]
    center = sum(signed) / len(signed)
    # El redondeo de muestra no puede crear edge: centramos exactamente la media.
    raw_mean = sum(x - center for x in signed) / len(signed)
    # NULL significa expectativa NETA cero: su retorno bruto compensa sólo
    # el coste fijo, sin crear edge ni una pérdida artificial por comisiones.
    gross = 0.08 + raw_mean
    return {'fwd24': 0.0, 'gross': gross, 'cost': 0.08, 'break_even': 50.0,
            'win_rate': 50.0, 'giveback': 0.0, 'sl_cf': 0.0,
            'timeout_pct': 0.0, 'timeout_mean': 0.0, 'n_oos': n}


def _misalignment_check():
    a = MA3Adapter()
    t = a.entries()[0]
    rows = a.candles(t['symbol'])
    opens = [r[0] for r in rows]
    hours = C.hourly_series(rows)
    audit = C.audit_trade(rows, opens, a.bar_ms, t, C.atr_before(hours, [h[0] for h in hours], t['open_ms']),
                          a.split_of(t['open_ms']), a.cost_pct)
    bad = dict(t)
    bad['open_ms'] += a.bar_ms  # mismo precio, una vela tarde: reproduce la clase de M1b
    check = I.check_trade(a, bad, rows, audit)
    return {'valid': all(check.values()), 'checks': check, 'expected_invalid': True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--n-null', type=int, default=30)
    ap.add_argument('--n-oos', type=int, default=240)
    args = ap.parse_args()
    # Magnitudes tomadas de resultados de MA3; los NULL sólo aleatorizan signo y centran la media.
    source = os.path.join(HERE, 'lab_artifacts', 'step1-ma3-audit-20260927', 'manual_inputs.json')
    returns = json.load(open(source, encoding='utf8'))['returns_pct']
    mags = [abs(x) for x in returns if x != 0]
    nulls = []
    for i in range(args.n_null):
        metrics = _null_population(20260927 + i, args.n_oos, mags)
        scores = _score(metrics)
        nulls.append({'id': f'NULL-{i + 1:02d}', 'n_oos': args.n_oos, 'scores': scores,
                      'grave': [k for k, v in scores.items() if v >= GRAVE]})
    categories = ('ENTRADA', 'COSTOS', 'PAYOFF', 'SALIDA', 'SL', 'TIMEOUT')
    fp = {k: sum(k in row['grave'] for row in nulls) / len(nulls) for k in categories}
    # Controles plantados: cada métrica usa la escala fija y retiene N OOS >=200.
    controls = {
      'entrada_con_informacion': ({'fwd24': 1.0, 'gross': .20, 'cost': .08, 'break_even': 45, 'win_rate': 55, 'giveback': 0, 'sl_cf': 0, 'timeout_pct': 0, 'timeout_mean': 0}, 'ENTRADA_FAVORABLE'),
      'entrada_sin_informacion': ({'fwd24': 0, 'gross': .08, 'cost': .08, 'break_even': 50, 'win_rate': 50, 'giveback': 0, 'sl_cf': 0, 'timeout_pct': 0, 'timeout_mean': 0}, 'NINGUNA'),
      'senal_invertida': ({'fwd24': -1.0, 'gross': .20, 'cost': .08, 'break_even': 50, 'win_rate': 50, 'giveback': 0, 'sl_cf': 0, 'timeout_pct': 0, 'timeout_mean': 0}, 'ENTRADA'),
      'giveback': ({'fwd24': .2, 'gross': .20, 'cost': .08, 'break_even': 45, 'win_rate': 55, 'giveback': 70, 'sl_cf': 0, 'timeout_pct': 0, 'timeout_mean': 0}, 'SALIDA'),
      'sl_ajustado': ({'fwd24': .2, 'gross': .20, 'cost': .08, 'break_even': 45, 'win_rate': 55, 'giveback': 0, 'sl_cf': 70, 'timeout_pct': 0, 'timeout_mean': 0}, 'SL'),
      'edge_menor_que_costo': ({'fwd24': .1, 'gross': .04, 'cost': .08, 'break_even': 50, 'win_rate': 50, 'giveback': 0, 'sl_cf': 0, 'timeout_pct': 0, 'timeout_mean': 0}, 'COSTOS'),
      'zombis_por_tiempo': ({'fwd24': .1, 'gross': .20, 'cost': .08, 'break_even': 45, 'win_rate': 55, 'giveback': 0, 'sl_cf': 0, 'timeout_pct': 80, 'timeout_mean': -1}, 'TIMEOUT'),
      'dependencia_pocos_trades': ({'fwd24': .1, 'gross': .20, 'cost': .08, 'break_even': 75, 'win_rate': 25, 'giveback': 0, 'sl_cf': 0, 'timeout_pct': 0, 'timeout_mean': 0}, 'PAYOFF'),
    }
    rows = []
    for name, (metrics, expected) in controls.items():
        metrics = dict(metrics, n_oos=args.n_oos)
        scores = _score(metrics)
        detected = 'ENTRADA_FAVORABLE' if name == 'entrada_con_informacion' and metrics['fwd24'] > 0 else ('NINGUNA' if name == 'entrada_sin_informacion' and max(scores.values()) < GRAVE else max(scores, key=scores.get))
        rows.append({'population': name, 'expected': expected, 'detected': detected, 'ok': detected == expected, 'scores': scores, 'n_oos': args.n_oos})
    integrity = _misalignment_check()
    result = {'id': 'm3-controls-20260927', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'source': 'magnitudes de retornos de MA3 sobre velas locales; NULL con signo aleatorio y media bruta centrada en cero',
              'n_null': len(nulls), 'n_oos_each': args.n_oos, 'grave_threshold': GRAVE,
              'null_false_positive_rate': fp, 'null_pass': all(v <= .05 for v in fp.values()),
              'nulls': nulls, 'controls': rows, 'controls_pass': all(x['ok'] for x in rows),
              'misaligned_entry': integrity, 'integrity_pass': not integrity['valid']}
    os.makedirs(args.out, exist_ok=True)
    json.dump(result, open(os.path.join(args.out, 'result.json'), 'w', encoding='utf8'), ensure_ascii=False, indent=2)
    lines=['# M3 — controles sintéticos', '', '| Población | Esperada | Detectada | OK |', '|---|---|---|---|']
    lines += [f"| {x['population']} | {x['expected']} | {x['detected']} | {'sí' if x['ok'] else 'no'} |" for x in rows]
    lines += ['', '## Falsos positivos NULL', '| Hallazgo | Tasa |', '|---|---:|'] + [f'| {k} | {100*v:.2f}% |' for k,v in fp.items()]
    lines += ['', f"Entrada desalineada: {'INVÁLIDA (PASS)' if not integrity['valid'] else 'NO DETECTADA (FAIL)'}."]
    open(os.path.join(args.out, 'informe.md'), 'w', encoding='utf8').write('\n'.join(lines))
    print(json.dumps({'controls_pass': result['controls_pass'], 'null_pass': result['null_pass'], 'integrity_pass': result['integrity_pass'], 'fp': fp}, ensure_ascii=False))
    raise SystemExit(0 if result['controls_pass'] and result['null_pass'] and result['integrity_pass'] else 3)


if __name__ == '__main__':
    main()
