import pandas as pd
import numpy as np
from datetime import datetime, timezone
from .schemas import Nexus15Request, Nexus15Response, GroupScores, Nexus15Features
from .feature_engine import Nexus15FeatureEngine
from .model_loader import Nexus15ModelLoader

# Pesos de grupo (configurables)
GROUP_WEIGHTS = {
    "g1": 0.15,
    "g2": 0.20,
    "g3": 0.15,
    "g4": 0.15,
    "g5": 0.20,
    "g6": 0.15,
}

STRONG_SIGNAL_THRESHOLD = 75.0


class Nexus15Analyzer:
    def __init__(self):
        self.engine = Nexus15FeatureEngine()
        self.model_loader = Nexus15ModelLoader()

    def analyze(self, req: Nexus15Request) -> Nexus15Response:
        df = pd.DataFrame([c.model_dump() for c in req.candles])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # 1. Calcular features
        feats = self.engine.compute(df)

        # 2. Scores por grupo (0.0 a 1.0)
        g1 = self._score_g1(feats)
        g2 = self._score_g2(feats)
        g3 = self._score_g3(feats)
        g4 = self._score_g4(feats)
        g5 = self._score_g5(feats)

        # 3. XGBoost prediction
        feature_vector = [
            feats["candle_body_ratio"], feats["upper_wick_ratio"],
            feats["lower_wick_ratio"], feats["consecutive_bull_bars"],
            int(feats["order_block_detected"]), int(feats["fair_value_gap"]),
            int(feats["bos_detected"]),
            self._wyckoff_to_num(feats["wyckoff_phase"]),
            int(feats["spring_detected"]), int(feats["upthrust_detected"]),
            int(feats["fractal_high_5"]), int(feats["fractal_low_5"]),
            feats["trend_structure"], feats["volume_ratio_20"],
            feats["cvd_delta"] / 1e6,  # normalizar
            int(feats["volume_surge_bullish"]), feats["poc_proximity"],
            feats["rsi_14"] / 100.0,
            feats["macd_histogram"],
            feats["atr_percent"],
        ]

        xgb_prob = self.model_loader.predict(feature_vector)
        g6 = xgb_prob if xgb_prob is not None else 0.5

        # 4. Raw Score (0 = Max Bearish, 1 = Max Bullish)
        technical_score_raw = (
            g1 * GROUP_WEIGHTS["g1"] +
            g2 * GROUP_WEIGHTS["g2"] +
            g3 * GROUP_WEIGHTS["g3"] +
            g4 * GROUP_WEIGHTS["g4"] +
            g5 * GROUP_WEIGHTS["g5"]
        )
        combined_raw = technical_score_raw * 0.85 + g6 * 0.15

        # 5. Direction First
        direction = self._determine_direction(feats, g6)

        # 6. AI Conviction (Absolute Strength)
        # Si combined = 0.1 (muy bajista), la distancia a 0.5 es 0.4 -> 80% Conviction
        # Si combined = 0.9 (muy alcista), la distancia a 0.5 es 0.4 -> 80% Conviction
        # El grupo SMC (g2) es de magnitud/volatilidad neutra, así que suma al conviction base
        conviction_base = abs(combined_raw - 0.5) * 2.0
        
        # Ajuste de convicción: SMC aumenta la convicción de la tendencia si se detectan barridos/bos.
        if direction != "NEUTRAL":
            conviction_base += (g2 * 0.20)  # Bonificación de evento institucional

        ai_confidence = round(min(1.0, conviction_base) * 100, 2)

        # 7. Recommendation
        recommendation = "Wait"
        if ai_confidence >= STRONG_SIGNAL_THRESHOLD:
            if direction == "BULLISH":
                recommendation = "Long"
            elif direction == "BEARISH":
                recommendation = "Short"

        # 8. Forward probabilities (decaying con XGBoost + ATR)
        base_prob = min(0.95, max(0.35, g6 if g6 else 0.5))
        atr_decay = max(0, 1 - feats["atr_percent"] / 5.0)

        # 8. Estimated range
        atr_current = feats["atr_percent"]
        estimated_range = round(atr_current * 2.5, 2)

        # 9. Regime (simplificado)
        regime = "BullTrend" if feats["trend_structure"] == 1 else (
            "BearTrend" if feats["trend_structure"] == -1 else "Ranging"
        )

        return Nexus15Response(
            symbol=req.symbol,
            timeframe=req.timeframe,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=ai_confidence,
            direction=direction,
            recommendation=recommendation,
            next_5_candles_prob=round(base_prob, 4),
            next_15_candles_prob=round(base_prob * atr_decay * 0.90, 4),
            next_20_candles_prob=round(base_prob * atr_decay * 0.82, 4),
            estimated_range_percent=estimated_range,
            regime=regime,
            group_scores=GroupScores(
                g1_price_action=round(g1 * 100, 2),
                g2_smc_ict=round(g2 * 100, 2),
                g3_wyckoff=round(g3 * 100, 2),
                g4_fractals=round(g4 * 100, 2),
                g5_volume=round(g5 * 100, 2),
                g6_ml=round(g6 * 100, 2),
            ),
            features=Nexus15Features(**{k: feats[k] for k in Nexus15Features.model_fields}),
            detectivity=self._build_detectivity(feats, g1, g2, g3, g4, g5, g6),
        )

    # ── Score helpers ──────────────────────────────────────────────────────
    def _score_g1(self, f) -> float:
        score = f["candle_body_ratio"] * 0.5
        score += (1 - f["upper_wick_ratio"]) * 0.2
        score += f["lower_wick_ratio"] * 0.2
        score += (f["consecutive_bull_bars"] / 5) * 0.1
        return round(min(1.0, max(0.0, score)), 4)

    def _score_g2(self, f) -> float:
        return round(
            int(f["order_block_detected"]) * 0.3 +
            int(f["fair_value_gap"]) * 0.2 +
            int(f["bos_detected"]) * 0.3 +
            int(f.get("liquidity_sweep", False)) * 0.2, 4
        )

    def _score_g3(self, f) -> float:
        phase_map = {"Markup": 0.9, "Accumulation": 0.7, "Ranging": 0.5,
                     "Distribution": 0.2, "Markdown": 0.1}
        score = phase_map.get(f["wyckoff_phase"], 0.5)
        score += int(f["spring_detected"]) * 0.1
        score -= int(f["upthrust_detected"]) * 0.1
        return round(min(1.0, max(0.0, score)), 4)

    def _score_g4(self, f) -> float:
        ts = f["trend_structure"]
        score = 0.5 + ts * 0.3
        score += int(f["fractal_high_5"]) * 0.1 * ts
        score -= int(f["fractal_low_5"]) * 0.05
        return round(min(1.0, max(0.0, score)), 4)

    def _score_g5(self, f) -> float:
        vol_score = min(f["volume_ratio_20"] / 3.0, 1.0) * 0.3
        cvd_norm = min(abs(f["cvd_delta"]) / 1e7, 1.0)
        cvd_dir = 1 if f["cvd_delta"] > 0 else -1
        score = 0.5 + cvd_dir * cvd_norm * 0.3
        score += int(f["volume_surge_bullish"]) * 0.2
        score += vol_score
        score -= f["poc_proximity"] * 0.1
        return round(min(1.0, max(0.0, score)), 4)

    def _determine_direction(self, f, xgb_prob) -> str:
        bullish_votes = 0
        bearish_votes = 0
        if f["trend_structure"] == 1: bullish_votes += 2
        if f["trend_structure"] == -1: bearish_votes += 2
        if f["cvd_delta"] > 0: bullish_votes += 1
        if f["cvd_delta"] < 0: bearish_votes += 1
        if xgb_prob and xgb_prob > 0.55: bullish_votes += 2
        if xgb_prob and xgb_prob < 0.45: bearish_votes += 2
        if f["bos_detected"]: bullish_votes += 1
        if f["upthrust_detected"]: bearish_votes += 1
        if bullish_votes > bearish_votes + 1: return "BULLISH"
        if bearish_votes > bullish_votes + 1: return "BEARISH"
        return "NEUTRAL"

    def _wyckoff_to_num(self, phase: str) -> float:
        return {"Markup": 1.0, "Accumulation": 0.6, "Ranging": 0.5,
                "Distribution": 0.4, "Markdown": 0.0}.get(phase, 0.5)

    def _build_detectivity(self, f, g1, g2, g3, g4, g5, g6) -> dict:
        return {
            "g1_price_action": f"Body ratio {f['candle_body_ratio']:.0%} | {f['consecutive_bull_bars']} velas alcistas consecutivas",
            "g2_smc_ict": f"OB: {'✅' if f['order_block_detected'] else '❌'} | FVG: {'✅' if f['fair_value_gap'] else '❌'} | BOS: {'✅' if f['bos_detected'] else '❌'} | Sweep: {'✅' if f.get('liquidity_sweep', False) else '❌'}",
            "g3_wyckoff": f"Fase: {f['wyckoff_phase']} | Spring: {'✅' if f['spring_detected'] else '❌'} | Upthrust: {'✅' if f['upthrust_detected'] else '❌'}",
            "g4_fractals": f"Estructura: {'HH/HL ↑' if f['trend_structure'] == 1 else 'LH/LL ↓' if f['trend_structure'] == -1 else 'Lateral'} | Fractal Alto: {'✅' if f['fractal_high_5'] else '❌'}",
            "g5_volume": f"Vol ratio {f['volume_ratio_20']:.2f}x | CVD {'📈' if f['cvd_delta'] > 0 else '📉'} {f['cvd_delta']:,.0f} | Surge: {'✅' if f['volume_surge_bullish'] else '❌'}",
            "g6_ml": f"XGBoost prob: {g6*100:.1f}% | RSI: {f['rsi_14']:.1f} | MACD hist: {f['macd_histogram']:.4f}",
        }
