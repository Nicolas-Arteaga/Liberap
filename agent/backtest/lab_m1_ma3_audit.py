"""CLI M1 compatible: delega la auditoría común en :mod:`lab_audit`."""
from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import lab_audit as A
from lab_adapters import get_adapter

STRATEGY = os.environ.get('LAB_AUDIT_STRATEGY', 'ma3')
OUT = os.environ.get('LAB_AUDIT_OUT', f'/app/backtest/lab_artifacts/m1-{STRATEGY}-20260926')


def write_progress(status, processed=0, total=0, **extra):
    payload = {'id': f'm1-{STRATEGY}-20260926', 'status': status,
               'processed': processed, 'total': total,
               'updated_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'progress.json'), 'w', encoding='utf8') as handle:
        json.dump(payload, handle, indent=2)


# Compatibilidad para tests/importadores históricos; no duplica fórmulas.
mean = A.mean
pct = A.pct
fmt = A.fmt
headline = A.headline
severity_scores = A.severity_scores
day_block_ci = A.day_block_ci
WHY = A.WHY


def main():
    adapter = get_adapter(STRATEGY)
    entries = adapter.entries()
    write_progress('running', 0, len(entries), started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    result, report, returns = A.audit_adapter(
        adapter, entries,
        lambda processed, total, done, symbols: write_progress(
            'running', processed, total, symbols_done=done, symbols_total=symbols),
    )
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'result.json'), 'w', encoding='utf8') as handle:
        json.dump(result, handle, indent=2)
    with open(os.path.join(OUT, 'manual_inputs.json'), 'w', encoding='utf8') as handle:
        json.dump({'returns_pct': returns}, handle)
    with open(os.path.join(OUT, 'informe.md'), 'w', encoding='utf8') as handle:
        handle.write(report)
    write_progress('completed', result['n'], len(entries),
                   finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), result='result.json')
    print(json.dumps({'out': OUT, 'n': result['n'], 'main': result['main_area']}))


if __name__ == '__main__':
    main()
