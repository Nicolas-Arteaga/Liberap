import config
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("RiskManager")


class RiskManager:
    """
    Tamaño de posición y niveles TP/SL.
    LSE: SL/TP2 estructurales + riesgo fijo en USD respecto a distancia al stop.
    Nexus/SCAR: mantiene rango estimado (estimated_range_pct) en el precio de mercado.
    """

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def calculate_position(
        self,
        symbol: str,
        signal_data: dict,
        available_balance: float = None,
    ) -> Optional[Dict[str, Any]]:
        balance = available_balance if available_balance is not None else config.VIRTUAL_CAPITAL_BASE

        if signal_data.get("source") == "LSE":
            return self._calculate_position_lse(symbol, signal_data, balance)

        return self._calculate_position_nexus_style(symbol, signal_data, balance)

    def _calculate_position_lse(
        self,
        symbol: str,
        signal_data: dict,
        balance: float,
    ) -> Optional[Dict[str, Any]]:
        entry_signal = signal_data.get("lse_entry_price")
        sl_s = signal_data.get("lse_stop_loss")
        tp2 = signal_data.get("lse_take_profit_2")
        side = int(signal_data.get("side", 0))

        current_price = self.fetcher.get_current_price(symbol)
        if current_price <= 0:
            logger.error("Cannot calculate LSE position for %s, invalid market price", symbol)
            return None

        try:
            entry_b = float(entry_signal)
            sl_b = float(sl_s)
            tp2_b = float(tp2)
            cp = float(current_price)
        except (TypeError, ValueError):
            logger.error("LSE structural levels invalid for %s", symbol)
            return None

        # Riesgo nominal al precio de ejecución (mismo reference que entry_price en monitor)
        if side == 0:
            stop_distance = cp - sl_b
        else:
            stop_distance = sl_b - cp
        if stop_distance <= 0:
            logger.error(
                "LSE stop_distance invalid (side=%s cp=%s sl=%s) for %s",
                side,
                cp,
                sl_b,
                symbol,
            )
            return None

        risk_usd = balance * float(getattr(config, "EQUITY_RISK_PCT_FOR_STOP", 0.01))
        qty = risk_usd / stop_distance

        lev = int(getattr(config, "DEFAULT_LEVERAGE", 1))
        notional = qty * cp
        margin = notional / max(lev, 1)

        cap_m = float(getattr(config, "MAX_MARGIN_PER_TRADE_USD", 500))
        margin = min(margin, cap_m, balance * 0.99)

        max_no = float(getattr(config, "MAX_NOTIONAL_PER_TRADE_USD", 50000))
        if notional > max_no:
            scale = max_no / notional
            margin *= scale
            qty *= scale
            notional = max_no

        tp_price = tp2_b
        sl_price = sl_b

        return {
            "symbol": symbol,
            "side": side,
            "margin": round(margin, 2),
            "leverage": lev,
            "entry_price": cp,
            "entry_signal_price": round(entry_b, 8),
            "tp_price": round(tp_price, 8),
            "sl_price": round(sl_price, 8),
            "range_pct_used": None,
            "lse_sizing": {
                "risk_usd": round(risk_usd, 4),
                "stop_distance": round(stop_distance, 8),
                "qty_est": round(qty, 8),
                "notional_est": round(notional, 2),
            },
        }

    def _calculate_position_nexus_style(
        self,
        symbol: str,
        signal_data: dict,
        balance: float,
    ) -> Optional[Dict[str, Any]]:
        cp = self.fetcher.get_current_price(symbol)
        if cp <= 0:
            logger.error(
                "Cannot calculate position for %s, invalid entry price: %s",
                symbol,
                cp,
            )
            return None

        range_pct = signal_data.get("estimated_range_pct", 2.0) / 100.0

        tp_distance = range_pct * config.TP_MULTIPLIER
        sl_distance = range_pct * config.SL_MULTIPLIER

        side = int(signal_data.get("side", 0))

        if side == 0:
            tp_price = cp * (1 + tp_distance)
            sl_price = cp * (1 - sl_distance)
            stop_distance = cp - sl_price
        else:
            tp_price = cp * (1 - tp_distance)
            sl_price = cp * (1 + sl_distance)
            stop_distance = sl_price - cp

        if stop_distance <= 0:
            logger.error("Nexus stop_distance invalid side=%s cp=%s sl=%s", side, cp, sl_price)
            return None

        risk_usd = balance * float(getattr(config, "EQUITY_RISK_PCT_FOR_STOP", 0.01))
        qty = risk_usd / stop_distance

        lev = int(getattr(config, "DEFAULT_LEVERAGE", 1))
        notional = qty * cp
        margin = notional / max(lev, 1)

        cap_m = float(getattr(config, "MAX_MARGIN_PER_TRADE_USD", 500))
        margin = min(margin, cap_m, balance * 0.99)

        max_no = float(getattr(config, "MAX_NOTIONAL_PER_TRADE_USD", 50000))
        if notional > max_no:
            scale = max_no / notional
            margin *= scale
            qty *= scale
            notional = max_no

        return {
            "symbol": symbol,
            "side": side,
            "margin": round(margin, 2),
            "leverage": lev,
            "entry_price": cp,
            "tp_price": round(tp_price, 8),
            "sl_price": round(sl_price, 8),
            "range_pct_used": round(range_pct * 100, 2),
            "nexus_sizing": {
                "risk_usd": round(risk_usd, 4),
                "stop_distance": round(stop_distance, 8),
                "qty_est": round(qty, 8),
                "notional_est": round(notional, 2),
            },
        }
