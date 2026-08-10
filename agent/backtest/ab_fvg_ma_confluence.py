"""
Hipotesis nueva (pedido del usuario, 2026-08-01): FVG-15m tiene ganancias
grandes por trade (avg win $13.25) pero WR bajo (13.9%) porque entra en
CUALQUIER gap de liquidez sin filtrar el contexto de tendencia. MA Slope
Caso 3 tiene WR alto (64.3%) pero gana poco por trade porque su TP es
chico. Se prueba si exigir la geometria de medias de Caso 3 (MA7>25>50>99
con giro bajista de pendiente -- su condicion real, short-only) COMO
FILTRO ADICIONAL sobre los candidatos de FVG mejora el resultado de FVG
(mismo TP grande, pero solo entrando cuando ademas hay una estructura de
tendencia que se esta revirtiendo, no un gap cualquiera).

No es bolt-on de datos externos (como el A/B de OFI/funding/liquidaciones,
que no aporto nada) -- es combinar dos patrones de PRECIO que el usuario ya
demostro que tienen edge cada uno por su lado.

Uso: python -m backtest.ab_fvg_ma_confluence   (desde agent/)
"""
import sys
import os
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.getLogger().setLevel(logging.ERROR)

from datetime import datetime, timezone
from backtest.engine import BacktestEngine

FVG_PROFILE = {
    "id": "fvg-15m-original",
    "name": "FVG - 15m",
    "strategyType": "FVG",
    "allowLong": True,
    "allowShort": True,
    "tpMultiplier": 3,
    "slMultiplier": 0.8,
    "minRR": 1.5,
    "marginPerTrade": 150,
    "maxOpenPositions": 3,
    "maxTradeDurationCandles": 16,
    "minConfluenceScore": 50,
    "minNexusConfidence": 0,
    "patternParamsJson": json.dumps({"timeframe": "15m", "requireExhaustion": False, "minExhaustionSlopeDeg": 3}),
}

# Geometria real de MA Slope Caso 3 (short-only: ma7>25>50>99, giro bajista
# de pendiente) -- se usa SOLO como filtro de confirmacion, no para abrir
# posicion propia.
CASO3_GEOMETRY_PARAMS = {
    "order": {"ma7VsMa25": "greater", "ma7VsMa50": "greater", "ma7VsMa99": "greater"},
    "slope": {"targetMa": "ma7", "windowCandles": 3, "currentOp": "lte", "currentDeg": -0.2,
              "priorOp": "gte", "priorDeg": 0.2},
}
CASO3_GEOMETRY_PROFILE = {"patternParamsJson": json.dumps(CASO3_GEOMETRY_PARAMS)}

START_MS = int(datetime(2026, 7, 17, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)


def summarize(result: dict) -> dict:
    trades = result.get("trades", [])
    n = len(trades)
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    avg_win = (gross_win / len(wins)) if wins else 0.0
    avg_loss = (-gross_loss / len(losses)) if losses else 0.0
    return {
        "trades": n,
        "win_rate_pct": round(100 * len(wins) / n, 1) if n else 0.0,
        "pnl_total": round(result.get("total_pnl_usdt", 0), 2),
        "profit_factor": round(pf, 3) if pf != float("inf") else float("inf"),
        "total_signals": result.get("total_signals", 0),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }


def main():
    engine = BacktestEngine()
    symbols = engine.available_symbols()
    print(f"Simbolos: {len(symbols)} | ventana {datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} -> {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}", flush=True)

    # ── Baseline: FVG-15m tal cual (ambos lados, sin filtro geometrico) ──
    print("Corriendo: FVG-15m baseline (sin filtro geometrico)...", flush=True)
    result_baseline = engine.run_fvg(FVG_PROFILE, symbols, START_MS, END_MS)
    s0 = summarize(result_baseline)
    print(f"  -> trades={s0['trades']} (de {s0['total_signals']}) | WR={s0['win_rate_pct']}% | "
          f"PnL=${s0['pnl_total']} | PF={s0['profit_factor']} | avg_win=${s0['avg_win']} avg_loss=${s0['avg_loss']}", flush=True)

    # ── Confluence: FVG + geometria de Caso 3 (filtro adicional, solo bearish/SHORT) ──
    print("Corriendo: FVG-15m + confirmacion geometrica Caso 3 (SHORT-only)...", flush=True)

    original_candidate_fn_builder = engine.run_fvg
    # Reimplementamos el candidate_fn combinado directamente via _run_generic
    # (mismo patron interno que run_fvg, agregando el chequeo de geometria).
    interval = "15m"
    allow_long = FVG_PROFILE.get("allowLong", True)
    allow_short = FVG_PROFILE.get("allowShort", True)

    def combined_candidate_fn(symbol):
        try:
            item, _reason = engine.fvg_analyzer._scan_symbol(symbol, interval, sort_by="range")
        except Exception:
            return None
        if not item:
            return None
        if item.direction == "bullish" and not allow_long:
            return None
        if item.direction == "bearish" and not allow_short:
            return None
        # Filtro nuevo: la geometria de Caso 3 es un patron SHORT (giro
        # bajista tras tendencia alcista) -- solo aplica como confirmacion
        # cuando el gap de FVG tambien es bearish. Un FVG bullish no tiene
        # equivalente geometrico probado (Caso 3 no opera Long), asi que
        # pasa sin este filtro adicional.
        if item.direction == "bearish":
            geo = engine.ma_agent._read_ma_geometry(symbol, interval="1h")
            if not geo:
                return None
            confirmed = engine.ma_agent._evaluate_ma_geometry_profile(CASO3_GEOMETRY_PROFILE, geo)
            if not confirmed:
                return None
        item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        return engine.fvg_agent._build_fvg_candidate(item_dict, FVG_PROFILE)

    result_confluence = engine._run_generic(FVG_PROFILE, symbols, START_MS, END_MS, interval, combined_candidate_fn)
    s1 = summarize(result_confluence)
    print(f"  -> trades={s1['trades']} (de {s1['total_signals']}) | WR={s1['win_rate_pct']}% | "
          f"PnL=${s1['pnl_total']} | PF={s1['profit_factor']} | avg_win=${s1['avg_win']} avg_loss=${s1['avg_loss']}", flush=True)

    print("=" * 100)
    print(f"{'Escenario':40s} | {'señales':>8s} | {'trades':>7s} | {'WR%':>6s} | {'PnL':>10s} | {'PF':>6s}")
    print(f"{'FVG-15m baseline':40s} | {s0['total_signals']:8d} | {s0['trades']:7d} | {s0['win_rate_pct']:6.1f} | {s0['pnl_total']:10.2f} | {s0['profit_factor']:6.3f}")
    print(f"{'FVG-15m + geometria Caso 3':40s} | {s1['total_signals']:8d} | {s1['trades']:7d} | {s1['win_rate_pct']:6.1f} | {s1['pnl_total']:10.2f} | {s1['profit_factor']:6.3f}")
    print("=" * 100)
    delta_pnl = s1["pnl_total"] - s0["pnl_total"]
    veredicto = "MEJORA" if (s1["profit_factor"] > s0["profit_factor"] and s1["pnl_total"] >= s0["pnl_total"]) else "no mejora"
    print(f"delta PnL=${delta_pnl:+.2f} | PF {s0['profit_factor']} -> {s1['profit_factor']} -> {veredicto}")


if __name__ == "__main__":
    main()
