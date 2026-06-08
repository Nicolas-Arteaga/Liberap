"""
NEXUS-5 Model Loader — XGBoost lazy loading con graceful degradation.
Si el modelo no existe, el analyzer funciona con los scores heurísticos de los 6 grupos.
"""
import os
import logging
import numpy as np

logger = logging.getLogger("NEXUS5_MODEL")

NEXUS5_FEATURES = [
    "compression_range",
    "ignition_candle",
    "efficiency_check",
    "displacement_fvg",
    "micro_choch",
    "instant_order_block",
    "compression_zone",
    "sos_detected",
    "jumping_creek",
    "fractal_high_break",
    "ema7_angle",
    "hh_hl_sequence",
    "relative_vol_multiplier",
    "vol_intensity",
    "buying_imbalance",
    "atr_expansion",
    "z_score",
    "rsi_velocity",
]

MODEL_PATH = os.environ.get("NEXUS5_MODEL_PATH", "models/nexus5/xgb_nexus5_v1.json")


class Nexus5ModelLoader:
    """Carga el modelo XGBoost de NEXUS-5 con lazy loading y graceful degradation."""

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
                logger.info(f"✅ NEXUS-5 XGBoost model loaded from {MODEL_PATH}")
            else:
                logger.warning(f"⚠️ NEXUS-5 model not found at {MODEL_PATH}. Heuristic mode active.")
        except ImportError:
            logger.warning("⚠️ xgboost not installed. NEXUS-5 running in heuristic-only mode.")
        except Exception as e:
            logger.error(f"❌ Failed to load NEXUS-5 model: {e}")
        self._loaded = True

    def predict(self, feature_vector: list) -> float | None:
        """Retorna probabilidad (0.0-1.0) o None si no hay modelo."""
        self._load()
        if self._model is None:
            return None
        try:
            import xgboost as xgb
            dm = xgb.DMatrix([feature_vector], feature_names=NEXUS5_FEATURES)
            prob = self._model.predict(dm)[0]
            return float(np.clip(prob, 0.0, 1.0))
        except Exception as e:
            logger.error(f"❌ NEXUS-5 predict error: {e}")
            return None
