import time
import logging
import config

logger = logging.getLogger("BTCMacroFilter")


class BTCMacroFilter:
    """
    Detecta régimen de BTC y flash crashes.
    Base del sistema BTC Triple Layer Defense.
    """
    
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self._regime_cache = None
        self._regime_cache_time = 0
        self._flash_crash_cache = None
        self._flash_crash_cache_time = 0
        self._first_regime_call = True  # Flag para log de primera ejecución
        self._first_dump_pct_call = True  # Flag para log de primera ejecución
        self._bleeding_call_count = 0  # Contador de llamadas a is_btc_bleeding
        self._regime_call_count = 0  # Contador de llamadas a get_regime
        self._error_count = 0  # Contador de errores silenciosos
        
    def get_regime(self) -> str:
        """
        Determina el régimen actual de BTC.
        Retorna: "BULLISH" | "DUMPING" | "NEUTRAL"
        
        Usa 3 ventanas temporales (5m, 15m, 1h) para detectar tanto
        caídas bruscas como sangrados graduales que no se ven en ventanas cortas.
        """
        now = time.time()
        self._regime_call_count += 1
        
        # Return cached if fresh
        if self._regime_cache and (now - self._regime_cache_time) < config.BTC_REGIME_CACHE_SEC:
            return self._regime_cache
        
        try:
            # Obtener velas 1m, 5m y 15m de BTCUSDT con límite suficiente para cálculos
            candles_1m = self.fetcher.get_klines_for_nexus("BTCUSDT", "1m", limit=60)
            candles_5m = self.fetcher.get_klines_for_nexus("BTCUSDT", "5m", limit=50)
            candles_15m = self.fetcher.get_klines_for_nexus("BTCUSDT", "15m", limit=10)
            
            if not candles_1m or not candles_5m:
                self._error_count += 1
                logger.warning(
                    f"[BTC-FILTER] !!! NO se pudieron obtener velas BTC "
                    f"(1m={len(candles_1m) if candles_1m else 0}, 5m={len(candles_5m) if candles_5m else 0}) "
                    f"- retornando NEUTRAL (error #{self._error_count}, ESCUDO CIEGO)"
                )
                self._regime_cache = "NEUTRAL"
                self._regime_cache_time = now
                return "NEUTRAL"
            
            # Calcular % cambio 5m (usando velas 1m)
            current_price_1m = float(candles_1m[-1]["close"])  # Close actual
            # -6 es la vela que cerró hace 5 min exactos (index -1 es la vela actual en desarrollo)
            price_5m_ago = float(candles_1m[-6]["close"]) if len(candles_1m) >= 6 else float(candles_1m[0]["close"])
            pct_5m = ((current_price_1m - price_5m_ago) / price_5m_ago) * 100
            
            # Calcular % cambio 15m (usando velas 5m)
            current_price_5m = float(candles_5m[-1]["close"])  # Close actual
            # -4 es la vela que cerró hace 15 min exactos (3 velas de 5m atrás)
            price_15m_ago = float(candles_5m[-4]["close"]) if len(candles_5m) >= 4 else float(candles_5m[0]["close"])
            pct_15m = ((current_price_5m - price_15m_ago) / price_15m_ago) * 100
            
            # ── NUEVO: Calcular % cambio 1h (sangrado gradual) ──────────────
            # Una caída de 2-3% distribuida en horas NO se ve en ventanas de 5m/15m.
            # Este fue el bug que causó la pérdida de 20 USDT: BTC cayó de 73k a 71k
            # gradualmente y el filtro decía NEUTRAL porque ninguna ventana corta lo detectaba.
            pct_1h = 0.0
            if candles_15m and len(candles_15m) >= 5:
                current_price_15m = float(candles_15m[-1]["close"])
                price_1h_ago = float(candles_15m[-5]["close"])  # 4 velas de 15m = 1 hora
                pct_1h = ((current_price_15m - price_1h_ago) / price_1h_ago) * 100
            
            # Determinar régimen con las 3 ventanas
            btc_dump_1h_threshold = float(getattr(config, "BTC_DUMP_THRESHOLD_1H", -1.5))
            
            if pct_5m < config.BTC_DUMP_THRESHOLD_5M or pct_15m < config.BTC_DUMP_THRESHOLD_15M or pct_1h < btc_dump_1h_threshold:
                regime = "DUMPING"
                logger.info(f"[BTC-FILTER] Regimen DUMPING - pct_5m={pct_5m:.2f}% pct_15m={pct_15m:.2f}% pct_1h={pct_1h:.2f}%")
            elif pct_5m > config.BTC_PUMP_THRESHOLD_5M:
                regime = "BULLISH"
                logger.info(f"[BTC-FILTER] Regimen BULLISH - pct_5m={pct_5m:.2f}% pct_15m={pct_15m:.2f}% pct_1h={pct_1h:.2f}%")
            else:
                regime = "NEUTRAL"
                # ANTES era debug (invisible). AHORA es info para confirmar que el filtro esta VIVO
                logger.info(f"[BTC-FILTER] Regimen NEUTRAL - pct_5m={pct_5m:.2f}% pct_15m={pct_15m:.2f}% pct_1h={pct_1h:.2f}%")
            
            self._regime_cache = regime
            self._regime_cache_time = now
            
            # ── Log de primera ejecución: confirma que el código NUEVO está corriendo ──
            if self._first_regime_call:
                self._first_regime_call = False
                logger.info(
                    f"[BTC-FILTER] >>> PRIMERA EJECUCION — Codigo v5.0 ACTIVO <<< "
                    f"| Ventanas: 5m + 15m + 1h | pct_5m={pct_5m:.2f}% pct_15m={pct_15m:.2f}% pct_1h={pct_1h:.2f}% "
                    f"| Regimen={regime}"
                )
            
            return regime
            
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"[BTC-FILTER] !!! ERROR al obtener regimen BTC (error #{self._error_count}): {e} "
                f"- retornando NEUTRAL (PELIGRO: el escudo esta CIEGO)"
            )
            self._regime_cache = "NEUTRAL"
            self._regime_cache_time = now
            return "NEUTRAL"
    
    def get_dump_pct(self, window_minutes: int) -> float:
        """
        Retorna el cambio porcentual de BTC en la ventana indicada.
        Negativo = caída.
        
        IMPORTANTE: Se asegura de medir exactamente la ventana pedida,
        no más. Antes usaba limit grande y comparaba contra candles[0]
        lo cual medía una ventana mucho más amplia que la solicitada.
        """
        try:
            # Determinar timeframe apropiado y límite EXACTO para la ventana
            if window_minutes <= 5:
                tf = "1m"
                # Necesitamos window_minutes + 1 velas para medir window_minutes
                exact_candles = window_minutes + 1
                limit = max(10, exact_candles + 2)  # margen de seguridad
            elif window_minutes <= 15:
                tf = "5m"
                exact_candles = (window_minutes // 5) + 1
                limit = max(10, exact_candles + 2)
            elif window_minutes <= 60:
                tf = "15m"
                exact_candles = (window_minutes // 15) + 1  # Para 60m: 5 velas
                limit = max(10, exact_candles + 2)
            else:
                tf = "1h"
                exact_candles = (window_minutes // 60) + 1
                limit = max(10, exact_candles + 2)
            
            candles = self.fetcher.get_klines_for_nexus("BTCUSDT", tf, limit=limit)
            
            if not candles or len(candles) < 2:
                self._error_count += 1
                logger.warning(
                    f"[BTC-FILTER] !!! DATOS INSUFICIENTES para ventana {window_minutes}m "
                    f"(candles={len(candles) if candles else 0}, need>=2) "
                    f"- retornando 0.0 (error #{self._error_count})"
                )
                return 0.0
            
            current_price = float(candles[-1]["close"])  # Close actual
            
            # Usar la vela que corresponde exactamente a la ventana pedida
            # Para 60m con tf=15m: necesitamos la vela de hace 4 períodos = candles[-5]
            candles_back = exact_candles - 1  # Para 60m: 4 velas atrás
            if candles_back > 0 and len(candles) > candles_back:
                start_price = float(candles[-(candles_back + 1)]["close"])
            else:
                start_price = float(candles[0]["close"])
            
            pct_change = ((current_price - start_price) / start_price) * 100
            
            # ── Log de primera ejecución: confirma ventana exacta ──
            if self._first_dump_pct_call:
                self._first_dump_pct_call = False
                logger.info(
                    f"[BTC-FILTER] >>> get_dump_pct() v5.0 ACTIVO <<< "
                    f"| Ventana exacta: {window_minutes}m | tf={tf} | candles_back={candles_back} "
                    f"| pct_change={pct_change:.2f}%"
                )
            
            return pct_change
            
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"[BTC-FILTER] !!! ERROR en dump_pct({window_minutes}m) (error #{self._error_count}): {e} "
                f"- retornando 0.0 (PELIGRO: puede no detectar caida de BTC)"
            )
            return 0.0
    
    def get_btc_trend_1h(self) -> str:
        """
        Compara precio actual vs hace 1 hora.
        Retorna: "UP" | "DOWN" | "SIDEWAYS" (umbral ±0.5%)
        """
        try:
            candles = self.fetcher.get_klines_for_nexus("BTCUSDT", "1h", limit=10)
            
            if not candles or len(candles) < 2:
                logger.warning("[BTC-FILTER] No se pudieron obtener velas 1h BTC - retornando SIDEWAYS")
                return "SIDEWAYS"
            
            current_price = float(candles[-1]["close"])  # Close actual
            price_1h_ago = float(candles[0]["close"])    # Close hace 1h
            pct_change = ((current_price - price_1h_ago) / price_1h_ago) * 100
            
            if pct_change > 0.5:
                trend = "UP"
            elif pct_change < -0.5:
                trend = "DOWN"
            else:
                trend = "SIDEWAYS"
            
            logger.debug(f"[BTC-FILTER] Trend 1h: {trend} (pct_change={pct_change:.2f}%)")
            return trend
            
        except Exception as e:
            logger.error(f"[BTC-FILTER] Error al obtener trend 1h BTC: {e} - retornando SIDEWAYS")
            return "SIDEWAYS"
    
    def is_flash_crash(self) -> bool:
        """
        Retorna True si BTC cayó más de BTC_FLASH_CRASH_PCT_1H en la última hora.
        Caché 5 minutos.
        """
        now = time.time()
        
        # Return cached if fresh
        if self._flash_crash_cache is not None and (now - self._flash_crash_cache_time) < 300:
            return self._flash_crash_cache
        
        try:
            pct_1h = self.get_dump_pct(60)
            
            if pct_1h <= config.BTC_FLASH_CRASH_PCT_1H:
                logger.warning(f"[BTC-FILTER] FLASH CRASH DETECTADO - BTC cayó {pct_1h:.2f}% en 1h")
                self._flash_crash_cache = True
                self._flash_crash_cache_time = now
                return True
            else:
                self._flash_crash_cache = False
                self._flash_crash_cache_time = now
                return False
                
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"[BTC-FILTER] !!! ERROR en flash_crash check (error #{self._error_count}): {e} "
                f"- retornando False (PELIGRO: flash crash podria pasar desapercibido)"
            )
            self._flash_crash_cache = False
            self._flash_crash_cache_time = now
            return False
    
    def is_btc_bleeding(self) -> tuple:
        """
        VETO DURO: Detecta si BTC está en sangrado activo (>1% caída en 1h).
        Este fue el fix principal tras la pérdida de 20 USDT: BTC puede caer 
        gradualmente sin activar los umbrales de 5m/15m, pero el sangrado de 1h
        es imposible de falsificar.
        
        Retorna: (bleeding: bool, pct_1h: float)
        """
        self._bleeding_call_count += 1
        try:
            pct_1h = self.get_dump_pct(60)
            bleed_threshold = float(getattr(config, "BTC_BLEED_1H_THRESHOLD", -1.0))
            
            if pct_1h <= bleed_threshold:
                logger.warning(
                    f"[BTC-FILTER] BLOOD-SHIELD BLOQUEO #{self._bleeding_call_count} "
                    f"— BTC cayo {pct_1h:.2f}% en 1h (umbral {bleed_threshold}%) — LONGs PROHIBIDOS"
                )
                return True, pct_1h
            
            # Log cada N llamadas para confirmar que el shield esta ACTIVO y chequeando
            if self._bleeding_call_count <= 3 or self._bleeding_call_count % 10 == 0:
                logger.info(
                    f"[BTC-FILTER] BLOOD-SHIELD OK #{self._bleeding_call_count} "
                    f"— BTC {pct_1h:+.2f}% en 1h (umbral {bleed_threshold}%) — LONGs permitidos"
                )
            
            return False, pct_1h
            
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"[BTC-FILTER] !!! ERROR en is_btc_bleeding (error #{self._error_count}, call #{self._bleeding_call_count}): {e} "
                f"- retornando False (PELIGRO: el Blood Shield esta ROTO)"
            )
            return False, 0.0
    
    def is_btc_daily_red(self) -> tuple:
        """
        VETO #11: Check si la vela diaria de BTC está en rojo.
        Retorna: (is_red: bool, daily_open: float, current_price: float)
        
        Una vela roja significa: precio actual < apertura diaria.
        Esto indica que BTC está en tendencia bajista en el día.
        """
        try:
            candles = self.fetcher.get_klines_for_nexus("BTCUSDT", "1d", limit=2)
            
            if not candles or len(candles) < 1:
                logger.warning("[BTC-FILTER] No se pudieron obtener velas 1d BTC - retornando False (seguro)")
                return False, 0.0, 0.0
            
            # La vela actual es candles[-1] (en desarrollo)
            current_candle = candles[-1]
            daily_open = float(current_candle["open"])
            current_price = float(current_candle["close"])
            
            is_red = current_price < daily_open
            
            if is_red:
                pct_change = ((current_price - daily_open) / daily_open) * 100
                logger.info(
                    f"[BTC-FILTER] Vela diaria ROJA detectada - BTC {pct_change:+.2f}% "
                    f"(open={daily_open:.2f}, close={current_price:.2f})"
                )
            
            return is_red, daily_open, current_price
            
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"[BTC-FILTER] !!! ERROR en is_btc_daily_red (error #{self._error_count}): {e} "
                f"- retornando False (seguro: no bloqueamos por error)"
            )
            return False, 0.0, 0.0
    
    def get_health_status(self) -> dict:
        """
        Retorna el estado de salud del filtro BTC para diagnóstico.
        Llamado desde setup_validator.py para el resumen periódico.
        """
        return {
            "regime_calls": self._regime_call_count,
            "bleeding_calls": self._bleeding_call_count,
            "errors": self._error_count,
            "current_regime": self._regime_cache or "UNKNOWN",
            "regime_cache_age_s": round(time.time() - self._regime_cache_time, 1) if self._regime_cache_time else -1,
            "flash_crash_active": self._flash_crash_cache or False,
        }
