"""
LSE Backtest Engine — Valida el LiquiditySweepEngine sobre datos históricos.

Flujo:
  1. Descarga velas históricas desde Binance (REST público, sin auth)
  2. Corre el detector LSE sobre ventanas deslizantes
  3. Simula resultado (TP1/TP2/SL) sobre velas posteriores
  4. Reporta métricas: winrate, expectancy, PF, max DD, avg R, trades/semana

Uso:
  python -m lse.backtest --symbol PEPEUSDT --tf 1h --limit 1000
  python -m lse.backtest --symbol BTCUSDT --tf 1h --limit 500
"""
import argparse
import logging
import sys
import json
import math
import time
import urllib.request
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from .models import CandleInput, LSEEntryMode, LSEDetectionMode
from .detector import run_lse_detection
from .config import get_config
from .state_machine import LSEStateMachine

logger = logging.getLogger("LSE_BACKTEST")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# Binance REST (sin autenticación — datos públicos)
# ---------------------------------------------------------------------------
TF_MAP_BINANCE = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}

# Muchos tokens low-cap en Binance Futures usan prefijo "1000"
# Ej: PEPEUSDT → 1000PEPEUSDT, SHIBUSDT → 1000SHIBUSDT
_BINANCE_FUTURES_1000_TOKENS = {
    "PEPEUSDT", "SHIBUSDT", "BONKUSDT", "FLOKIUSDT",
    "XECUSDT", "LUNCUSDT", "BTTCUSDT",
}


def _resolve_binance_symbol(symbol: str, interval: str) -> str:
    """
    Determina el símbolo correcto en Binance Futures.
    Prueba el símbolo original primero; si falla con 400, intenta con prefijo 1000.
    Retorna el símbolo funcional o el original si ambos fallan.
    """
    upper = symbol.upper()
    candidates = [upper]

    # Si está en lista de tokens 1000 o si el precio es muy bajo (heurística por nombre)
    if upper in _BINANCE_FUTURES_1000_TOKENS or (
        not upper.startswith("1000") and any(
            upper.startswith(t) for t in ["PEPE", "SHIB", "BONK", "FLOKI", "XEC", "LUNC", "BTTC"]
        )
    ):
        candidates.insert(0, f"1000{upper}")  # intentar con 1000 primero

    base_url = "https://fapi.binance.com/fapi/v1/klines"
    for sym in candidates:
        test_url = f"{base_url}?symbol={sym}&interval={interval}&limit=1"
        try:
            with urllib.request.urlopen(test_url, timeout=8) as resp:
                if resp.status == 200:
                    logger.info("✅ Símbolo resuelto: %s → %s", symbol, sym)
                    return sym
        except Exception:
            continue

    logger.warning("⚠️ No se pudo resolver símbolo %s en Binance Futures — usando original", symbol)
    return upper


