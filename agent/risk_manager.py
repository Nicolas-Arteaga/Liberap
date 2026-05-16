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
        profile: dict = None,
    ) -> Optional[Dict[str, Any]]:
        balance = available_balance if available_balance is not None else config.VIRTUAL_CAPITAL_BASE

        if signal_data.get("source") == "LSE":
            return self._calculate_position_lse(symbol, signal_data, balance, profile)

        return self._calculate_position_nexus_style(symbol, signal_data, balance, profile)

    def _calculate_position_lse(
        self,
        symbol: str,
        signal_data: dict,
        balance: float,
        profile: dict = None,
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

        if profile:
            cap_m = float(profile.get("marginPerTrade", 150))
        else:
            cap_m = float(getattr(config, "MAX_MARGIN_PER_TRADE_USD", 500))

        if margin > cap_m:
            scale = cap_m / margin
            margin = cap_m
            qty *= scale
            notional *= scale

        margin = min(margin, balance * 0.99)
        
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
        profile: dict = None,
    ) -> Optional[Dict[str, Any]]:
        current_price = self.fetcher.get_current_price(symbol)
        if current_price <= 0:
            logger.error("Cannot calculate position for %s, invalid entry price", symbol)
            return None

        cp = float(current_price)

        # 1. Distancia SL basada en volatilidad (atr o estimated_range)
        atr_signal = signal_data.get("atr_signal")
        est_range = signal_data.get("estimated_range_pct")

        if profile:
            sl_mult = float(profile.get("slMultiplier", 0.8))
        else:
            sl_mult = float(getattr(config, "SL_MULTIPLIER", 0.8))

        atr_f = float(atr_signal) if atr_signal else 0.0
        est_range_f = float(est_range) if est_range else 0.0

        if atr_f > 0 and (atr_f / cp) <= 0.20:
            sl_distance_price = atr_f * sl_mult
            sl_distance_pct = sl_distance_price / cp
        elif est_range_f > 0:
            sl_distance_pct = (est_range_f / 100.0) * sl_mult
        else:
            sl_distance_pct = 0.015 * sl_mult

        min_sl_pct = float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))
        if sl_distance_pct < min_sl_pct:
            sl_distance_pct = min_sl_pct

        sl_distance_price = cp * sl_distance_pct

        # Limitar RR según setup_type (caps hard por tipo de señal)
        if profile:
            rr_target = float(profile.get("tpMultiplier", 3.0))
        else:
            rr_target = float(getattr(config, "TP_MULTIPLIER", 2.0))
        nexus_conf = signal_data.get("nexus_confidence", 0)
        setup_type = "Momentum Burst" if nexus_conf > 80 else ("Trend Following" if nexus_conf > 60 else "Mean Reversion")

        tp_mult_tf_max = float(getattr(config, "TP_MULT_TREND_FOLLOWING_MAX", 2.5))
        tp_mult_mr_max = float(getattr(config, "TP_MULT_MEAN_REVERSION_MAX", 1.8))

        if setup_type == "Trend Following":
            rr_target = min(rr_target, tp_mult_tf_max)
        elif setup_type == "Mean Reversion":
            rr_target = min(rr_target, tp_mult_mr_max)
        # Momentum Burst: sin cap adicional (ya limitado por config.TP_MULTIPLIER)

        logger.info(
            "[RISK] setup_type=%s | rr_cap=%.2f | rr_effective=%.2f",
            setup_type,
            tp_mult_tf_max if setup_type == "Trend Following" else (tp_mult_mr_max if setup_type == "Mean Reversion" else rr_target),
            rr_target,
        )

        tp_distance_price = sl_distance_price * rr_target

        side = int(signal_data.get("side", 0))

        if side == 0:
            tp_price = cp + tp_distance_price
            sl_price = cp - sl_distance_price
            stop_distance = cp - sl_price
        else:
            tp_price = cp - tp_distance_price
            sl_price = cp + sl_distance_price
            stop_distance = sl_price - cp

        if stop_distance <= 0:
            logger.error("Nexus stop_distance invalid side=%s cp=%s sl=%s", side, cp, sl_price)
            return None

        # 3. Calcular risk_usd constante
        risk_usd = balance * float(getattr(config, "EQUITY_RISK_PCT_FOR_STOP", 0.01))
        
        # 4. Calcular qty final
        qty = risk_usd / stop_distance

        # 5. Aplicar caps
        lev = int(getattr(config, "DEFAULT_LEVERAGE", 1))
        notional = qty * cp
        margin = notional / max(lev, 1)

        if profile:
            cap_m = float(profile.get("marginPerTrade", 150))
        else:
            cap_m = float(getattr(config, "MAX_MARGIN_PER_TRADE_USD", 500))
        if margin > cap_m:
            scale = cap_m / margin
            margin = cap_m
            qty *= scale
            notional *= scale

        margin = min(margin, balance * 0.99)

        max_no = float(getattr(config, "MAX_NOTIONAL_PER_TRADE_USD", 50000))
        if notional > max_no:
            scale = max_no / notional
            margin *= scale
            qty *= scale
            notional = max_no

        # Metadata para logs
        atr_pct = (float(atr_signal) / cp) if (atr_signal and float(atr_signal) > 0) else 0
        range_pct = sl_distance_pct

        # Validación post-caps
        real_risk_usd = qty * stop_distance
        sl_pct = stop_distance / cp
        atr_ratio = sl_pct / atr_pct if atr_pct > 0 else 0

        logger.info(
            f"[RISK] ATR={atr_pct:.4f} | SL%={sl_pct:.4f} "
            f"| RR={rr_target:.2f} | Qty={qty:.4f} | RiskUSD={risk_usd:.2f}"
        )
        logger.info(f"[RISK_FINAL] Intended={risk_usd:.2f} | Real={real_risk_usd:.2f}")
        logger.info(f"[RISK_CHECK] SL/ATR ratio={atr_ratio:.2f}")

        # ── Validación hard: niveles inválidos → bloquear trade ──
        if sl_price <= 0:
            logger.error(
                "[RISK_ERROR] sl_price inválido (<=0) para %s | sl_price=%s entry=%s — trade bloqueado",
                symbol, sl_price, cp,
            )
            return None

        if side == 0 and tp_price > cp * 3:
            logger.error(
                "[RISK_ERROR] tp_price absurdo para LONG %s | tp=%s entry=%s (>300%%) — trade bloqueado",
                symbol, tp_price, cp,
            )
            return None

        if side == 1 and tp_price <= 0:
            logger.error(
                "[RISK_ERROR] tp_price inválido (<=0) para SHORT %s | tp=%s entry=%s — trade bloqueado",
                symbol, tp_price, cp,
            )
            return None

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
