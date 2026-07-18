import config
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("RiskManager")

# 2026-07-12: tope de seguridad UNIVERSAL sobre el TP final de CUALQUIER
# estrategia (no solo FVG/Arrow Peak, que ya tienen su propio TP estructural
# — ver más abajo, esas se saltean este tope porque ya pasaron por uno
# equivalente). El usuario verificó el mismo síntoma (TP inalcanzable,
# apunta a la punta de un impulso viejo y ya agotado) en varias estrategias
# más, no solo FVG. Mismo razonamiento que
# python-service/fvg/analyzer.py::_liquidity_target: compara el alcance de
# una ventana reciente (pata actual) contra el de una ventana de 3-4 días —
# si el TP ya calculado (por RR×SL o lo que sea) implica ir más lejos de lo
# proporcional, se recorta a la mitad del camino restante. Siempre se aplica
# además un haircut del 10% (nunca el 100% del nivel calculado). Solo puede
# achicar el TP, nunca agrandarlo — y si faltan datos, no toca nada.
STRUCTURAL_CAP_INTERVAL = "15m"
STRUCTURAL_CAP_LOOKBACK_BARS = 400   # ~4 días en 15m
RECENT_IMPULSE_LOOKBACK_BARS = 40
DISPROPORTION_RATIO = 1.5
FADING_IMPULSE_TARGET_RATIO = 0.5
TP_HAIRCUT_RATIO = 0.9