def fetch_binance_klines(symbol: str, interval: str, limit: int = 1000) -> List[CandleInput]:
    """
    Descarga velas históricas desde Binance Futures (klines sin auth).
    Auto-resuelve símbolos con prefijo 1000 (PEPEUSDT → 1000PEPEUSDT).
    limit máx por request: 1500. Para más, itera con startTime.
    """
    resolved = _resolve_binance_symbol(symbol, interval)
    all_candles: List[CandleInput] = []
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    batch_size = min(limit, 1500)
    fetched = 0
    end_time = None

    while fetched < limit:
        to_fetch = min(batch_size, limit - fetched)
        url = f"{base_url}?symbol={resolved}&interval={interval}&limit={to_fetch}"
        if end_time:
            url += f"&endTime={end_time}"

        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            logger.error("Error descargando klines %s (%s): %s", symbol, resolved, e)
            break

        if not data:
            break

        for row in data:
            all_candles.append(CandleInput(
                timestamp=str(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            ))

        fetched += len(data)
        end_time = int(data[0][0]) - 1

        if len(data) < to_fetch:
            break
        time.sleep(0.2)

    all_candles.sort(key=lambda c: int(c.timestamp))
    logger.info("✅ %d velas descargadas para %s [%s]", len(all_candles), resolved, interval)
    return all_candles


def fetch_htf_candles(symbol: str, limit: int = 200) -> List[CandleInput]:
    return fetch_binance_klines(symbol, "4h", limit=limit)


# ---------------------------------------------------------------------------
# Simulación de resultado
# ---------------------------------------------------------------------------

def simulate_trade_outcome(
    future_candles: List[CandleInput],
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: float,
    max_candles: int = 30,
) -> Dict:
    """
    Simula qué ocurre con el trade en las próximas `max_candles` velas.
    Retorna outcome dict con: resultado, exit_price, r_multiple, pnl_pct, candles_held
    """
    risk = entry_price - stop_loss
    if risk <= 0:
        return {"result": "INVALID", "exit_price": entry_price, "r_multiple": 0.0, "pnl_pct": 0.0, "candles_held": 0}

    # Follow-through check: si en las primeras 2-3 velas no hay impulso → salida anticipada
    NO_FOLLOWTHROUGH_CANDLES = 3
    no_follow = True
    for i, c in enumerate(future_candles[:NO_FOLLOWTHROUGH_CANDLES]):
        if c.close > entry_price * 1.005:  # al menos +0.5% de impulso
            no_follow = False
            break

    if no_follow:
        # Salida anticipada sin follow-through (precio de entrada)
        return {
            "result": "NO_FOLLOW",
            "exit_price": entry_price,
            "r_multiple": 0.0,
            "pnl_pct": 0.0,
            "candles_held": NO_FOLLOWTHROUGH_CANDLES,
        }

    # Simular vela a vela
    for i, candle in enumerate(future_candles[:max_candles]):
        # SL alcanzado (low toca SL)
        if candle.low <= stop_loss:
            pnl_pct = (stop_loss - entry_price) / entry_price * 100
            return {
                "result": "SL",
                "exit_price": stop_loss,
                "r_multiple": -1.0,
                "pnl_pct": round(pnl_pct, 3),
                "candles_held": i + 1,
            }
        # TP1 alcanzado (high toca TP1)
        if candle.high >= take_profit_1:
            pnl_pct = (take_profit_1 - entry_price) / entry_price * 100
            r = (take_profit_1 - entry_price) / risk
            # Parcial: cerrar 50%, mover SL a breakeven, buscar TP2
            # Para el backtest contamos TP1 como win completo
            return {
                "result": "TP1",
                "exit_price": take_profit_1,
                "r_multiple": round(r, 2),
                "pnl_pct": round(pnl_pct, 3),
                "candles_held": i + 1,
            }

    # Timeout: cerrar al último precio
    last_close = future_candles[min(max_candles - 1, len(future_candles) - 1)].close
    pnl_pct = (last_close - entry_price) / entry_price * 100
    r = (last_close - entry_price) / risk
    return {
        "result": "TIMEOUT",
        "exit_price": last_close,
        "r_multiple": round(r, 2),
        "pnl_pct": round(pnl_pct, 3),
        "candles_held": max_candles,
    }


# ---------------------------------------------------------------------------
# Motor de backtest
# ---------------------------------------------------------------------------

def run_backtest(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 1000,
    entry_mode: LSEEntryMode = LSEEntryMode.conservative,
    detection_mode: LSEDetectionMode = LSEDetectionMode.conservative,
    min_window: int = 150,
) -> Dict:
    """
    Corre el backtest deslizante sobre datos históricos.

    Args:
        symbol:     Par de trading (ej. "PEPEUSDT")
        timeframe:  Timeframe de análisis ("1h" recomendado)
        limit:      Cantidad de velas históricas a descargar
        entry_mode: Entrada agresiva (cierre reclaim) vs conservadora (ruptura high)
        detection_mode: conservative (equal lows + score sum) vs aggressive (min low + weighted score)
        min_window: Mínimo de velas históricas antes de empezar a detectar

    Returns:
        Dict con métricas completas y lista de trades
    """
    logger.info("🔍 Iniciando backtest: %s [%s] — %d velas", symbol, timeframe, limit)

    # Reset de state machine para backtest limpio
    LSEStateMachine._instance = None

    # Descarga de datos
    candles_1h = fetch_binance_klines(symbol, timeframe, limit=limit)
    candles_4h = fetch_htf_candles(symbol, limit=200)

    if len(candles_1h) < min_window + 50:
        logger.error("❌ Datos insuficientes para backtest: %d velas", len(candles_1h))
        return {"error": "insufficient_data", "symbol": symbol}

    trades = []
    signals_found = 0
    i = min_window

    while i < len(candles_1h) - 10:
        window_1h = candles_1h[:i]

        # Reset state machine para cada ventana (backtest puro — sin estado carryover)
        LSEStateMachine._instance = None

        signal, _diag = run_lse_detection(
            symbol=symbol,
            timeframe=timeframe,
            candles_1h=window_1h,
            candles_4h=candles_4h,
            entry_mode=entry_mode,
            detection_mode=detection_mode,
            preview_only=False,
        )

        if signal is None or signal.entry_price is None:
            i += 1
            continue

        signals_found += 1
        logger.info(
            "📍 Señal #%d en vela %d/%d | entry=%.6f | score=%.1f",
            signals_found, i, len(candles_1h), signal.entry_price, signal.score
        )

        # Futuro disponible para simulación
        future = candles_1h[i:]

        outcome = simulate_trade_outcome(
            future_candles=future,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2 or signal.take_profit_1 * 1.5,
        )

        trade_record = {
            "signal_index": i,
            "timestamp": candles_1h[i - 1].timestamp,
            "symbol": symbol,
            "score": signal.score,
            "sub_scores": {
                "compression": signal.sub_scores.compression,
                "sweep":       signal.sub_scores.sweep,
                "reclaim":     signal.sub_scores.reclaim,
                "volume":      signal.sub_scores.volume,
                "htf_context": signal.sub_scores.htf_context,
            },
            "entry_price":   signal.entry_price,
            "stop_loss":     signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            **outcome,
        }
        trades.append(trade_record)

        # Avanzar al menos N velas para evitar señales superpuestas
        cfg = get_config(symbol)
        i += cfg.cooldown_candles + 1

    # ── Métricas ──────────────────────────────────────────────────────────
    metrics = _compute_metrics(trades, candles_1h, timeframe)
    metrics["symbol"]    = symbol
    metrics["timeframe"] = timeframe
    metrics["limit_used"] = len(candles_1h)
    metrics["entry_mode"] = entry_mode.value
    metrics["detection_mode"] = detection_mode.value
    metrics["trades"]    = trades

    _print_report(metrics)
    return metrics


def _compute_metrics(trades: List[Dict], all_candles: List[CandleInput], timeframe: str) -> Dict:
    if not trades:
        return {
            "total_signals": 0,
            "wins": 0, "losses": 0, "no_follow": 0, "timeouts": 0,
            "winrate": 0.0, "expectancy": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "avg_r_multiple": 0.0,
            "trades_per_week": 0.0,
        }

    wins       = [t for t in trades if t["result"] in ("TP1", "TP2")]
    losses     = [t for t in trades if t["result"] == "SL"]
    no_follow  = [t for t in trades if t["result"] == "NO_FOLLOW"]
    timeouts   = [t for t in trades if t["result"] == "TIMEOUT"]

    total = len(trades)
    n_wins = len(wins)
    n_loss = len(losses)

    winrate = n_wins / total * 100 if total > 0 else 0.0

    r_multiples = [t["r_multiple"] for t in trades]
    avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0

    gross_profit = sum(t["r_multiple"] for t in trades if t["r_multiple"] > 0)
    gross_loss   = abs(sum(t["r_multiple"] for t in trades if t["r_multiple"] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    expectancy = (winrate / 100 * (gross_profit / n_wins if n_wins else 0)
                  - (1 - winrate / 100) * (gross_loss / n_loss if n_loss else 0))

    # Max Drawdown en R
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cumulative += t["r_multiple"]
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Trades por semana
    candles_per_week = {"1h": 168, "15m": 672, "4h": 42, "1d": 7}.get(timeframe, 168)
    n_candles = len(all_candles)
    weeks = n_candles / candles_per_week if candles_per_week > 0 else 1
    trades_per_week = total / weeks if weeks > 0 else 0.0

    return {
        "total_signals": total,
        "wins":       n_wins,
        "losses":     n_loss,
        "no_follow":  len(no_follow),
        "timeouts":   len(timeouts),
        "winrate":    round(winrate, 2),
        "expectancy": round(expectancy, 4),
        "profit_factor": round(profit_factor, 3),
        "max_drawdown": round(max_dd, 3),
        "avg_r_multiple": round(avg_r, 3),
        "trades_per_week": round(trades_per_week, 2),
    }


def _print_report(m: Dict):
    logger.info("=" * 60)
    logger.info("📊 LSE BACKTEST REPORT — %s [%s]", m.get("symbol"), m.get("timeframe"))
    logger.info("=" * 60)
    logger.info("Total señales   : %d", m.get("total_signals", 0))
    logger.info("Wins (TP1/TP2)  : %d", m.get("wins", 0))
    logger.info("Losses (SL)     : %d", m.get("losses", 0))
    logger.info("No Follow-thru  : %d", m.get("no_follow", 0))
    logger.info("Timeouts        : %d", m.get("timeouts", 0))
    logger.info("Winrate         : %.2f%%", m.get("winrate", 0))
    logger.info("Expectancy      : %.4f R", m.get("expectancy", 0))
    logger.info("Profit Factor   : %.3f", m.get("profit_factor", 0))
    logger.info("Max Drawdown    : %.3f R", m.get("max_drawdown", 0))
    logger.info("Avg R Multiple  : %.3f", m.get("avg_r_multiple", 0))
    logger.info("Trades/semana   : %.2f", m.get("trades_per_week", 0))
    logger.info("Entry mode      : %s", m.get("entry_mode", "-"))
    logger.info("Detection mode  : %s", m.get("detection_mode", "-"))
    logger.info("=" * 60)


def run_backtest_compare(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 1000,
    entry_mode: LSEEntryMode = LSEEntryMode.conservative,
    min_window: int = 150,
) -> Dict[str, Dict]:
    """
    Mismo dataset y condiciones — reporta métricas separadas conservative vs aggressive.
    """
    logger.info("🔬 Comparativa LSE: conservative vs aggressive — %s [%s]", symbol, timeframe)

    LSEStateMachine._instance = None
    conservative = run_backtest(
        symbol, timeframe, limit,
        entry_mode=entry_mode,
        detection_mode=LSEDetectionMode.conservative,
        min_window=min_window,
    )

    LSEStateMachine._instance = None
    aggressive = run_backtest(
        symbol, timeframe, limit,
        entry_mode=entry_mode,
        detection_mode=LSEDetectionMode.aggressive,
        min_window=min_window,
    )

    logger.info("")
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║           LSE COMPARE — mismo dataset                     ║")
    logger.info("╠════════════════════════════════════════════════════════════╣")
    for label, m in [("CONSERVATIVE", conservative), ("AGGRESSIVE", aggressive)]:
        if m.get("error"):
            logger.info("║ %-12s │ ERROR: %s", label, m.get("error"))
            continue
        logger.info(
            "║ %-12s │ signals=%3d │ WR=%6.2f%% │ PF=%5.2f │ DD=%6.3f │ E=%+.4f",
            label,
            m.get("total_signals", 0),
            m.get("winrate", 0),
            m.get("profit_factor", 0) if m.get("profit_factor") != float("inf") else 999,
            m.get("max_drawdown", 0),
            m.get("expectancy", 0),
        )
    logger.info("╚════════════════════════════════════════════════════════════╝")

    return {"conservative": conservative, "aggressive": aggressive}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LSE Backtest Engine")
    parser.add_argument("--symbol",  default="PEPEUSDT", help="Par de trading")
    parser.add_argument("--tf",      default="1h",       help="Timeframe (1h recomendado)")
    parser.add_argument("--limit",   default=1000, type=int, help="Velas históricas a descargar")
    parser.add_argument(
        "--mode", default="conservative",
        choices=["aggressive", "conservative"],
        help="entry_mode (entrada)",
    )
    parser.add_argument(
        "--detection", default="conservative",
        choices=["conservative", "aggressive"],
        help="detection_mode del motor LSE",
    )
    parser.add_argument("--compare", action="store_true", help="Ejecutar backtest conservative vs aggressive")
    parser.add_argument("--out", default=None, help="Guardar resultado en JSON")
    args = parser.parse_args()

    entry_mode = LSEEntryMode.aggressive if args.mode == "aggressive" else LSEEntryMode.conservative
    detection_mode = (
        LSEDetectionMode.aggressive if args.detection == "aggressive" else LSEDetectionMode.conservative
    )

    if args.compare:
        result = run_backtest_compare(
            symbol=args.symbol,
            timeframe=args.tf,
            limit=args.limit,
            entry_mode=entry_mode,
        )
    else:
        result = run_backtest(
            symbol=args.symbol,
            timeframe=args.tf,
            limit=args.limit,
            entry_mode=entry_mode,
            detection_mode=detection_mode,
        )

    if args.out:
        if args.compare:
            summary = {
                "conservative": {k: v for k, v in result["conservative"].items() if k != "trades"},
                "aggressive": {k: v for k, v in result["aggressive"].items() if k != "trades"},
            }
        else:
            summary = {k: v for k, v in result.items() if k != "trades"}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info("✅ Reporte guardado en %s", args.out)
