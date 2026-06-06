import time
import logging
import numpy as np
import config

logger = logging.getLogger("BTCCorrelation")


class BTCCorrelation:
    """
    Calcula correlación rolling entre altcoins y BTC.
    Penaliza el score de Nexus proporcionalmente a la correlación cuando BTC está en DUMPING.
    """
    
    def __init__(self, fetcher, btc_filter):
        self.fetcher = fetcher
        self.btc_filter = btc_filter
        self._correlation_cache = {}
        self._cache_ttl = config.BTC_CORR_CACHE_MINUTES * 60
        self._call_count = 0
        self._fallback_count = 0  # Cuántas veces devolvimos 0.5 (datos insuficientes)
        
    def get_correlation(self, symbol: str) -> float:
        """
        Calcula correlación de Pearson entre retornos de symbol y BTCUSDT.
        Retorna valor entre -1 y 1.
        """
        now = time.time()
        
        # Check cache
        if symbol in self._correlation_cache:
            cached_corr, cached_time = self._correlation_cache[symbol]
            if (now - cached_time) < self._cache_ttl:
                return cached_corr
        
        try:
            # Obtener velas 5m para symbol y BTC con límite suficiente
            # Aumentamos el límite para asegurar suficientes velas para correlación
            limit = max(50, config.BTC_CORR_WINDOW_CANDLES * 2)
            symbol_candles = self.fetcher.get_klines_for_nexus(symbol, "5m", limit=limit)
            btc_candles = self.fetcher.get_klines_for_nexus("BTCUSDT", "5m", limit=limit)
            
            if not symbol_candles or not btc_candles or len(symbol_candles) < 2 or len(btc_candles) < 2:
                self._fallback_count += 1
                logger.warning(
                    f"[BTC-CORR] !!! Datos INSUFICIENTES para {symbol} "
                    f"(sym={len(symbol_candles) if symbol_candles else 0}, btc={len(btc_candles) if btc_candles else 0}) "
                    f"- retornando 0.5 (fallback #{self._fallback_count}, correlacion desconocida)"
                )
                self._correlation_cache[symbol] = (0.5, now)
                return 0.5
            
            # Extraer closes y calcular retornos porcentuales
            symbol_closes = np.array([float(c["close"]) for c in symbol_candles])
            btc_closes = np.array([float(c["close"]) for c in btc_candles])
            
            # Asegurar mismo tamaño
            min_len = min(len(symbol_closes), len(btc_closes))
            symbol_closes = symbol_closes[-min_len:]
            btc_closes = btc_closes[-min_len:]
            
            # Calcular retornos porcentuales
            symbol_returns = np.diff(symbol_closes) / symbol_closes[:-1]
            btc_returns = np.diff(btc_closes) / btc_closes[:-1]
            
            # Calcular correlación de Pearson
            if len(symbol_returns) < 2:
                self._fallback_count += 1
                logger.warning(f"[BTC-CORR] !!! Datos insuficientes para {symbol} tras diff (returns={len(symbol_returns)}) - retornando 0.5 (fallback #{self._fallback_count})")
                self._correlation_cache[symbol] = (0.5, now)
                return 0.5
            
            correlation = np.corrcoef(symbol_returns, btc_returns)[0, 1]
            
            # Handle NaN
            if np.isnan(correlation):
                self._fallback_count += 1
                logger.warning(f"[BTC-CORR] !!! Correlacion NaN para {symbol} - retornando 0.5 (fallback #{self._fallback_count})")
                self._correlation_cache[symbol] = (0.5, now)
                return 0.5
            
            self._call_count += 1
            # Log visible para las primeras correlaciones y cada 10 llamadas
            if self._call_count <= 3 or self._call_count % 10 == 0:
                logger.info(f"[BTC-CORR] {symbol} correlacion #{self._call_count} con BTC: {correlation:.3f}")
            self._correlation_cache[symbol] = (correlation, now)
            return correlation
            
        except Exception as e:
            self._fallback_count += 1
            logger.error(
                f"[BTC-CORR] !!! ERROR calculando correlacion para {symbol}: {e} "
                f"- retornando 0.5 (fallback #{self._fallback_count}, CORRELACION ROTA)"
            )
            self._correlation_cache[symbol] = (0.5, now)
            return 0.5
    
    def get_score_penalty(self, symbol: str, btc_regime: str) -> float:
        """
        Calcula penalización del score de Nexus basado en correlación y régimen BTC.
        Retorna multiplicador (0.0 - 1.0).
        """
        # Si BTC no está en DUMPING, no penalizar
        if btc_regime in ["BULLISH", "NEUTRAL"]:
            return 1.0
        
        if btc_regime != "DUMPING":
            return 1.0
        
        # Si BTC está en DUMPING, penalizar según correlación
        correlation = self.get_correlation(symbol)
        
        if correlation > config.BTC_CORR_HIGH_THRESHOLD:
            penalty = config.BTC_CORR_PENALTY_HIGH  # 0.60
            logger.info(f"[BTC-CORR] {symbol} penalización ALTA - corr={correlation:.3f} > {config.BTC_CORR_HIGH_THRESHOLD} → penalty={penalty:.2f}")
        elif correlation > config.BTC_CORR_MED_THRESHOLD:
            penalty = config.BTC_CORR_PENALTY_MED  # 0.75
            logger.info(f"[BTC-CORR] {symbol} penalización MEDIA - corr={correlation:.3f} > {config.BTC_CORR_MED_THRESHOLD} → penalty={penalty:.2f}")
        elif correlation > config.BTC_CORR_LOW_THRESHOLD:
            penalty = config.BTC_CORR_PENALTY_LOW  # 0.88
            logger.info(f"[BTC-CORR] {symbol} penalización LEVE - corr={correlation:.3f} > {config.BTC_CORR_LOW_THRESHOLD} → penalty={penalty:.2f}")
        else:
            penalty = 1.0  # Sin penalización - alt independiente
            logger.info(f"[BTC-CORR] {symbol} SIN penalizacion — corr={correlation:.3f} <= {config.BTC_CORR_LOW_THRESHOLD} (alt independiente de BTC)")
        
        return penalty
