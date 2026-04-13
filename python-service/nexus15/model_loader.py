import os
import logging
import numpy as np

logger = logging.getLogger("NEXUS15_MODEL")

NEXUS15_FEATURES = [
    "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "consecutive_bull_bars", "order_block_detected", "fair_value_gap",
    "bos_detected", "wyckoff_phase_num", "spring_detected", "upthrust_detected",
    "fractal_high_5", "fractal_low_5", "trend_structure",
    "volume_ratio_20", "cvd_delta_norm", "volume_surge_bullish",
    "poc_proximity", "rsi_14_norm", "macd_histogram", "atr_percent",
]

MODEL_PATH = os.environ.get("NEXUS15_MODEL_PATH", "models/nexus15/xgb_nexus15_v1.json")


class Nexus15ModelLoader:
    """Carga el modelo XGBoost de NEXUS-15 con lazy loading y graceful degradation."""

    def __init__(self):
        self._model = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        try:
            import xgboost as xgb
            if os.path.exists(MODEL_PATH):
                self._model = xgb.Booster()
                self._model.load_model(MODEL_PATH)
                logger.info(f"✅ NEXUS-15 XGBoost model loaded from {MODEL_PATH}")
            else:
                logger.warning(f"⚠️ NEXUS-15 model not found at {MODEL_PATH}. Fallback mode active.")
        except Exception as e:
            logger.error(f"❌ Failed to load NEXUS-15 model: {e}")
        self._loaded = True

    def predict(self, feature_vector: list) -> float | None:
        """Retorna probabilidad alcista (0.0-1.0) o None si no hay modelo."""
        self._load()
        if self._model is None:
            return None
        try:
            import xgboost as xgb
            dm = xgb.DMatrix([feature_vector], feature_names=NEXUS15_FEATURES)
            prob = self._model.predict(dm)[0]
            return float(np.clip(prob, 0.0, 1.0))
        except Exception as e:
            logger.error(f"❌ NEXUS-15 predict error: {e}")
            return None
