import pandas as pd
import numpy as np
import ta
from typing import List, Dict, Any

EPSILON = 1e-9

class Nexus15FeatureEngine:
    """Calcula los 20 features de los 6 grupos de NEXUS-15."""

    def compute(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        df debe tener columnas: open, high, low, close, volume
        Retorna dict con los 20 features + scores por grupo.
        """
        features = {}
        features.update(self._group1_price_action(df))
        features.update(self._group2_smc_ict(df))
        features.update(self._group3_wyckoff(df))
        features.update(self._group4_fractals(df))
        features.update(self._group5_volume(df))
        features.update(self._group6_ml_features(df))
        return features

    # ── Grupo 1: Price Action ──────────────────────────────────────────────
    def _group1_price_action(self, df: pd.DataFrame) -> dict:
        last = df.iloc[-1]
        hl = last['high'] - last['low'] + EPSILON
        body = abs(last['close'] - last['open'])
        upper = last['high'] - max(last['open'], last['close'])
        lower = min(last['open'], last['close']) - last['low']

        consecutive = 0
        for i in range(len(df) - 1, -1, -1):
            if df.iloc[i]['close'] > df.iloc[i]['open']:
                consecutive += 1
            else:
                break

        return {
            "candle_body_ratio": round(body / hl, 4),
            "upper_wick_ratio":  round(upper / hl, 4),
            "lower_wick_ratio":  round(lower / hl, 4),
            "consecutive_bull_bars": min(consecutive, 5),
        }

    # ── Grupo 2: SMC/ICT ──────────────────────────────────────────────────
    def _group2_smc_ict(self, df: pd.DataFrame) -> dict:
        # Order Block: vela bajista fuerte seguida de impulso alcista
        ob_detected = False
        if len(df) >= 3:
            prev2 = df.iloc[-3]
            prev1 = df.iloc[-2]
            last  = df.iloc[-1]
            if (prev2['close'] < prev2['open'] and
                abs(prev2['close'] - prev2['open']) / (prev2['high'] - prev2['low'] + EPSILON) > 0.6 and
                last['close'] > prev2['high']):
                ob_detected = True

        # Fair Value Gap: gap entre high[i-2] y low[i]
        fvg = False
        if len(df) >= 3:
            if df.iloc[-3]['high'] < df.iloc[-1]['low']:
                gap_pct = (df.iloc[-1]['low'] - df.iloc[-3]['high']) / df.iloc[-1]['close']
                fvg = gap_pct > 0.001  # > 0.1%

        # BOS: nuevo HH (Higher High) sobre últimos 10 pivots
        bos = False
        if len(df) >= 10:
            recent_highs = df['high'].iloc[-10:-1]
            if df['high'].iloc[-1] > recent_highs.max():
                bos = True

        return {
            "order_block_detected": ob_detected,
            "fair_value_gap": fvg,
            "bos_detected": bos,
        }

    # ── Grupo 3: Wyckoff ──────────────────────────────────────────────────
    def _group3_wyckoff(self, df: pd.DataFrame) -> dict:
        # Fase Wyckoff simplificada via volumen + precio
        vol_ma = df['volume'].rolling(20).mean().iloc[-1]
        price_ma = df['close'].rolling(20).mean().iloc[-1]
        last_close = df['close'].iloc[-1]
        last_vol   = df['volume'].iloc[-1]

        phase = "Ranging"
        if last_close > price_ma and last_vol > vol_ma * 1.2:
            phase = "Markup"
        elif last_close < price_ma and last_vol > vol_ma * 1.2:
            phase = "Markdown"
        elif last_close > price_ma and last_vol <= vol_ma:
            phase = "Distribution"
        elif last_close < price_ma and last_vol <= vol_ma:
            phase = "Accumulation"

        # Spring: precio rompió mínimo reciente pero cerró por encima
        spring = False
        if len(df) >= 10:
            recent_low = df['low'].iloc[-10:-1].min()
            if df['low'].iloc[-1] < recent_low and df['close'].iloc[-1] > recent_low:
                spring = True

        # Upthrust: precio rompió máximo reciente pero cerró por debajo
        upthrust = False
        if len(df) >= 10:
            recent_high = df['high'].iloc[-10:-1].max()
            if df['high'].iloc[-1] > recent_high and df['close'].iloc[-1] < recent_high:
                upthrust = True

        return {
            "wyckoff_phase": phase,
            "spring_detected": spring,
            "upthrust_detected": upthrust,
        }

    # ── Grupo 4: Fractales & Estructura ───────────────────────────────────
    def _group4_fractals(self, df: pd.DataFrame) -> dict:
        fractal_high = False
        fractal_low  = False

        if len(df) >= 5:
            i = len(df) - 3  # penúltimo central para tener [-2] y [+2]
            if i >= 2:
                fractal_high = (df['high'].iloc[i] > df['high'].iloc[i-2] and
                                df['high'].iloc[i] > df['high'].iloc[i-1] and
                                df['high'].iloc[i] > df['high'].iloc[i+1] and
                                df['high'].iloc[i] > df['high'].iloc[i+2])
                fractal_low  = (df['low'].iloc[i] < df['low'].iloc[i-2] and
                                df['low'].iloc[i] < df['low'].iloc[i-1] and
                                df['low'].iloc[i] < df['low'].iloc[i+1] and
                                df['low'].iloc[i] < df['low'].iloc[i+2])

        # Trend structure: HH/HL = 1, LH/LL = -1, else = 0
        trend_structure = 0
        if len(df) >= 20:
            closes = df['close'].values
            # Comparar últimos 3 pivots (simplificado via rolling max/min)
            curr_high = df['high'].iloc[-5:].max()
            prev_high = df['high'].iloc[-10:-5].max()
            curr_low  = df['low'].iloc[-5:].min()
            prev_low  = df['low'].iloc[-10:-5].min()

            if curr_high > prev_high and curr_low > prev_low:
                trend_structure = 1   # HH y HL → alcista
            elif curr_high < prev_high and curr_low < prev_low:
                trend_structure = -1  # LH y LL → bajista

        return {
            "fractal_high_5": fractal_high,
            "fractal_low_5":  fractal_low,
            "trend_structure": trend_structure,
        }

    # ── Grupo 5: Volume Profile & Order Flow ──────────────────────────────
    def _group5_volume(self, df: pd.DataFrame) -> dict:
        vol_ma_20 = df['volume'].rolling(20).mean().iloc[-1]
        last_vol  = df['volume'].iloc[-1]
        vol_ratio = last_vol / (vol_ma_20 + EPSILON)

        # CVD Delta aproximado (últimas 10 velas)
        cvd_delta = 0.0
        for _, row in df.iloc[-10:].iterrows():
            if row['close'] > row['open']:
                cvd_delta += row['volume']
            else:
                cvd_delta -= row['volume']

        volume_surge_bullish = (vol_ratio > 1.5 and df['close'].iloc[-1] > df['open'].iloc[-1])

        # POC: precio de mayor volumen en ventana 50 velas
        poc_price = df.loc[df['volume'].idxmax(), 'close']
        current_price = df['close'].iloc[-1]
        poc_proximity = abs(current_price - poc_price) / (current_price + EPSILON)

        return {
            "volume_ratio_20": round(vol_ratio, 4),
            "cvd_delta": round(cvd_delta, 2),
            "volume_surge_bullish": volume_surge_bullish,
            "poc_proximity": round(poc_proximity, 4),
        }

    # ── Grupo 6: ML Features ──────────────────────────────────────────────
    def _group6_ml_features(self, df: pd.DataFrame) -> dict:
        rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]
        macd_diff = ta.trend.MACD(df['close']).macd_diff().iloc[-1]
        atr = ta.volatility.AverageTrueRange(
            df['high'], df['low'], df['close'], window=14
        ).average_true_range().iloc[-1]

        return {
            "rsi_14": round(float(rsi), 4),
            "macd_histogram": round(float(macd_diff), 6),
            "atr_percent": round(float(atr) / float(df['close'].iloc[-1]) * 100, 4),
        }
