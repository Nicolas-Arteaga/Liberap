"""Chequeos de integridad que invalidan informes antes de emitir veredictos."""
from __future__ import annotations
import bisect
from collections import Counter
from statistics import variance

def check_trade(adapter, trade, rows, audit_row):
    opens=[row[0] for row in rows]
    tolerance=max(abs(trade['entry'])*0.001, 1e-12)
    if getattr(adapter, 'population', 'raw') == 'real':
        i=bisect.bisect_right(opens, trade['open_ms'])-1
        price_ok=i >= 0 and rows[i][2]-tolerance <= trade['entry'] <= rows[i][1]+tolerance
    else:
        # Replay: la señal se ejecuta al cierre de la vela que termina en open_ms.
        i=bisect.bisect_left(opens, trade['open_ms'])-1
        expected=rows[i][3] if i >= 0 else None
        price_ok=expected is not None and abs(trade['entry']-expected)<=max(abs(trade['entry'])*1e-8,1e-12)
    start=bisect.bisect_right(opens, trade['open_ms'])
    no_prior=all(row[0] > trade['open_ms'] for row in rows[start:start+1])
    exit_ok=audit_row['age_h'] >= 0
    split_ok=audit_row['split']==adapter.split_of(trade['open_ms'])
    return {'entry_price_observable':price_ok,'no_pre_entry_candle':no_prior,
            'no_exit_before_entry':exit_ok,'split_at_entry':split_ok}

def summarize(adapter, checked, audit_rows):
    counts=Counter()
    for item in checked:
        for key, value in item.items(): counts[key]+=int(bool(value))
    n=len(checked)
    fwd=[row['fwd'][1] for row in audit_rows if row['fwd'][1] is not None]
    days=len({row['day'] for row in audit_rows})
    checks={key:{'status':'PASS' if n and value==n else 'FAIL','pass_n':value,'n':n}
            for key,value in counts.items()}
    checks['forward_1h_variance']={'status':'PASS' if len(fwd)>1 and variance(fwd)>0 else 'FAIL',
        'variance':variance(fwd) if len(fwd)>1 else None,'n':len(fwd)}
    checks['sample_counts']={'status':'PASS','n':len(audit_rows),'n_days':days,
        'splits':dict(Counter(row['split'] for row in audit_rows))}
    return {'valid':all(value['status']=='PASS' for value in checks.values()),'checks':checks}
