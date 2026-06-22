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

        # v12.0-BERSERKER: Balance ignorado. Siempre $150 fijo.
        logger.info(f"[BERSERKER v12.0] {symbol}: Bala fija $150 USDT. Sin chequeo de saldo.")

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

        # ── v10.3 Fixed Bullet: Margen fijo de 150 USDT para TODOS los trades LSE ──
        # Eliminamos el cálculo de qty basado en risk_usd / stop_distance
        # Ahora usamos siempre el margen configurado ($150 USDT)
        
        if profile:
            margin = float(profile.get("marginPerTrade", 150))
        else:
            margin = float(getattr(config, "MAX_MARGIN_PER_TRADE_USD", 150))
        
        lev = int(getattr(config, "DEFAULT_LEVERAGE", 1))
        notional = margin * lev
        qty = notional / cp
        
        # Calcular SL porcentual para logs
        sl_pct = (stop_distance / cp) * 100 if cp > 0 else 0
        
        logger.warning(
            f"[FIXED-MARGIN] {symbol} (LSE): Entrando con bala fija de ${margin:.2f} USDT | SL={sl_pct:.2f}% | qty={qty:.4f}"
        )

        # v12.0-BERSERKER: PURGE eliminado. Bala fija $150 sin chequeo de saldo.
        # margin ya es 150 fijo, no se cap contra balance.
        
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
                "fixed_margin": round(margin, 4),
                "stop_distance": round(stop_distance, 8),
                "qty": round(qty, 8),
                "notional": round(notional, 2),
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

        # Inicializar siempre — Golden U-Turn saltea el bloque estándar de ATR/rango
        atr_signal = signal_data.get("atr_signal")
        est_range = signal_data.get("estimated_range_pct")
        atr_f = float(atr_signal) if atr_signal else 0.0
        est_range_f = float(est_range) if est_range else 0.0
        min_sl_pct = float(getattr(config, "MIN_STOP_PCT_OF_PRICE", 0.002))
        sl_distance_pct = min_sl_pct
        sl_distance_price = cp * sl_distance_pct

        if atr_f <= 0 and signal_data.get("golden_uturn_mode"):
            gu_ctx = (signal_data.get("agent_audit_context") or {}).get("golden_uturn") or {}
            gu_atr_pct = gu_ctx.get("atr_volatility_pct")
            if gu_atr_pct:
                atr_f = cp * float(gu_atr_pct) / 100.0
                atr_signal = atr_f

        # ── HYBRID SNIPER / GOLDEN U-TURN: Custom SL Calibration ─────────────────
        # Golden U-Turn: SL = low de las últimas 20 velas (piso estructural)
        structural_sniper_mode = signal_data.get("structural_sniper_mode", False)
        golden_uturn_mode = signal_data.get("golden_uturn_mode", False)
        custom_sl_price = signal_data.get("custom_sl_price")
        
        if (structural_sniper_mode or golden_uturn_mode) and custom_sl_price:
            try:
                custom_sl_f = float(custom_sl_price)
                if custom_sl_f > 0 and custom_sl_f < cp:  # Solo LONGs
                    sl_price = custom_sl_f
                    sl_distance_price = cp - sl_price
                    sl_distance_pct = sl_distance_price / cp

                    # v9.6 Big Fish: Golden U-Turn exige SL mínimo 3% bajo entrada
                    if golden_uturn_mode:
                        min_sl_pct = float(getattr(config, "GOLDEN_UTURN_SL_MIN_DISTANCE_PCT", 3.0)) / 100.0
                        min_sl_dist = cp * min_sl_pct
                        if sl_distance_price < min_sl_dist:
                            sl_distance_price = min_sl_dist
                            sl_price = cp - sl_distance_price
                            sl_distance_pct = min_sl_pct
                            custom_sl_f = sl_price
                            min_tp_pct = float(getattr(config, "GOLDEN_UTURN_TP_MIN_DISTANCE_PCT", 10.0))
                            logger.warning(
                                f"[BIG-FISH-RISK] {symbol}: SL estirado a {min_sl_pct*100:.1f}% "
                                f"(mínimo estructural) para buscar TP del {min_tp_pct:.1f}%"
                            )
                        else:
                            logger.info(
                                f"[BIG-FISH-RISK] {symbol}: SL estructural={sl_distance_pct*100:.2f}% "
                                f"(low-20 o 3% mín)"
                            )

                    tag = "GOLDEN-U-TURN" if golden_uturn_mode else "STRUCTURAL-SNIPER"
                    if not golden_uturn_mode:
                        logger.info(
                            f"[{tag}-RISK] {symbol}: Usando custom SL={custom_sl_f:.6f} "
                            f"(distancia={sl_distance_pct:.4f}%)"
                        )
                else:
                    logger.warning(
                        f"[STRUCTURAL-SNIPER-RISK] {symbol}: Custom SL inválido ({custom_sl_f}), "
                        f"usando cálculo estándar"
                    )
                    custom_sl_price = None  # Fallback a cálculo estándar
            except (TypeError, ValueError):
                logger.warning(
                    f"[STRUCTURAL-SNIPER-RISK] {symbol}: Error al parsear custom SL, "
                    f"usando cálculo estándar"
                )
                custom_sl_price = None

        # 1. Distancia SL basada en volatilidad (atr o estimated_range)
        # Solo calcular si no hay custom SL de Sniper Mode
        if not ((structural_sniper_mode or golden_uturn_mode) and custom_sl_price):
            if profile:
                sl_mult = float(profile.get("slMultiplier", 0.8))
            else:
                sl_mult = float(getattr(config, "SL_MULTIPLIER", 0.8))

            if atr_f > 0 and (atr_f / cp) <= 0.20:
                sl_distance_price = atr_f * sl_mult
                sl_distance_pct = sl_distance_price / cp
            elif est_range_f > 0:
                sl_distance_pct = (est_range_f / 100.0) * sl_mult
            else:
                sl_distance_pct = 0.015 * sl_mult

            if sl_distance_pct < min_sl_pct:
                sl_distance_pct = min_sl_pct

            sl_distance_price = cp * sl_distance_pct

        # Calcular base SL sin el multiplicador de Clone para el Take Profit
        # Para Sniper/Golden con custom SL, usar el mismo sl_distance_price calculado
        if (structural_sniper_mode or golden_uturn_mode) and custom_sl_price:
            base_sl_distance_price = sl_distance_price
        else:
            if profile and profile.get("name") == "Scalping Clone":
                base_sl_mult = float(getattr(config, "SL_MULTIPLIER", 0.6))
            elif profile:
                base_sl_mult = float(profile.get("slMultiplier", 0.6))
            else:
                base_sl_mult = float(getattr(config, "SL_MULTIPLIER", 0.6))

            if atr_f > 0 and (atr_f / cp) <= 0.20:
                base_sl_distance_pct = (atr_f * base_sl_mult) / cp
            elif est_range_f > 0:
                base_sl_distance_pct = (est_range_f / 100.0) * base_sl_mult
            else:
                base_sl_distance_pct = 0.015 * base_sl_mult

            if base_sl_distance_pct < min_sl_pct:
                base_sl_distance_pct = min_sl_pct

            base_sl_distance_price = cp * base_sl_distance_pct

        # Limitar RR según setup_type (Golden U-Turn v9.6 ignora caps de perfil)
        if golden_uturn_mode:
            rr_target = float(getattr(config, "GOLDEN_UTURN_TP_MULTIPLIER", getattr(config, "TP_MULTIPLIER", 3.5)))
            setup_type = "Golden U-Turn Big Fish"
        else:
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

        logger.info(
            "[RISK] setup_type=%s | rr_effective=%.2f",
            setup_type, rr_target,
        )

        base_tp_distance_price = base_sl_distance_price * rr_target

        if profile and profile.get("name") == "Scalping Clone" and not golden_uturn_mode:
            boost = float(getattr(config, "CLONE_TP_BOOST", 1.3))
            tp_distance_price = base_tp_distance_price * boost
            logger.info(
                "[CLONE-TP] Decoupled Clone TP. standard_tp_dist=%.6f | clone_boost=%.2f | effective_tp_dist=%.6f",
                base_tp_distance_price, boost, tp_distance_price
            )
        else:
            tp_distance_price = sl_distance_price * rr_target

        # v9.6 Big Fish: TP mínimo 10% para Golden U-Turn
        if golden_uturn_mode:
            min_tp_pct = float(getattr(config, "GOLDEN_UTURN_TP_MIN_DISTANCE_PCT", 10.0)) / 100.0
            min_tp_distance = cp * min_tp_pct
            tp_from_rr = tp_distance_price
            if tp_distance_price < min_tp_distance:
                tp_distance_price = min_tp_distance
                logger.warning(
                    f"[BIG-FISH-RISK] {symbol}: TP forzado al {min_tp_pct*100:.1f}% "
                    f"(3.5x daba {tp_from_rr/cp*100:.2f}%)"
                )
            else:
                logger.info(
                    f"[BIG-FISH-RISK] {symbol}: TP={tp_distance_price/cp*100:.2f}% "
                    f"(RR {rr_target:.1f}x sobre SL {sl_distance_pct*100:.2f}%)"
                )

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

        # ── v10.3 Fixed Bullet: Margen fijo de 150 USDT para TODOS los trades ──
        # Eliminamos el cálculo de qty basado en risk_usd / stop_distance
        # Ahora usamos siempre el margen configurado ($150 USDT)
        
        if profile:
            margin = float(profile.get("marginPerTrade", 150))
        else:
            margin = float(getattr(config, "MAX_MARGIN_PER_TRADE_USD", 150))
        
        lev = int(getattr(config, "DEFAULT_LEVERAGE", 1))
        notional = margin * lev
        qty = notional / cp
        
        # Calcular SL y TP porcentuales para logs
        sl_pct = (sl_distance_price / cp) * 100 if cp > 0 else 0
        tp_pct = (tp_distance_price / cp) * 100 if cp > 0 else 0
        
        logger.warning(
            f"[FIXED-MARGIN] {symbol}: Entrando con bala fija de ${margin:.2f} USDT | SL={sl_pct:.2f}% | TP={tp_pct:.2f}% | qty={qty:.4f}"
        )

        # v12.0-BERSERKER: PURGE eliminado. Bala fija $150 sin chequeo de saldo.
        # margin ya es 150 fijo, no se cap contra balance.

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
        sl_pct = stop_distance / cp
        atr_ratio = sl_pct / atr_pct if atr_pct > 0 else 0

        logger.info(
            f"[RISK-FINAL] {symbol} | Margin: ${margin:.2f} | Qty: {qty:.4f} | SL: {sl_pct:.2f}% | TP: {tp_pct:.2f}%"
        )

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
                "fixed_margin": round(margin, 4),
                "stop_distance": round(stop_distance, 8),
                "qty_est": round(qty, 8),
                "notional_est": round(notional, 2),
            },
        }
