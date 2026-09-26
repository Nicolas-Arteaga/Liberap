"""Verificación independiente mínima de los tres números base del informe M1."""
from __future__ import annotations
import json
from pathlib import Path

RUN = Path('/app/backtest/lab_artifacts/m1-ma3-20260926')

def close(a: float, b: float) -> bool:
    return abs(a - b) < 1e-10

def main() -> int:
    returns = json.loads((RUN / 'manual_inputs.json').read_text())['returns_pct']
    report = json.loads((RUN / 'result.json').read_text())
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    win_rate = 100 * len(wins) / len(returns)
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))
    break_even = 100 * avg_loss / (avg_loss + avg_win)
    mean_return = sum(returns) / len(returns)
    checks = {
        'win_rate_pct': close(win_rate, report['win_rate_pct']),
        'break_even_win_rate_pct': close(break_even, report['break_even_win_rate_pct']),
        'net_expectancy_pct': close(mean_return, report['net_expectancy_pct']),
    }
    print(json.dumps({'n':len(returns),'recalculated':{'win_rate_pct':win_rate,
        'break_even_win_rate_pct':break_even,'net_expectancy_pct':mean_return},
        'matches_report':checks}, indent=2))
    return 0 if all(checks.values()) else 1

if __name__ == '__main__':
    raise SystemExit(main())
