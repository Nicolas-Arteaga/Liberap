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
        
    def get_regime(self) -> str:
        """
        Determina el régimen actual de BTC.
        Retorna: "BULLISH" | "DUMPING" | "NEUTRAL"
        """
        now = time.time()
        
        # Return cached if fresh
        if self._regime_cache and (now - self._regime_cache_time) < config.BTC_REGIME_CACHE_SEC:
            return self._regime_cache
        
        try:
            # Obtener velas 1m y 5m de BTCUSDT con límite suficiente para cálculos
            candles_1m = self.fetcher.get_klines_for_nexus("BTCUSDT", "1m", limit=60)
            candles_5m = self.fetcher.get_klines_for_nexus("BTCUSDT", "5m", limit=50)
            
            if not candles_1m or not candles_5m:
                logger.warning("[BTC-FILTER] No se pudieron obtener velas BTC - retornando NEUTRAL")
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
            
            # Determinar régimen
            if pct_5m < config.BTC_DUMP_THRESHOLD_5M or pct_15m < config.BTC_DUMP_THRESHOLD_15M:
                regime = "DUMPING"
                logger.info(f"[BTC-FILTER] Régimen DUMPING - pct_5m={pct_5m:.2f}% pct_15m={pct_15m:.2f}%")
            elif pct_5m > config.BTC_PUMP_THRESHOLD_5M:
                regime = "BULLISH"
                logger.info(f"[BTC-FILTER] Régimen BULLISH - pct_5m={pct_5m:.2f}%")
            else:
                regime = "NEUTRAL"
                logger.debug(f"[BTC-FILTER] Régimen NEUTRAL - pct_5m={pct_5m:.2f}% pct_15m={pct_15m:.2f}%")
            
            self._regime_cache = regime
            self._regime_cache_time = now
            return regime
            
        except Exception as e:
            logger.error(f"[BTC-FILTER] Error al obtener régimen BTC: {e} - retornando NEUTRAL")
            self._regime_cache = "NEUTRAL"
            self._regime_cache_time = now
            return "NEUTRAL"
    
    def get_dump_pct(self, window_minutes: int) -> float:
        """
        Retorna el cambio porcentual de BTC en la ventana indicada.
        Negativo = caída.
        """
        try:
            # Determinar timeframe apropiado con límite suficiente
            if window_minutes <= 5:
                tf = "1m"
                limit = max(10, window_minutes * 2)  # Mínimo 10 velas de 1m
            elif window_minutes <= 15:
                tf = "5m"
                limit = max(20, (window_minutes // 5) * 2)  # Mínimo 20 velas de 5m
            elif window_minutes <= 60:
                tf = "15m"
                limit = max(20, (window_minutes // 15) * 2)  # Mínimo 20 velas de 15m
            else:
                tf = "1h"
                limit = max(10, (window_minutes // 60) * 2)  # Mínimo 10 velas de 1h
            
            candles = self.fetcher.get_klines_for_nexus("BTCUSDT", tf, limit=limit)
            
            if not candles or len(candles) < 2:
                logger.warning(f"[BTC-FILTER] No se pudieron obtener velas BTC para ventana {window_minutes}m - retornando 0.0")
                return 0.0
            
            current_price = float(candles[-1]["close"])  # Close
            start_price = float(candles[0]["close"])     # Close de vela más antigua
            pct_change = ((current_price - start_price) / start_price) * 100
            
            return pct_change
            
        except Exception as e:
            logger.error(f"[BTC-FILTER] Error al calcular dump_pct({window_minutes}m): {e} - retornando 0.0")
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
            logger.error(f"[BTC-FILTER] Error al detectar flash crash: {e} - retornando False")
            self._flash_crash_cache = False
            self._flash_crash_cache_time = now
            return False