class RiskManager:
    """
    Tamaño de posición y niveles TP/SL.
    LSE: SL/TP2 estructurales + riesgo fijo en USD respecto a distancia al stop.
    Nexus/SCAR: mantiene rango estimado (estimated_range_pct) en el precio de mercado.
    """

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def _apply_structural_tp_cap(self, symbol: str, side: int, cp: float, tp_price: float) -> float:
        """
        Ver constantes arriba. Fail-open: si no hay datos suficientes o algo
        falla, devuelve tp_price sin tocar — nunca bloquea un trade por esto.
        """
        try:
            klines = self.fetcher.get_klines_for_nexus(
                symbol, interval=STRUCTURAL_CAP_INTERVAL, limit=STRUCTURAL_CAP_LOOKBACK_BARS
            )
        except Exception as e:
            logger.debug(f"[TP-CAP] {symbol}: no se pudo obtener klines ({e}), sin tope estructural")
            return tp_price

        if not klines or len(klines) < 60:
            return tp_price

        try:
            recent = klines[-RECENT_IMPULSE_LOOKBACK_BARS:]
            if side == 0:
                full_high = max(float(k["high"]) for k in klines)
                local_high = max(float(k["high"]) for k in recent)
                if full_high <= cp or local_high <= cp:
                    candidate = tp_price
                else:
                    local_reach = local_high - cp
                    full_reach = full_high - cp
                    if full_reach > local_reach * DISPROPORTION_RATIO:
                        candidate = cp + full_reach * FADING_IMPULSE_TARGET_RATIO
                    else:
                        candidate = tp_price
                candidate = cp + (candidate - cp) * TP_HAIRCUT_RATIO
                capped = min(tp_price, candidate) if candidate > cp else tp_price
            else:
                full_low = min(float(k["low"]) for k in klines)
                local_low = min(float(k["low"]) for k in recent)
                if full_low >= cp or local_low >= cp:
                    candidate = tp_price
                else:
                    local_reach = cp - local_low
                    full_reach = cp - full_low
                    if full_reach > local_reach * DISPROPORTION_RATIO:
                        candidate = cp - full_reach * FADING_IMPULSE_TARGET_RATIO
                    else:
                        candidate = tp_price
                candidate = cp - (cp - candidate) * TP_HAIRCUT_RATIO
                capped = max(tp_price, candidate) if candidate < cp else tp_price

            if capped != tp_price:
                logger.info(
                    f"[TP-CAP] {symbol}: TP recortado por tope estructural "
                    f"{tp_price:.6f} -> {capped:.6f} (lado={side})"
                )
            return capped
        except Exception as e:
            logger.warning(f"[TP-CAP] {symbol}: error aplicando tope estructural: {e}")
            return tp_price

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

        tp2_b = self._apply_structural_tp_cap(symbol, side, cp, tp2_b)

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

        # ── HYBRID SNIPER / GOLDEN U-TURN / ARROW PEAK / MA SLOPE: Custom SL ─────
        # Golden U-Turn: SL = low de las últimas 20 velas (piso estructural, LONG).
        # Arrow Peak: SL = techo del pico + buffer (resistencia estructural, SHORT).
        # MA Slope (Casos 1/2/3): SL = mínimo/máximo reciente + buffer, según lado.
        structural_sniper_mode = signal_data.get("structural_sniper_mode", False)
        golden_uturn_mode = signal_data.get("golden_uturn_mode", False)
        # arrow_peak_v2_mode (clon con TP graduado, openspec market-data-expansion
        # sección 7) reusa EXACTAMENTE la misma rama de riesgo que el original —
        # ambos ya traen su propio custom_sl_price/custom_tp_price calculado
        # correctamente en verge_agent.py, esta rama solo respeta lo que venga.
        arrow_peak_mode = signal_data.get("arrow_peak_mode", False) or signal_data.get("arrow_peak_v2_mode", False)
        ma_slope_mode = signal_data.get("ma_slope_mode", False)
        fvg_mode = signal_data.get("fvg_mode", False)
        custom_sl_price = signal_data.get("custom_sl_price")
        side_for_custom_sl = int(signal_data.get("side", 0))

        if (structural_sniper_mode or golden_uturn_mode or arrow_peak_mode or ma_slope_mode or fvg_mode) and custom_sl_price:
            try:
                custom_sl_f = float(custom_sl_price)
                # LONG: el SL custom debe quedar debajo del precio actual.
                # SHORT (Arrow Peak): el SL custom debe quedar arriba (techo del pico).
                is_valid_custom_sl = (
                    (side_for_custom_sl == 0 and custom_sl_f > 0 and custom_sl_f < cp) or
                    (side_for_custom_sl == 1 and custom_sl_f > cp)
                )
                if is_valid_custom_sl:
                    sl_distance_price = abs(cp - custom_sl_f)
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

                    tag = (
                        "GOLDEN-U-TURN" if golden_uturn_mode
                        else "ARROW-PEAK" if arrow_peak_mode
                        else "MA-SLOPE" if ma_slope_mode
                        else "FVG" if fvg_mode
                        else "STRUCTURAL-SNIPER"
                    )
                    if not golden_uturn_mode:
                        # sl_distance_pct es una fracción (0.78 == 78%, no 0.78%) —
                        # faltaba *100 acá, el log mostraba "0.7809%" para un SL
                        # que en realidad estaba a 78.09% (confirmado contra el
                        # log de [FIXED-MARGIN] unas líneas más abajo, que sí
                        # multiplica bien). Engañó el diagnóstico del caso LRCUSDT
                        # 2026-07-13/14 haciendo parecer sano un SL roto.
                        logger.info(
                            f"[{tag}-RISK] {symbol}: Usando custom SL={custom_sl_f:.6f} "
                            f"(distancia={sl_distance_pct*100:.4f}%)"
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
        if not ((structural_sniper_mode or golden_uturn_mode or arrow_peak_mode or ma_slope_mode or fvg_mode) and custom_sl_price):
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
        # Para Sniper/Golden/Arrow Peak/MA Slope/FVG con custom SL, usar el mismo sl_distance_price calculado
        if (structural_sniper_mode or golden_uturn_mode or arrow_peak_mode or ma_slope_mode or fvg_mode) and custom_sl_price:
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

        # [MA SLOPE] TP mínimo genérico — el propio candidato trae su piso
        # (min_tp_pct), distinto por caso, en vez de un bloque fijo por cada uno.
        if ma_slope_mode and signal_data.get("min_tp_pct"):
            ms_min_tp_pct = float(signal_data.get("min_tp_pct")) / 100.0
            ms_min_tp_distance = cp * ms_min_tp_pct
            if tp_distance_price < ms_min_tp_distance:
                logger.info(
                    f"[MA-SLOPE-RISK] {symbol}: TP estirado al mínimo {ms_min_tp_pct*100:.1f}% "
                    f"(RR daba {tp_distance_price/cp*100:.2f}%)"
                )
                tp_distance_price = ms_min_tp_distance

        # [ARROW PEAK] TP estructural: apunta al origen real de la flecha (open de
        # la primera vela del pump, con buffer para cerrar un poco ANTES de
        # completarla), no a un múltiplo RR de la distancia al SL — ese RR podía
        # dar objetivos irreales (60%+) cuando el pump previo fue grande, ya que
        # el SL de Arrow Peak es estructural (distancia al pico) y variable.
        if arrow_peak_mode:
            ap_custom_tp = signal_data.get("custom_tp_price")
            ap_custom_tp_f = None
            if ap_custom_tp:
                try:
                    ap_custom_tp_f = float(ap_custom_tp)
                except (TypeError, ValueError):
                    ap_custom_tp_f = None

            if ap_custom_tp_f and 0 < ap_custom_tp_f < cp:
                tp_distance_price = cp - ap_custom_tp_f
                logger.info(
                    f"[ARROW-PEAK-RISK] {symbol}: TP=origen de flecha "
                    f"({ap_custom_tp_f:.6f}, distancia={tp_distance_price/cp*100:.2f}%)"
                )
            else:
                ap_min_tp_pct = float(getattr(config, "ARROW_PEAK_TP_MIN_DISTANCE_PCT", 10.0)) / 100.0
                ap_min_tp_distance = cp * ap_min_tp_pct
                if tp_distance_price < ap_min_tp_distance:
                    logger.info(
                        f"[ARROW-PEAK-RISK] {symbol}: TP estirado al mínimo {ap_min_tp_pct*100:.1f}% "
                        f"(RR daba {tp_distance_price/cp*100:.2f}%, sin origen de flecha válido)"
                    )
                    tp_distance_price = ap_min_tp_distance

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

        # [FVG] TP estructural: usa el liquidity target ya calculado en
        # python-service (swing real de la ventana reciente, con recorte a la
        # mitad cuando el máximo/mínimo de la ventana completa pertenece a un
        # impulso anterior desproporcionadamente más grande, más un haircut
        # final) como objetivo directo — no un múltiplo RR de un SL que en
        # FVG suele ser chico (el piso `min_tp_pct` solo podía ESTIRAR el TP,
        # nunca acotarlo, así que un RR grande igual mandaba a un objetivo
        # irreal aunque python-service ya calculara uno razonable). Ver casos
        # reales BEATUSDT/VELVETUSDT 2026-07-12.
        if fvg_mode:
            fvg_side = int(signal_data.get("side", 0))
            fvg_custom_tp = signal_data.get("custom_tp_price")
            fvg_custom_tp_f = None
            if fvg_custom_tp:
                try:
                    fvg_custom_tp_f = float(fvg_custom_tp)
                except (TypeError, ValueError):
                    fvg_custom_tp_f = None

            is_valid_fvg_tp = fvg_custom_tp_f is not None and (
                (fvg_side == 0 and fvg_custom_tp_f > cp) or
                (fvg_side == 1 and 0 < fvg_custom_tp_f < cp)
            )
            if is_valid_fvg_tp:
                tp_distance_price = abs(fvg_custom_tp_f - cp)
                logger.info(
                    f"[FVG-RISK] {symbol}: TP=liquidity target estructural "
                    f"({fvg_custom_tp_f:.6f}, distancia={tp_distance_price/cp*100:.2f}%)"
                )
            else:
                logger.warning(
                    f"[FVG-RISK] {symbol}: TP estructural inválido/ausente, "
                    f"usando fallback RR×SL ({tp_distance_price/cp*100:.2f}%)"
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

        # Tope estructural universal — FVG y Arrow Peak ya calculan su propio
        # TP estructural (con su propio haircut), aplicarlo de nuevo encima
        # solo los recortaría el doble sin necesidad.
        if not (fvg_mode or arrow_peak_mode):
            tp_price = self._apply_structural_tp_cap(symbol, side, cp, tp_price)
            tp_distance_price = abs(tp_price - cp)

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
