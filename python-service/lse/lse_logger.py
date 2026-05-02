"""
LSE Structured Logger — Registra cada señal LSE con todos sus atributos.

Por cada señal, emite:
  - symbol, timeframe, score total y sub-scores
  - valores de MA, ATR, volumen
  - niveles: sweep_low, reclaim_close, entry, TP1, TP2, SL
  - reasoning list
  - resultado final (cuando se cierra: TP1/TP2/SL/manual)

Escribe a: logs/lse_signals.jsonl (JSON Lines — una línea por entrada)
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import LSESignal

logger = logging.getLogger("LSE_LOGGER")

# Ruta de salida: dentro del python-service para que docker lo monte fácil
_LOG_DIR  = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "lse_signals.jsonl"


def _ensure_log_dir():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_signal(signal: LSESignal, event: str = "SIGNAL_EMITTED") -> None:
    """
    Escribe la señal LSE en formato JSON Lines.

    Args:
        signal: LSESignal completo
        event:  Etiqueta del evento (SIGNAL_EMITTED | POSITION_CLOSED | TP1_HIT | SL_HIT)
    """
    _ensure_log_dir()

    record = {
        "ts":             datetime.now(timezone.utc).isoformat(),
        "event":          event,
        "symbol":         signal.symbol,
        "timeframe":      signal.timeframe,
        "state":          signal.state.value if signal.state else None,
        "score":          signal.score,
        "sub_scores": {
            "compression":  signal.sub_scores.compression,
            "sweep":        signal.sub_scores.sweep,
            "reclaim":      signal.sub_scores.reclaim,
            "volume":       signal.sub_scores.volume,
            "htf_context":  signal.sub_scores.htf_context,
        },
        "entry_price":    signal.entry_price,
        "stop_loss":      signal.stop_loss,
        "take_profit_1":  signal.take_profit_1,
        "take_profit_2":  signal.take_profit_2,
        "sweep_low":      signal.sweep_low,
        "reclaim_close":  signal.reclaim_close,
        "ma7":            signal.ma7,
        "ma25":           signal.ma25,
        "ma99":           signal.ma99,
        "atr":            signal.atr,
        "volume_ratio":   signal.volume_ratio,
        "compression_pct": signal.compression_pct,
        "entry_mode":     signal.entry_mode.value if signal.entry_mode else None,
        "detected_at":    signal.detected_at,
        "reasoning":      signal.reasoning,
    }

    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug("📝 LSE log escrito: %s %s score=%.1f", event, signal.symbol, signal.score)
    except Exception as e:
        logger.error("❌ Error escribiendo log LSE: %s", e)


def log_close(
    symbol: str,
    timeframe: str,
    exit_price: float,
    exit_reason: str,  # "TP1" | "TP2" | "SL" | "MANUAL" | "TIMEOUT"
    pnl_pct: Optional[float] = None,
    r_multiple: Optional[float] = None,
) -> None:
    """
    Registra el cierre de una posición LSE para cálculo de métricas.
    """
    _ensure_log_dir()

    record = {
        "ts":           datetime.now(timezone.utc).isoformat(),
        "event":        f"CLOSED_{exit_reason}",
        "symbol":       symbol,
        "timeframe":    timeframe,
        "exit_price":   exit_price,
        "exit_reason":  exit_reason,
        "pnl_pct":      pnl_pct,
        "r_multiple":   r_multiple,
    }

    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(
            "📊 LSE CLOSE: %s | Razón=%s | PnL=%.2f%% | R=%.2f",
            symbol, exit_reason,
            pnl_pct or 0.0,
            r_multiple or 0.0,
        )
    except Exception as e:
        logger.error("❌ Error escribiendo close LSE: %s", e)


def get_recent_signals(limit: int = 50) -> list:
    """Lee los últimos N registros del log JSONL."""
    if not _LOG_FILE.exists():
        return []
    try:
        lines = _LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
        records = [json.loads(l) for l in lines if l.strip()]
        return records[-limit:]
    except Exception as e:
        logger.error("❌ Error leyendo log LSE: %s", e)
        return []
