"""
NEXUS-5 Analyzer — Ignition Core
Orquesta los 6 grupos, detecta fase, aplica RSI Bypass y genera la respuesta final.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from .schemas import Nexus5Request, Nexus5Response, GroupScores, Nexus5Features
from .feature_engine import Nexus5FeatureEngine
from .model_loader import Nexus5ModelLoader

# Pesos de grupo — G5 (Volumen) es el corazón con 25%
GROUP_WEIGHTS = {
    "g1": 0.20,  # Price Action — Ruptura Sniper
    "g2": 0.15,  # SMC/ICT — Desplazamiento
    "g3": 0.15,  # Wyckoff — Fases de Resorte
    "g4": 0.10,  # Fractales — Micro-Tendencia
    "g5": 0.25,  # Volume & Order Flow — CORAZÓN
    "g6": 0.15,  # ML — Anomalías
}

STRONG_SIGNAL_THRESHOLD = 60.0   # más bajo que NEXUS-15 (65) — más reactivo
RSI_BYPASS_VOL_THRESHOLD = 3.0   # volumen > 3x promedio para anular veto RSI


class Nexus5Analyzer:
    def __init__(self):
        self.engine = Nexus5FeatureEngine()
        self.model_loader = Nexus5ModelLoader()

    def analyze(self, req: Nexus5Request) -> Nexus5Response:
        df = pd.DataFrame([c.model_dump() for c in req.candles])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Build native 15m DataFrame if provided (for structural MA50/MA99)
        df_15m = None
        if req.candles_15m and len(req.candles_15m) >= 30:
            df_15m = pd.DataFrame([c.model_dump() for c in req.candles_15m])
            df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
            df_15m = df_15m.sort_values('timestamp').reset_index(drop=True)
            print(f"[NEXUS5] {req.symbol}: {len(df_15m)} velas 15m NATIVAS recibidas")

        # Build native 1m DataFrame if provided (for Sweep Detector v13.0)
        df_1m = None
        if req.candles_1m and len(req.candles_1m) >= 30:
            df_1m = pd.DataFrame([c.model_dump() for c in req.candles_1m])
            df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
            df_1m = df_1m.sort_values('timestamp').reset_index(drop=True)
            print(f"[NEXUS5] {req.symbol}: {len(df_1m)} velas 1m recibidas")

        # 1. Calcular features
        feats = self.engine.compute(df, df_15m)

        # 1b. Sweep Detection — dual timeframe 15m+1m (v13.0)
        if df_15m is not None and df_1m is not None:
            sweep_results = self.engine._detect_sweep(df_15m, df_1m)
            feats.update(sweep_results)
            print(f"[NEXUS5] {req.symbol}: SWEEP detection → {sweep_results.get('sweep_detected', False)}")

        # 2. Scores por grupo (0.0 a 1.0)
        g1 = self._score_g1(feats)
        g2 = self._score_g2(feats)
        g3 = self._score_g3(feats)
        g4 = self._score_g4(feats)
        g5 = self._score_g5(feats)

        # 3. XGBoost prediction (G6)
        feature_vector = [
            feats["compression_range"],
            float(feats["ignition_candle"]),
            feats["efficiency_check"],
            float(feats["displacement_fvg"]),
            float(feats["micro_choch"]),
            float(feats["instant_order_block"]),
            float(feats["compression_zone"]),
            float(feats["sos_detected"]),
            float(feats["jumping_creek"]),
            float(feats["fractal_high_break"]),
            feats["ema7_angle"],
            float(feats["hh_hl_sequence"]),
            feats["relative_vol_multiplier"],
            feats["vol_intensity"],
            feats["buying_imbalance"],
            feats["atr_expansion"],
            feats["z_score"],
            feats["rsi_velocity"],
        ]

        xgb_prob = self.model_loader.predict(feature_vector)
        g6 = xgb_prob if xgb_prob is not None else 0.5

        # [DEBUG]
        print(f"DEBUG NEXUS5 {req.symbol}: g1={g1:.3f} g2={g2:.3f} g3={g3:.3f} g4={g4:.3f} g5={g5:.3f} g6={g6:.3f}")

        # 4. Combined Score (0.0 = Max Bearish, 1.0 = Max Bullish)
        combined_raw = (
            g1 * GROUP_WEIGHTS["g1"] +
            g2 * GROUP_WEIGHTS["g2"] +
            g3 * GROUP_WEIGHTS["g3"] +
            g4 * GROUP_WEIGHTS["g4"] +
            g5 * GROUP_WEIGHTS["g5"] +
            g6 * GROUP_WEIGHTS["g6"]
        )

        # 5. Direction
        direction = self._determine_direction(feats, g6)

        # 6. Phase Detection
        phase, phase_score = self._detect_phase(feats, g5)

        # 7. RSI Bypass Check
        bypass_active = (
            feats["ignition_candle"] and
            feats["relative_vol_multiplier"] >= RSI_BYPASS_VOL_THRESHOLD
        )

        # 7b. Bottom Sniper Phase Override — if is_bottom_sniper and phase is IDLE,
        # force COMPRESSION so it is never filtered out by the C# IDLE check.
        # The score here reflects how close MA50 and MA99 are.
        _is_bs_check = feats.get("is_bottom_sniper", False)
        _ma50_ma99_dist_check = feats.get("ma50_ma99_dist", 1.0)
        if _is_bs_check and phase == "IDLE":
            phase = "COMPRESSION"
            # Score based on MA50/MA99 proximity: dist=0 → 100, dist=0.05 → 75
            phase_score = max(65.0, 100.0 - _ma50_ma99_dist_check * 500)

        # 8. AI Confidence — REGLAS DE ORO v8.0 (BOTTOM SNIPER)
        # ── REGLAS DE ORO ESTRUCTURALES (v8.0) ───────────────────────────────────
        # NEXUS-5 ahora es un BOTTOM SNIPER: detecta acumulación debajo de MA99

        # Obtener características estructurales (Bottom Sniper v9.0)
        slope_ma50 = feats.get("slope_ma50", 0.0)
        ma99_long_slope = feats.get("ma99_long_slope", 0.0)
        is_bottom_sniper = feats.get("is_bottom_sniper", False)
        gravity_ma99_safe = feats.get("gravity_ma99_safe", True)
        vol_ratio = feats.get("vol_ratio", 1.0)
        viper = feats.get("compression_viper", False)
        ma50_horiz = feats.get("ma50_horizontal", False)
        price_to_ma99 = feats.get("price_to_ma99_pct", 0.0)
        ma50_ma99_dist = feats.get("ma50_ma99_dist", 1.0)

        # 7b. Sweep Override — if sweep detected, bypass MA99 veto
        _is_sweep = feats.get("sweep_detected", False)

        # ── VETO #1: PRECIO POR ENCIMA DE MA99 = SCORE 0 ────────────────────────────────
        # Si precio >= MA99, ya llegamos tarde. Descartar inmediatamente.
        # EXCEPCIÓN: si price_to_ma99 < -900 es un sentinel (datos insuficientes), no vetar.
        # EXCEPCIÓN: si sweep_detected = True, el sweep opera con lógica independiente.
        if not _is_sweep and price_to_ma99 >= 0 and price_to_ma99 > -900:
            ai_confidence = 0.0
            direction = "NEUTRAL"
            recommendation = "Wait"
            return Nexus5Response(
                symbol=req.symbol,
                timeframe=req.timeframe,
                analyzed_at=datetime.now(timezone.utc).isoformat(),
                ai_confidence=ai_confidence,
                direction=direction,
                recommendation=recommendation,
                phase="IDLE",
                phase_score=0.0,
                entry_timeframe="5m",
                compression_state=False,
                ignition_detected=False,
                bypass_active=False,
                next_3_candles_prob=0.0,
                next_5_candles_prob=0.0,
                next_10_candles_prob=0.0,
                estimated_range_percent=0.0,
                regime="Ranging",
                volume_explosion=False,
                group_scores=GroupScores(
                    g1_price_action=round(g1 * 100, 2),
                    g2_smc_ict=round(g2 * 100, 2),
                    g3_wyckoff=round(g3 * 100, 2),
                    g4_fractals=round(g4 * 100, 2),
                    g5_volume=round(g5 * 100, 2),
                    g6_ml=round(g6 * 100, 2),
                ),
                features=Nexus5Features(**{k: feats.get(k, 0.0 if k in ["slope_ma50", "ma99_long_slope", "vol_ratio", "ma50_ma99_dist", "price_to_ma99_pct", "minutes_to_next_pump", "confidence_boost", "super_crash_pct", "sweep_depth_pct"] else False if k in ["gravity_ma99_safe", "compression_viper", "ma50_horizontal", "is_bottom_sniper", "cycle_detected", "crash_detected", "sweep_detected", "half_u_forming", "lateralization_1m", "mas_aligned_1m"] else "") for k in Nexus5Features.model_fields}),
                detectivity=self._build_detectivity(feats, g1, g2, g3, g4, g5, g6),
            )

        # ── SCORING SWEEP (v13.0) ─────────────────────────────────────────────────
        _is_sweep = feats.get("sweep_detected", False)
        _sweep_depth = feats.get("sweep_depth_pct", 0.0)

        # ── SCORING BOTTOM SNIPER (v11.0) ─────────────────────────────────────────
        # Lógica de Score para el TOP-5
        if _is_sweep:
            # SWEEP detectado — alta confianza, dirección BULLISH
            base_score = 92.0
            depth_bonus = min(5.0, _sweep_depth * 10)  # Más profundo = más confianza
            # Bonus por compresión activa (nice-to-have, no obligatorio)
            _has_compression = feats.get("sweep_15m_compression", False)
            compression_bonus = 3.0 if _has_compression else 0.0
            ai_confidence = base_score + depth_bonus + compression_bonus
            direction = "BULLISH"
            recommendation = "Long"
        elif is_bottom_sniper:
            # ES EL SETUP DE FIDA. Ignoramos todo lo demás.
            base_score = 95.0
            # Cuanto más cerca estén la MA50 y la MA99, más puntaje (compresión final)
            proximity_bonus = (1 - ma50_ma99_dist) * 5
            ai_confidence = base_score + proximity_bonus
            direction = "BULLISH"
            recommendation = "Long"  # Bottom Sniper = entrada directa
        else:
            # Si no es un Bottom Sniper ni Sweep, bajamos el score drásticamente
            # para que no ensucie el TOP 5 con pumps ya empezados.
            ai_confidence = combined_raw * 20
            direction = "NEUTRAL"
            recommendation = "Wait"

        ai_confidence = round(min(100.0, max(0.0, ai_confidence)), 1)

        # 9. Recommendation (solo sobreescribir si NO es Bottom Sniper ni Sweep)
        if not is_bottom_sniper and not _is_sweep:
            recommendation = "Wait"
            if ai_confidence >= STRONG_SIGNAL_THRESHOLD:
                if direction == "BULLISH":
                    recommendation = "Long"
                elif direction == "BEARISH":
                    recommendation = "Short"

        # 10. Entry Timeframe Logic
        entry_timeframe = self._determine_entry_timeframe(phase, phase_score, feats)

        # 11. Forward Probabilities
        base_prob = min(0.95, max(0.35, g6 if g6 else 0.5))
        atr_decay = max(0, 1 - feats.get("atr_expansion", 1.0) / 5.0)

        # 12. Estimated Range
        atr_current_pct = feats.get("atr_expansion", 1.0)
        estimated_range = round(max(1.0, atr_current_pct * 3.0), 2)

        # 13. Regime
        regime = self._determine_regime(feats)

        # 14. Volume explosion flag
        volume_explosion = feats["relative_vol_multiplier"] >= 2.0

        # 15. Compression state
        compression_state = feats["compression_zone"] or (feats["compression_range"] < 0.04)

        # 16. Ignition detected
        ignition_detected = feats["ignition_candle"] and (
            feats["sos_detected"] or feats["jumping_creek"] or feats["relative_vol_multiplier"] >= 2.5
        )

        return Nexus5Response(
            symbol=req.symbol,
            timeframe=req.timeframe,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=ai_confidence,
            direction=direction,
            recommendation=recommendation,
            phase=phase,
            phase_score=phase_score,
            entry_timeframe=entry_timeframe,
            compression_state=compression_state,
            ignition_detected=ignition_detected,
            bypass_active=bypass_active,
            next_3_candles_prob=round(base_prob, 4),
            next_5_candles_prob=round(base_prob * atr_decay * 0.92, 4),
            next_10_candles_prob=round(base_prob * atr_decay * 0.80, 4),
            estimated_range_percent=estimated_range,
            regime=regime,
            volume_explosion=volume_explosion,
            group_scores=GroupScores(
                g1_price_action=round(g1 * 100, 2),
                g2_smc_ict=round(g2 * 100, 2),
                g3_wyckoff=round(g3 * 100, 2),
                g4_fractals=round(g4 * 100, 2),
                g5_volume=round(g5 * 100, 2),
                g6_ml=round(g6 * 100, 2),
            ),
            features=Nexus5Features(**{k: feats.get(k, 0.0 if k in ["slope_ma50", "ma99_long_slope", "vol_ratio", "ma50_ma99_dist", "price_to_ma99_pct", "minutes_to_next_pump", "confidence_boost", "super_crash_pct", "sweep_depth_pct"] else False if k in ["gravity_ma99_safe", "compression_viper", "ma50_horizontal", "is_bottom_sniper", "cycle_detected", "crash_detected", "sweep_detected", "half_u_forming", "lateralization_1m", "mas_aligned_1m"] else "") for k in Nexus5Features.model_fields}),
            detectivity=self._build_detectivity(feats, g1, g2, g3, g4, g5, g6),
        )

    # ══════════════════════════════════════════════════════════════════════════
    # SCORING HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _score_g1(self, f) -> float:
        """G1: Price Action — Ruptura Sniper. Favorece ignición + eficiencia."""
        score = 0.3  # base neutral
        # Compression activa: bueno si se combina con ignición
        if f["compression_range"] < 0.04:
            score += 0.15
        elif f["compression_range"] < 0.06:
            score += 0.08

        # Ignición: el evento más importante de G1
        if f["ignition_candle"]:
            score += 0.35

        # Eficiencia temporal
        score += f["efficiency_check"] * 0.25

        return round(min(1.0, max(0.0, score)), 4)

    def _score_g2(self, f) -> float:
        """G2: SMC/ICT — Desplazamiento. Eventos binarios de alta calidad."""
        score = (
            float(f["displacement_fvg"]) * 0.35 +
            float(f["micro_choch"]) * 0.35 +
            float(f["instant_order_block"]) * 0.30
        )
        return round(min(1.0, max(0.0, score)), 4)

    def _score_g3(self, f) -> float:
        """G3: Wyckoff — Resorte. Compression + SOS + Jumping the Creek."""
        score = 0.3  # base
        if f["compression_zone"]:
            score += 0.20
        if f["sos_detected"]:
            score += 0.25
        if f["jumping_creek"]:
            score += 0.25  # el evento más fuerte — cruce con volumen
        return round(min(1.0, max(0.0, score)), 4)

    def _score_g4(self, f) -> float:
        """G4: Fractales & Micro-Tendencia."""
        score = 0.3
        if f["fractal_high_break"]:
            score += 0.25
        score += f["ema7_angle"] * 0.25
        if f["hh_hl_sequence"]:
            score += 0.20
        return round(min(1.0, max(0.0, score)), 4)

    def _score_g5(self, f) -> float:
        """G5: Volume & Order Flow — CORAZÓN de NEXUS-5. Peso 25%."""
        # Volume multiplier: el indicador más importante
        vol_mul = f["relative_vol_multiplier"]
        vol_score = min(vol_mul / 5.0, 1.0) * 0.40  # hasta 5x = 40% del score

        # Volume intensity (bots peleando)
        intensity_score = min(f["vol_intensity"] / 3.0, 1.0) * 0.25

        # Buying imbalance: >0.7 = bullish, <0.3 = bearish
        imbalance = f["buying_imbalance"]
        if imbalance > 0.7:
            imbalance_score = 0.35
        elif imbalance < 0.3:
            imbalance_score = 0.35  # bearish también es señal (SHORT)
        else:
            imbalance_score = 0.10  # neutral = bajo score

        score = vol_score + intensity_score + imbalance_score
        return round(min(1.0, max(0.0, score)), 4)

    # ══════════════════════════════════════════════════════════════════════════
    # DIRECTION — Soporta LONG y SHORT
    # ══════════════════════════════════════════════════════════════════════════

    def _determine_direction(self, f, xgb_prob) -> str:
        bullish_votes = 0
        bearish_votes = 0

        # G5: Volumen — VOTO FUERTE (es el corazón)
        if f["buying_imbalance"] > 0.7:
            bullish_votes += 2
        elif f["buying_imbalance"] < 0.3:
            bearish_votes += 2

        if f["relative_vol_multiplier"] > 2.0:
            # Volumen alto amplifica la dirección
            if f["buying_imbalance"] > 0.5:
                bullish_votes += 1
            else:
                bearish_votes += 1

        # G1: Ignition candle — dirección de la ruptura
        if f["ignition_candle"]:
            # Necesitamos saber si fue ruptura alcista o bajista
            # Si efficiency_check es alto y compression_range bajo → ruptura fuerte
            if f["efficiency_check"] > 0.5:
                bullish_votes += 1  # asumimos alcista; el Z-score nos dirá la dirección real

        # Z-Score: dirección del movimiento
        if f["z_score"] > 1.5:
            bullish_votes += 2
        elif f["z_score"] < -1.5:
            bearish_votes += 2

        # RSI Velocity: velocidad del RSI (no el nivel)
        if f["rsi_velocity"] > 0.3:
            bullish_votes += 1
        elif f["rsi_velocity"] < -0.3:
            bearish_votes += 1

        # G6: XGBoost
        if xgb_prob and xgb_prob > 0.60:
            bullish_votes += 2
        if xgb_prob and xgb_prob < 0.40:
            bearish_votes += 2

        # G2: SMC events
        if f["micro_choch"]:
            bullish_votes += 1
        if f["displacement_fvg"]:
            bullish_votes += 1

        # G3: Wyckoff
        if f["jumping_creek"]:
            bullish_votes += 1
        if f["sos_detected"] and not f["jumping_creek"]:
            # SOS sin jumping puede ser cualquiera — verificamos el Z-score
            if f["z_score"] > 0:
                bullish_votes += 1
            else:
                bearish_votes += 1

        # G4: Structure
        if f["fractal_high_break"] and f["z_score"] > 0:
            bullish_votes += 1
        if f["fractal_high_break"] and f["z_score"] < 0:
            bearish_votes += 1
        if f["hh_hl_sequence"]:
            bullish_votes += 1

        if bullish_votes > bearish_votes + 1:
            return "BULLISH"
        if bearish_votes > bullish_votes + 1:
            return "BEARISH"
        return "NEUTRAL"

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE DETECTION — El alma de NEXUS-5
    # ══════════════════════════════════════════════════════════════════════════

    def _detect_phase(self, f, g5_score) -> tuple:
        """
        Retorna (phase, phase_score):
        - COMPRESSION: resorte apretado, acercándose a ignición
        - IGNITION: acaba de romper (Fase 2 iniciada)
        - EXPANSION: ya rompió y está corriendo
        - IDLE: nada especial
        """
        compression_range = f["compression_range"]
        compression_zone = f["compression_zone"]
        ignition_candle = f["ignition_candle"]
        sos = f["sos_detected"]
        jumping = f["jumping_creek"]
        vol_mul = f["relative_vol_multiplier"]

        # ── IGNITION: El momento exacto de la ruptura ────────────────────────
        if ignition_candle and (sos or jumping or vol_mul >= 2.5):
            phase = "IGNITION"
            # Score basado en qué tan fuerte es la ignición
            score = 70.0
            if jumping:
                score += 15.0
            if vol_mul >= 3.0:
                score += 10.0
            if f["efficiency_check"] > 0.5:
                score += 5.0
            return phase, min(100.0, score)

        # ── COMPRESSION: Resorte apretado, monitorear ─────────────────────────
        if compression_zone or compression_range < 0.04:
            phase = "COMPRESSION"
            # Score basado en qué tan apretado está y qué tan cerca de romper
            score = 30.0
            if compression_range < 0.03:
                score += 20.0  # muy apretado
            elif compression_range < 0.04:
                score += 10.0

            # Señales pre-ignición suben el score
            if sos:
                score += 15.0
            if vol_mul > 1.5:
                score += 10.0
            if f["ema7_angle"] > 0.3:
                score += 5.0
            if g5_score > 0.5:
                score += 10.0

            return phase, min(100.0, score)

        # ── EXPANSION: Ya rompió, el movimiento está en curso ─────────────────
        if (sos or ignition_candle) and vol_mul >= 2.0:
            phase = "EXPANSION"
            score = 50.0
            if vol_mul >= 3.0:
                score += 15.0
            if f["atr_expansion"] > 1.5:
                score += 10.0
            return phase, min(100.0, score)

        # ── IDLE: Nada especial ───────────────────────────────────────────────
        return "IDLE", max(0.0, 20.0 - compression_range * 200)

    # ══════════════════════════════════════════════════════════════════════════
    # ENTRY TIMEFRAME LOGIC
    # ══════════════════════════════════════════════════════════════════════════

    def _determine_entry_timeframe(self, phase: str, phase_score: float, f: dict) -> str:
        """
        Recomendar timeframe de entrada basado en la fase:
        - IGNITION → 1m (entrar YA, en el segundo 30 de la ruptura)
        - COMPRESSION alta (>70) → 3m (prepararse, entrada inminente)
        - COMPRESSION baja (<70) → 5m (monitorear)
        - EXPANSION → 1m (si todavía hay oportunidad) o 3m
        - IDLE → 5m (no hay urgencia)
        """
        if phase == "IGNITION":
            return "1m"
        elif phase == "COMPRESSION":
            if phase_score > 70:
                return "3m"
            return "5m"
        elif phase == "EXPANSION":
            if f.get("relative_vol_multiplier", 0) >= 3.0:
                return "1m"
            return "3m"
        else:
            return "5m"

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _determine_regime(self, f: dict) -> str:
        if f["z_score"] > 1.0 and f["ema7_angle"] > 0.3:
            return "BullTrend"
        elif f["z_score"] < -1.0 and f["ema7_angle"] > 0.3:
            return "BearTrend"
        return "Ranging"

    def _build_detectivity(self, f, g1, g2, g3, g4, g5, g6) -> dict:
        detectivity = {
            "g1_price_action": (
                f"Compresión: {f['compression_range']*100:.1f}% | "
                f"Ignición: {'✅' if f['ignition_candle'] else '❌'} | "
                f"Eficiencia: {f['efficiency_check']:.0%}"
            ),
            "g2_smc_ict": (
                f"FVG Desplaz: {'✅' if f['displacement_fvg'] else '❌'} | "
                f"Micro-CHoCH: {'✅' if f['micro_choch'] else '❌'} | "
                f"OB Instant: {'✅' if f['instant_order_block'] else '❌'}"
            ),
            "g3_wyckoff": (
                f"Comp Zone: {'✅' if f['compression_zone'] else '❌'} | "
                f"SOS: {'✅' if f['sos_detected'] else '❌'} | "
                f"Jump Creek: {'✅' if f['jumping_creek'] else '❌'}"
            ),
            "g4_fractals": (
                f"Fractal Break: {'✅' if f['fractal_high_break'] else '❌'} | "
                f"EMA7 Angle: {f['ema7_angle']:.0%} | "
                f"HH/HL Seq: {'✅' if f['hh_hl_sequence'] else '❌'}"
            ),
            "g5_volume": (
                f"Vol Mult: {f['relative_vol_multiplier']:.2f}x | "
                f"Vol Intens: {f['vol_intensity']:.2f}x | "
                f"Buy Imbalance: {f['buying_imbalance']:.0%}"
            ),
            "g6_ml": (
                f"ATR Expand: {f['atr_expansion']:.2f}x | "
                f"Z-Score: {f['z_score']:+.2f} | "
                f"RSI Velocity: {f['rsi_velocity']:+.2f}"
            ),
        }
        
        # Agregar información del ciclo si está detectado
        if f.get("cycle_detected", False):
            minutes_to_next = f.get("minutes_to_next_pump", 0)
            detectivity["cycle_clock"] = (
                f"🕐 CLOCK SYNC: ACTIVE | "
                f"Próximo Pump en: {minutes_to_next:.0f} min | "
                f"Boost: +{f.get('confidence_boost', 0)*100:.0f}%"
            )
        else:
            detectivity["cycle_clock"] = "🕐 CLOCK SYNC: INACTIVE (sin patrón 24h detectado)"

        # ── ESTRUCTURAL ANALYSIS — Reglas de Oro (v7.0) ───────────────────────────
        slope_ma50 = f.get("slope_ma50", 0.0)
        slope_ma99 = f.get("ma99_long_slope", 0.0)  # campo correcto
        gravity_safe = f.get("gravity_ma99_safe", True)
        vol_ratio = f.get("vol_ratio", 1.0)
        viper = f.get("compression_viper", False)
        ma50_horiz = f.get("ma50_horizontal", False)

        # Formatear pendientes como porcentaje
        slope_ma50_pct = slope_ma50 * 100
        slope_ma99_pct = slope_ma99 * 100

        detectivity["structural_ma50"] = (
            f"📊 MA50 Slope: {slope_ma50_pct:+.2f}% | "
            f"Horizontal: {'✅' if ma50_horiz else '❌'}"
        )
        detectivity["structural_ma99"] = (
            f"📊 MA99 Slope: {slope_ma99_pct:+.2f}% | "
            f"Gravity Safe: {'✅' if gravity_safe else '❌ DANGER'}"
        )
        detectivity["structural_volume"] = (
            f"⛽ Vol Ratio: {vol_ratio:.2f}x | "
            f"Gasolina: {'✅' if vol_ratio >= 2.5 else '❌'}"
        )
        detectivity["structural_viper"] = (
            f"🐍 Víbora Compresión: {'✅' if viper else '❌'}"
        )

        # Resumen de las 4 Reglas de Oro
        structural_score = 0
        if ma50_horiz:
            structural_score += 40
        if viper:
            structural_score += 30
        if vol_ratio >= 2.5:
            structural_score += 15
        if not gravity_safe:
            structural_score = 0  # Veto absoluto

        # Info del crash (v11.0)
        super_crash_pct = f.get("super_crash_pct", 0.0)
        crash_detected = f.get("crash_detected", False)

        detectivity["structural_crash"] = (
            f"💥 SUPER CAÍDA: {super_crash_pct*100:.1f}% | "
            f"Detectada: {'✅' if crash_detected else '❌'}"
        )

        detectivity["structural_summary"] = (
            f"🏆 Estructural Score: {structural_score}/85 | "
            f"Reglas Activas: {sum([ma50_horiz, viper, vol_ratio >= 2.5, gravity_safe])}/4"
        )

        # ── SWEEP DETECTOR (v13.0) ────────────────────────────────────────────
        sweep_detected = f.get("sweep_detected", False)
        sweep_depth = f.get("sweep_depth_pct", 0.0)
        half_u = f.get("half_u_forming", False)
        lat_1m = f.get("lateralization_1m", False)
        mas_1m = f.get("mas_aligned_1m", False)

        detectivity["sweep_status"] = (
            f"🧹 SWEEP: {'✅ DETECTED' if sweep_detected else '❌'} | "
            f"Depth: {sweep_depth:.2f}% | "
            f"Half-U: {'✅' if half_u else '❌'}"
        )
        detectivity["sweep_1m"] = (
            f"📊 1m Lat: {'✅' if lat_1m else '❌'} | "
            f"MAs Flat: {'✅' if mas_1m else '❌'}"
        )

        return detectivity
