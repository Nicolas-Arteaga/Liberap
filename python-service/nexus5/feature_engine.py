"""
NEXUS-5 Feature Engine — 6 Grupos, 18 Features
Optimizado para velas de 5 minutos.
Detecta Compression (Fase 1) e Ignition (Fase 2) — tanto LONG como SHORT.
"""
import pandas as pd
import numpy as np
import ta
from typing import Dict, Any
from datetime import datetime, timezone

EPSILON = 1e-9


class Nexus5FeatureEngine:
    """Calcula los 18 features de los 6 grupos de NEXUS-5 Ignition Core."""

    def compute(self, df: pd.DataFrame, df_15m: pd.DataFrame = None) -> Dict[str, Any]:
        """
        df debe tener columnas: open, high, low, close, volume (5m candles)
        df_15m: optional DataFrame with native 15m candles for structural MA50/MA99.
        Retorna dict con los 18 features + cyclicity features + structural features.
        """
        features: Dict[str, Any] = {}
        features.update(self._group1_price_action(df))
        features.update(self._group2_smc_ict(df))
        features.update(self._group3_wyckoff(df))
        features.update(self._group4_fractals(df))
        features.update(self._group5_volume(df))
        features.update(self._group6_ml_features(df))
        features.update(self._calculate_pump_cyclicity(df))
        features.update(self._calculate_structural_analysis(df, df_15m))
        return features

    # ══════════════════════════════════════════════════════════════════════════
    # G1: PRICE ACTION — RUPTURA SNIPER (Peso: 0.20)
    # Busca: compresión activa → ignición con una sola vela → eficiencia temporal
    # ══════════════════════════════════════════════════════════════════════════
    def _group1_price_action(self, df: pd.DataFrame) -> dict:
        n = len(df)
        last = df.iloc[-1]

        # ── 1. Compression Range ─────────────────────────────────────────────
        # Rango (max-min)/close de las últimas 20 velas.
        # < 0.04 (4%) = compresión activa → el resorte está apretado
        lookback = min(20, n)
        window = df.iloc[-lookback:]
        range_high = window['high'].max()
        range_low = window['low'].min()
        compression_range = (range_high - range_low) / (last['close'] + EPSILON)

        # ── 2. Ignition Candle ───────────────────────────────────────────────
        # La vela actual cruza el MAX del rango y su cuerpo > promedio de los cuerpos de las 10 velas anteriores.
        # Funciona también en SHORT: cruza el MIN del rango con cuerpo bajista fuerte.
        ignition_candle = False
        if n >= 11:
            prev_10 = df.iloc[-11:-1]
            avg_body = (prev_10['close'] - prev_10['open']).abs().mean()
            current_body = abs(last['close'] - last['open'])

            # Ignición alcista: cierra por encima del max de las 20 velas anteriores (excluyendo la actual)
            range_high_prev = df.iloc[-lookback:-1]['high'].max() if n > lookback else df.iloc[:-1]['high'].max()
            bull_ignition = (last['close'] > range_high_prev) and (current_body > avg_body)

            # Ignición bajista: cierra por debajo del min de las 20 velas anteriores
            range_low_prev = df.iloc[-lookback:-1]['low'].min() if n > lookback else df.iloc[:-1]['low'].min()
            bear_ignition = (last['close'] < range_low_prev) and (current_body > avg_body)

            ignition_candle = bull_ignition or bear_ignition

        # ── 3. Efficiency Check ──────────────────────────────────────────────
        # Comparar velocidad actual vs histórica.
        # Si subió 2% en 5min (1 vela) y antes le tomaba 60min (12 velas) → eficiencia = máxima (1.0)
        efficiency_check = 0.0
        if n >= 24:
            # Velocidad reciente: % movimiento de la última vela
            recent_speed = abs(last['close'] - last['open']) / (last['open'] + EPSILON)

            # Velocidad histórica: % movimiento promedio por vela en las últimas 12 velas
            hist_window = df.iloc[-24:-1]
            hist_speeds = (hist_window['close'] - hist_window['open']).abs() / (hist_window['open'] + EPSILON)
            hist_avg_speed = hist_speeds.mean()

            if hist_avg_speed > EPSILON:
                # Ratio: cuántas veces más rápido es ahora vs el promedio
                speed_ratio = recent_speed / hist_avg_speed
                # Normalizar a 0-1: ratio de 5x = 1.0, ratio de 1x = 0.2
                efficiency_check = min(1.0, max(0.0, (speed_ratio - 1.0) / 4.0))

        return {
            "compression_range": round(float(compression_range), 6),
            "ignition_candle": bool(ignition_candle),
            "efficiency_check": round(float(efficiency_check), 4),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # G2: SMC/ICT — DESPLAZAMIENTO (Peso: 0.15)
    # Busca: FVG gigante, Micro-CHoCH, Order Block instantáneo
    # ══════════════════════════════════════════════════════════════════════════
    def _group2_smc_ict(self, df: pd.DataFrame) -> dict:
        n = len(df)
        displacement_fvg = False
        micro_choch = False
        instant_order_block = False

        if n < 10:
            return {
                "displacement_fvg": False,
                "micro_choch": False,
                "instant_order_block": False,
            }

        last = df.iloc[-1]

        # ── 1. Displacement FVG (Fair Value Gap Gigante) ─────────────────────
        # FVG normal requiere >0.1% del precio. Para NEXUS-5 exigimos >0.3% (desplazamiento real).
        for i in range(max(2, n - 5), n):
            if i < 2:
                continue
            # Bullish FVG: high de vela i-2 < low de vela i
            fvg_bull = df.iloc[i - 2]['high'] < df.iloc[i]['low']
            # Bearish FVG: low de vela i-2 > high de vela i
            fvg_bear = df.iloc[i - 2]['low'] > df.iloc[i]['high']

            if fvg_bull or fvg_bear:
                gap = min(
                    abs(df.iloc[i]['low'] - df.iloc[i - 2]['high']),
                    abs(df.iloc[i - 2]['low'] - df.iloc[i]['high'])
                )
                gap_pct = gap / (df.iloc[i]['close'] + EPSILON)
                if gap_pct > 0.003:  # >0.3% = FVG GIGANTE (desplazamiento)
                    displacement_fvg = True
                    break

        # ── 2. Micro-CHoCH (Change of Character en 5m) ──────────────────────
        # Primer quiebre de un máximo/mínimo previo de las últimas 8 velas.
        # Alcista: la vela actual cierra por encima del high más alto de las 8 velas previas
        # Bajista: la vela actual cierra por debajo del low más bajo de las 8 velas previas
        choch_window = min(8, n - 1)
        recent_highs = df.iloc[-(choch_window + 1):-1]['high'].max()
        recent_lows = df.iloc[-(choch_window + 1):-1]['low'].min()

        if last['close'] > recent_highs or last['close'] < recent_lows:
            micro_choch = True

        # ── 3. Instant Order Block (últimas 5 velas) ────────────────────────
        # OB alcista: vela bajista sólida (body/hl > 0.6) en las últimas 5 velas,
        # y el precio actual está mitigando esa zona.
        ob_lookback = min(5, n - 1)
        for i in range(n - ob_lookback - 1, n - 1):
            if i < 0:
                continue
            candle = df.iloc[i]
            body = abs(candle['close'] - candle['open'])
            hl = candle['high'] - candle['low'] + EPSILON

            if body / hl > 0.6:
                # OB Alcista: vela bajista previa al movimiento alcista
                if candle['close'] < candle['open']:
                    if last['low'] <= candle['high'] and last['close'] > candle['low']:
                        instant_order_block = True
                        break
                # OB Bajista: vela alcista previa al movimiento bajista
                else:
                    if last['high'] >= candle['low'] and last['close'] < candle['high']:
                        instant_order_block = True
                        break

        return {
            "displacement_fvg": bool(displacement_fvg),
            "micro_choch": bool(micro_choch),
            "instant_order_block": bool(instant_order_block),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # G3: WYCKOFF INTRADAY — FASES DE RESORTE (Peso: 0.15)
    # Detecta: Compression Zone, SOS (Sign of Strength), Jumping the Creek
    # ══════════════════════════════════════════════════════════════════════════
    def _group3_wyckoff(self, df: pd.DataFrame) -> dict:
        n = len(df)
        compression_zone = False
        sos_detected = False
        jumping_creek = False

        if n < 15:
            return {
                "compression_zone": False,
                "sos_detected": False,
                "jumping_creek": False,
            }

        last = df.iloc[-1]

        # ── 1. Compression Zone ──────────────────────────────────────────────
        # El precio estuvo encerrado en un rango <4% por al menos 12 velas consecutivas.
        # Buscamos la ventana más larga de compresión en las últimas 20 velas.
        for window_size in range(min(20, n), 11, -1):
            window = df.iloc[-window_size:]
            range_high = window['high'].max()
            range_low = window['low'].min()
            range_pct = (range_high - range_low) / (window['close'].mean() + EPSILON)

            if range_pct < 0.04:
                compression_zone = True
                break

        # ── 2. SOS (Sign of Strength) ────────────────────────────────────────
        # Primera vela que logra cerrar por fuera de la lateralización.
        # Buscamos el rango de las últimas 12-20 velas y verificamos si la última cierra fuera.
        sos_window = min(15, n - 1)
        sos_range = df.iloc[-(sos_window + 1):-1]
        sos_high = sos_range['high'].max()
        sos_low = sos_range['low'].min()
        sos_range_pct = (sos_high - sos_low) / (sos_range['close'].mean() + EPSILON)

        # Solo es SOS si venimos de compresión (<4%) y la vela actual cierra fuera
        if sos_range_pct < 0.04:
            if last['close'] > sos_high or last['close'] < sos_low:
                sos_detected = True

        # ── 3. Jumping the Creek ─────────────────────────────────────────────
        # El cruce definitivo del "techo" de la Fase 1 con volumen >2x promedio.
        # Es SOS + confirmación de volumen explosivo.
        if sos_detected:
            vol_ma = df['volume'].iloc[-20:].mean() if n >= 20 else df['volume'].mean()
            if last['volume'] > vol_ma * 2.0:
                jumping_creek = True

        return {
            "compression_zone": bool(compression_zone),
            "sos_detected": bool(sos_detected),
            "jumping_creek": bool(jumping_creek),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # G4: FRACTALES & ESTRUCTURA — MICRO-TENDENCIA (Peso: 0.10)
    # Busca: fractal high break, EMA-7 angle, HH/HL sequence
    # ══════════════════════════════════════════════════════════════════════════
    def _group4_fractals(self, df: pd.DataFrame) -> dict:
        n = len(df)
        fractal_high_break = False
        ema7_angle_val = 0.0
        hh_hl_sequence = False

        if n < 10:
            return {
                "fractal_high_break": False,
                "ema7_angle": 0.0,
                "hh_hl_sequence": False,
            }

        last = df.iloc[-1]

        # ── 1. Fractal High Break ────────────────────────────────────────────
        # Ruptura del último punto alto fractal de 5m.
        # Un fractal high: vela central con high mayor que las 2 velas a cada lado.
        # Buscamos el último fractal high en las velas [-10:-2] y verificamos si la última lo rompe.
        last_fractal_high = None
        for i in range(max(2, n - 10), n - 2):
            if i < 2 or i >= n - 2:
                continue
            h = df.iloc[i]['high']
            if (h > df.iloc[i - 1]['high'] and h > df.iloc[i - 2]['high'] and
                    h > df.iloc[i + 1]['high'] and h > df.iloc[i + 2]['high']):
                last_fractal_high = h

        # También buscamos fractal low para SHORT signals
        last_fractal_low = None
        for i in range(max(2, n - 10), n - 2):
            if i < 2 or i >= n - 2:
                continue
            lo = df.iloc[i]['low']
            if (lo < df.iloc[i - 1]['low'] and lo < df.iloc[i - 2]['low'] and
                    lo < df.iloc[i + 1]['low'] and lo < df.iloc[i + 2]['low']):
                last_fractal_low = lo

        # Break: la última vela cierra por encima del fractal high o por debajo del fractal low
        if last_fractal_high is not None and last['close'] > last_fractal_high:
            fractal_high_break = True
        if last_fractal_low is not None and last['close'] < last_fractal_low:
            fractal_high_break = True  # también cuenta como break (bearish)

        # ── 2. EMA-7 Angle ───────────────────────────────────────────────────
        # Ángulo de la EMA-7. Si > 45° → momentum vertical.
        # Calculamos la pendiente normalizada entre los últimos 3 valores de EMA-7.
        if n >= 10:
            ema7 = ta.trend.EMAIndicator(df['close'], window=7).ema_indicator()
            if len(ema7) >= 3:
                ema_last = ema7.iloc[-1]
                ema_prev = ema7.iloc[-3]
                # Pendiente: cambio en precio / precio (normalizado)
                slope = (ema_last - ema_prev) / (ema_prev + EPSILON)
                # Normalizar: pendiente de 2% en 3 velas = ángulo máximo (1.0)
                ema7_angle_val = min(1.0, max(0.0, abs(slope) / 0.02))

        # ── 3. HH/HL Sequence ────────────────────────────────────────────────
        # Dos mínimos crecientes consecutivos en 5m (estructura alcista incipiente).
        # O dos máximos decrecientes (estructura bajista para SHORT).
        if n >= 20:
            # Comparar los lows de las últimas 3 ventanas de 5 velas
            low1 = df['low'].iloc[-15:-10].min()
            low2 = df['low'].iloc[-10:-5].min()
            low3 = df['low'].iloc[-5:].min()

            high1 = df['high'].iloc[-15:-10].max()
            high2 = df['high'].iloc[-10:-5].max()
            high3 = df['high'].iloc[-5:].max()

            # Alcista: Higher Lows + Higher Highs
            if low2 > low1 and low3 > low2 and high2 > high1:
                hh_hl_sequence = True
            # Bajista: Lower Highs + Lower Lows (para SHORT)
            if high2 < high1 and high3 < high2 and low2 < low1:
                hh_hl_sequence = True

        return {
            "fractal_high_break": bool(fractal_high_break),
            "ema7_angle": round(float(ema7_angle_val), 4),
            "hh_hl_sequence": bool(hh_hl_sequence),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # G5: VOLUME PROFILE & ORDER FLOW — CORAZÓN (Peso: 0.25)
    # El grupo más importante de NEXUS-5. Busca: >3x volumen, bots peleando, imbalance.
    # ══════════════════════════════════════════════════════════════════════════
    def _group5_volume(self, df: pd.DataFrame) -> dict:
        n = len(df)
        last = df.iloc[-1]

        # ── 1. Relative Volume Multiplier ────────────────────────────────────
        # Volumen actual vs promedio de 20 velas. Target: >3x o >4x = ignición.
        vol_lookback = min(20, n)
        vol_ma = df['volume'].iloc[-vol_lookback:].mean()
        relative_vol_multiplier = last['volume'] / (vol_ma + EPSILON)

        # ── 2. Volume Intensity ──────────────────────────────────────────────
        # Volumen de la vela actual dividido por el body size.
        # Alta intensidad con poco movimiento de precio = bots peleando (acumulación agresiva).
        body = abs(last['close'] - last['open']) + EPSILON
        vol_intensity = last['volume'] / body
        # Normalizar: dividir por el vol_intensity promedio de las últimas 10 velas
        if n >= 11:
            prev_bodies = (df['close'].iloc[-11:-1] - df['open'].iloc[-11:-1]).abs() + EPSILON
            prev_vol_intensities = df['volume'].iloc[-11:-1].values / prev_bodies.values
            avg_vol_intensity = prev_vol_intensities.mean()
            if avg_vol_intensity > EPSILON:
                vol_intensity = vol_intensity / avg_vol_intensity
            else:
                vol_intensity = 1.0
        else:
            vol_intensity = 1.0

        # ── 3. Buying Imbalance ──────────────────────────────────────────────
        # % del volumen de las últimas 5 velas que fue de compra (cierre > apertura).
        # >70% = imbalance alcista. <30% = imbalance bajista (SHORT signal).
        imbalance_lookback = min(5, n)
        buy_vol = 0.0
        total_vol = 0.0
        for i in range(n - imbalance_lookback, n):
            row = df.iloc[i]
            total_vol += row['volume']
            if row['close'] > row['open']:
                buy_vol += row['volume']

        buying_imbalance = buy_vol / (total_vol + EPSILON)

        return {
            "relative_vol_multiplier": round(float(relative_vol_multiplier), 4),
            "vol_intensity": round(float(vol_intensity), 4),
            "buying_imbalance": round(float(buying_imbalance), 4),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # G6: ML FEATURES — ANOMALÍAS ESTADÍSTICAS (Peso: 0.15)
    # ATR Expansion, Z-Score, RSI Velocity
    # ══════════════════════════════════════════════════════════════════════════
    def _group6_ml_features(self, df: pd.DataFrame) -> dict:
        n = len(df)
        last_close = df['close'].iloc[-1]

        # ── 1. ATR Expansion ─────────────────────────────────────────────────
        # ATR% actual vs ATR% promedio de las últimas 50 velas.
        # >1.5 = el "resorte" se soltó (volatilidad expandiéndose de golpe).
        atr_period = min(14, n)
        atr_indicator = ta.volatility.AverageTrueRange(
            df['high'], df['low'], df['close'], window=atr_period
        )
        atr_series = atr_indicator.average_true_range()
        atr_current = atr_series.iloc[-1]
        atr_current_pct = atr_current / (last_close + EPSILON)

        atr_expansion = 1.0
        if n >= 50:
            atr_hist = atr_series.iloc[-50:]
            atr_avg_pct = (atr_hist / (df['close'].iloc[-50:] + EPSILON)).mean()
            if atr_avg_pct > EPSILON:
                atr_expansion = atr_current_pct / atr_avg_pct
        elif n >= 20:
            atr_hist = atr_series.iloc[-20:]
            atr_avg_pct = (atr_hist / (df['close'].iloc[-20:] + EPSILON)).mean()
            if atr_avg_pct > EPSILON:
                atr_expansion = atr_current_pct / atr_avg_pct

        # ── 2. Z-Score ───────────────────────────────────────────────────────
        # Distancia del precio actual vs su media móvil de 50 velas, en desvíos estándar.
        # |Z| > 2.0 = movimiento estadísticamente anómalo (palo vertical).
        ma_period = min(50, n)
        ma = df['close'].rolling(ma_period).mean().iloc[-1]
        std = df['close'].rolling(ma_period).std().iloc[-1]
        z_score = (last_close - ma) / (std + EPSILON)

        # ── 3. RSI Velocity ──────────────────────────────────────────────────
        # NO miramos el nivel de RSI (si es 80), sino qué tan rápido llegó ahí.
        # Subir de 50 a 80 en 2 velas = compra masiva, no sobrecompra.
        rsi_period = min(14, n)
        rsi_indicator = ta.momentum.RSIIndicator(df['close'], window=rsi_period)
        rsi_series = rsi_indicator.rsi()

        rsi_velocity = 0.0
        if len(rsi_series) >= 4:
            rsi_now = rsi_series.iloc[-1]
            rsi_3ago = rsi_series.iloc[-4]
            # Cambio absoluto de RSI en las últimas 3 velas
            rsi_velocity = rsi_now - rsi_3ago
            # Normalizar: velocity de +30 puntos en 3 velas = 1.0, -30 = -1.0
            rsi_velocity = rsi_velocity / 30.0
            rsi_velocity = max(-1.0, min(1.0, rsi_velocity))

        return {
            "atr_expansion": round(float(atr_expansion), 4),
            "z_score": round(float(z_score), 4),
            "rsi_velocity": round(float(rsi_velocity), 4),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # PUMP CYCLICITY DETECTOR — EL RELOJ DEL MARKET MAKER (v6.2)
    # Detecta patrones de 24h en los pumps para predecir el próximo movimiento.
    # ══════════════════════════════════════════════════════════════════════════
    def _calculate_pump_cyclicity(self, df: pd.DataFrame) -> dict:
        """
        Analiza el historial de velas buscando "Picos de Ignición" con patrón de 24h.
        
        Lógica:
        1. Filtra velas donde Volumen > 3x promedio y Precio > 2.5%
        2. Calcula deltas de tiempo entre picos consecutivos
        3. Si el delta es múltiplo de 24h (86400 seg) con margen 2%, activa cycle_detected
        4. Calcula ETA para el próximo pump basado en el último ciclo
        
        Retorna:
        - cycle_detected: bool (si detectó patrón de 24h)
        - minutes_to_next_pump: float (minutos restantes para el próximo pump)
        - confidence_boost: float (boost de confianza basado en proximidad)
        """
        n = len(df)
        
        # Necesitamos al menos 100 velas para detectar patrones (~8 horas en 5m)
        if n < 100:
            return {
                "cycle_detected": False,
                "minutes_to_next_pump": 0.0,
                "confidence_boost": 0.0
            }
        
        try:
            # 1. Detectar eventos históricos de ignición
            vol_ma = df['volume'].rolling(20).mean()
            
            # Pico de ignición: volumen > 3x promedio Y precio subió > 2.5%
            price_change_pct = (df['close'] - df['open']) / (df['open'] + EPSILON) * 100
            spikes = df[(df['volume'] > vol_ma * 3) & (price_change_pct > 2.5)]
            
            if len(spikes) < 2:
                return {
                    "cycle_detected": False,
                    "minutes_to_next_pump": 0.0,
                    "confidence_boost": 0.0
                }
            
            # 2. Calcular deltas de tiempo entre los últimos 2 pumps
            # Asumimos que el índice del DataFrame representa el tiempo
            last_pump_idx = spikes.index[-1]
            prev_pump_idx = spikes.index[-2]
            
            # Calcular delta en velas (cada vela = 5 minutos en NEXUS-5)
            delta_candles = last_pump_idx - prev_pump_idx
            delta_seconds = delta_candles * 300  # 5 minutos = 300 segundos
            
            # 3. Verificar si es múltiplo de 24 horas (86400 seg)
            # Margen de error: 2% de 24h = ~28.8 minutos = ~6 velas
            seconds_in_24h = 86400
            margin_seconds = seconds_in_24h * 0.02  # 2% margen
            
            # Calcular el residuo de la división por 24h
            remainder = abs(delta_seconds % seconds_in_24h)
            
            # Si el residuo es pequeño (o muy cercano a 24h), es un ciclo de 24h
            is_24h_cycle = remainder < margin_seconds or remainder > (seconds_in_24h - margin_seconds)
            
            if not is_24h_cycle:
                return {
                    "cycle_detected": False,
                    "minutes_to_next_pump": 0.0,
                    "confidence_boost": 0.0
                }
            
            # 4. Calcular ETA para el próximo pump
            # Tiempo transcurrido desde el último pump (en velas)
            candles_since_last = n - 1 - last_pump_idx
            seconds_since_last = candles_since_last * 300
            
            # Tiempo restante para completar 24h desde el último pump
            seconds_to_next = seconds_in_24h - (seconds_since_last % seconds_in_24h)
            minutes_to_next = seconds_to_next / 60.0
            
            # 5. Calcular confidence boost basado en proximidad
            # Si faltan < 30 minutos: boost +15%
            # Si faltan < 10 minutos: boost +25%
            confidence_boost = 0.0
            if minutes_to_next < 10:
                confidence_boost = 0.25
            elif minutes_to_next < 30:
                confidence_boost = 0.15
            elif minutes_to_next < 60:
                confidence_boost = 0.10
            
            return {
                "cycle_detected": True,
                "minutes_to_next_pump": round(minutes_to_next, 1),
                "confidence_boost": round(confidence_boost, 4)
            }
            
        except Exception as e:
            # Si hay algún error, retornar valores seguros
            return {
                "cycle_detected": False,
                "minutes_to_next_pump": 0.0,
                "confidence_boost": 0.0
            }

    # ══════════════════════════════════════════════════════════════════════════
    # ESTRUCTURAL ANALYSIS — Reglas de Oro (v7.0 → v10.0 Native 15m)
    # MA50/MA99 calculadas directamente de velas NATIVAS de 15m (sin resample)
    # ══════════════════════════════════════════════════════════════════════════
    def _calculate_structural_analysis(self, df: pd.DataFrame, df_15m: pd.DataFrame = None) -> dict:
        """
        Calcula características estructurales basadas en MA50 y MA99 de 15m NATIVAS.
        
        Bottom Sniper v11.0 — Tres prerrequisitos OBLIGATORIOS:
        1. SUPER CAÍDA: crash >= 12% visible en velas 15m recientes
        2. MA99 descendiendo en diagonal: slope < -1% (no solo "no subiendo")
        3. Precio lateralizando: rango reciente < 4% en 15m
        
        Si las 3 condiciones no se cumplen → is_bottom_sniper = False.
        """
        n = len(df)
        
        # Sin velas 15m nativas → sentinel (no vetar, no decidir)
        if df_15m is None or len(df_15m) < 30:
            n_15m = len(df_15m) if df_15m is not None else 0
            print(f"[Structural] SKIP: solo {n_15m} velas 15m (mínimo 30)")
            return {
                "slope_ma50": 0.0,
                "ma99_long_slope": 0.0,
                "is_bottom_sniper": False,
                "ma50_ma99_dist": 1.0,
                "price_to_ma99_pct": -999.0,  # Sentinel: sin datos, no aplicar veto
                "vol_ratio": 1.0,
                "gravity_ma99_safe": True,
                "compression_viper": False,
                "ma50_horizontal": False,
                "super_crash_pct": 0.0,
                "crash_detected": False,
            }
        
        try:
            n_15m = len(df_15m)
            print(f"[Structural] Usando {n_15m} velas 15m NATIVAS (sin resample)")

            # MEDIAS REALES: calculadas directamente de velas nativas de 15m
            ma50_window = min(50, n_15m)
            ma99_window = min(99, n_15m)

            ma50 = df_15m['close'].rolling(window=ma50_window, min_periods=ma50_window).mean()
            ma99 = df_15m['close'].rolling(window=ma99_window, min_periods=ma99_window).mean()

            # Verificar que tenemos valores válidos al final
            if pd.isna(ma99.iloc[-1]) or pd.isna(ma50.iloc[-1]):
                print(f"[Structural] MA inválida: ma50={ma50.iloc[-1]}, ma99={ma99.iloc[-1]}")
                return {
                    "slope_ma50": 0.0,
                    "ma99_long_slope": 0.0,
                    "is_bottom_sniper": False,
                    "ma50_ma99_dist": 1.0,
                    "price_to_ma99_pct": -999.0,  # Sentinel: sin veto
                    "vol_ratio": 1.0,
                    "gravity_ma99_safe": True,
                    "compression_viper": False,
                    "ma50_horizontal": False,
                    "super_crash_pct": 0.0,
                    "crash_detected": False,
                }

            # ── 1. PENDIENTE MA99 (largo plazo, 40 velas) ──────────────────────
            lookback_slope = min(40, n_15m - 1)
            ma99_valid = ma99.dropna()
            if len(ma99_valid) >= 2:
                ma99_long_slope = (ma99_valid.iloc[-1] - ma99_valid.iloc[max(0, -lookback_slope)]) / (ma99_valid.iloc[max(0, -lookback_slope)] + EPSILON)
            else:
                ma99_long_slope = 0.0

            # ── 2. MA50 horizontalidad ──────────────────────────────────────────
            ma50_valid = ma50.dropna()
            slope_lookback = min(10, len(ma50_valid) - 1)
            if slope_lookback > 0:
                slope_ma50 = (ma50_valid.iloc[-1] - ma50_valid.iloc[-slope_lookback]) / (ma50_valid.iloc[-slope_lookback] + EPSILON)
            else:
                slope_ma50 = 0.0
            ma50_horizontal = abs(slope_ma50) < 0.01

            # ── 3. PRECIO vs MA99 ──────────────────────────────────────────────
            current_price = df['close'].iloc[-1]
            ma99_current = ma99.iloc[-1]
            price_below_ma99 = current_price < ma99_current
            price_to_ma99_pct = (current_price - ma99_current) / (ma99_current + EPSILON)

            # ── 4. Distancia MA50-MA99 ──────────────────────────────────────────
            ma50_current = ma50.iloc[-1]
            ma50_ma99_dist = abs(ma50_current - ma99_current) / (ma99_current + EPSILON)
            
            # ── 5. Vol ratio ────────────────────────────────────────────────────
            vol_ma_10 = df['volume'].iloc[-10:].mean()
            vol_current = df['volume'].iloc[-1]
            vol_ratio = vol_current / (vol_ma_10 + EPSILON)

            # ════════════════════════════════════════════════════════════════════
            # BOTTOM SNIPER v11.0 — TRES PRERREQUISITOS OBLIGATORIOS
            # ════════════════════════════════════════════════════════════════════

            # ── PRERREQUISITO #1: SUPER CAÍDA (crash >= 12%) ────────────────────
            # Buscar el pico más alto en la primera mitad de las velas 15m,
            # luego el valle más bajo después del pico.
            search_end = max(int(n_15m * 0.75), 30)  # pico en las primeras 75% de velas
            peak_idx = df_15m['close'].iloc[:search_end].idxmax()
            peak_price = df_15m['close'].iloc[peak_idx]

            # Valle: el mínimo después del pico
            if peak_idx < n_15m - 5:
                trough_idx = df_15m['close'].iloc[peak_idx:].idxmin()
                trough_price = df_15m['close'].iloc[trough_idx]
                crash_pct = (peak_price - trough_price) / (peak_price + EPSILON)
            else:
                crash_pct = 0.0
                trough_price = df_15m['close'].iloc[-1]

            super_crash = crash_pct >= 0.12  # crash >= 12%

            # ── PRERREQUISITO #2: MA99 BAJANDO EN DIAGONAL ──────────────────────
            # La MA99 debe estar activamente cayendo, no solo "no subiendo".
            # slope < -1% en las últimas 40 velas = diagonal visible.
            ma99_descending = ma99_long_slope < -0.01

            # ── PRERREQUISITO #3: PRECIO LATERALIZANDO ──────────────────────────
            # El rango de las últimas 20 velas 15m debe ser < 4% (lateralización clara).
            lat_lookback = min(20, n_15m)
            lat_window = df_15m.iloc[-lat_lookback:]
            lat_range = (lat_window['high'].max() - lat_window['low'].min()) / (lat_window['close'].iloc[-1] + EPSILON)
            price_lateralizing = lat_range < 0.04

            # ── VEREDICTO FINAL: las 3 deben ser True ───────────────────────────
            is_bs = bool(super_crash and ma99_descending and price_lateralizing)

            print(f"[Structural] 15m NATIVO: crash={crash_pct:.4f}(>={0.12})={super_crash} | ma99_slope={ma99_long_slope:.4f}(<-0.01)={ma99_descending} | lat_range={lat_range:.4f}(<0.04)={price_lateralizing} | BELOW={price_below_ma99}")
            print(f"[Structural] is_bottom_sniper={is_bs}")

            return {
                "slope_ma50": round(float(slope_ma50), 6),
                "ma99_long_slope": round(float(ma99_long_slope), 6),
                "is_bottom_sniper": is_bs,
                "ma50_ma99_dist": round(float(ma50_ma99_dist), 6),
                "price_to_ma99_pct": round(float(price_to_ma99_pct), 6),
                "vol_ratio": round(float(vol_ratio), 4),
                "gravity_ma99_safe": True,
                "compression_viper": False,
                "ma50_horizontal": bool(ma50_horizontal),
                "super_crash_pct": round(float(crash_pct), 6),
                "crash_detected": bool(super_crash),
            }
            
        except Exception as e:
            print(f"[Structural] ERROR: {e}")
            # Si hay algún error, retornar sentinel para no aplicar veto
            return {
                "slope_ma50": 0.0,
                "ma99_long_slope": 0.0,
                "is_bottom_sniper": False,
                "ma50_ma99_dist": 1.0,
                "price_to_ma99_pct": -999.0,  # Sentinel: sin veto cuando hay error
                "vol_ratio": 1.0,
                "gravity_ma99_safe": True,
                "compression_viper": False,
                "ma50_horizontal": False,
                "super_crash_pct": 0.0,
                "crash_detected": False,
            }
