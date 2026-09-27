"""Muestreo reproducible de la alineación temporal del stream bruto MA3."""
from __future__ import annotations

import json
import os
import pickle
import random
import sqlite3
from collections import Counter

STREAM = os.environ.get('LAB_MA3_STREAM', '/app/backtest/lab_artifacts/f2-ma3-broad-20260921-0104/raw_ma3_243d.pkl')
DB = os.environ.get('LAB_CANONICAL_DB', '/app/data/binance_vision_clean.db')
HOUR = 3_600_000
BAR = 300_000
SAMPLE = 300

def main() -> int:
    stream = pickle.load(open(STREAM, 'rb'))['stream']
    chosen = random.Random(20260926).sample(stream, min(SAMPLE, len(stream)))
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    offsets, entry_close_matches, before_entry = Counter(), 0, 0
    examples = []
    for b, symbol, entry, _sl, _tp, _side, _rest in chosen:
        # La vela que termina en b+1h es la de offset 11 dentro de la hora b.
        terminal_open = b + 11 * BAR
        row = con.execute("SELECT close FROM klines_5m WHERE symbol=? AND interval='5m' AND open_time=?", (symbol, terminal_open)).fetchone()
        if row is None:
            continue
        offset = (b % HOUR) // BAR
        offsets[int(offset)] += 1
        terminal_close = row[0]
        close_match = abs(float(entry) - float(terminal_close)) <= max(1e-12, abs(float(entry)) * 1e-9)
        entry_close_matches += int(close_match)
        before_entry += int(b < b + HOUR)
        if len(examples) < 5:
            examples.append({'symbol':symbol, 'stream_b':b, 'engine_now_ms':b + HOUR,
                'entry':entry, 'terminal_5m_open':terminal_open, 'terminal_5m_close':terminal_close,
                'matches_terminal_close':close_match})
    n = sum(offsets.values())
    out = {'sample_requested':SAMPLE, 'sample_evaluable':n, 'offsets_5m_from_hour_start':dict(sorted(offsets.items())),
           'all_stream_b_at_hour_start': n > 0 and set(offsets) == {0},
           'entry_matches_close_of_offset_11': {'matches':entry_close_matches,'n':n,'pct':100*entry_close_matches/n if n else None},
           'engine_evaluates_at_b_plus_hour': {'n':n,'pct':100*before_entry/n if n else None},
           'conclusion':'CONFIRMED_DESALIGNED' if n and set(offsets)=={0} and entry_close_matches==n else 'NOT_CONFIRMED',
           'examples':examples}
    print(json.dumps(out, indent=2))
    return 0 if out['conclusion'] == 'CONFIRMED_DESALIGNED' else 1

if __name__ == '__main__':
    raise SystemExit(main())
