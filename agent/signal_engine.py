import requests
import logging
import config
from typing import Dict, Any, Optional

logger = logging.getLogger("SignalEngine")

class SignalEngine:
    """
    Connects to the VERGE Python Service (Nexus-15 & SCAR).
    Calculates the Confluence Score based on both AI modules.
    """
    def __init__(self, binance_fetcher):
        self.base_url = config.PYTHON_SERVICE_URL
        self.fetcher = binance_fetcher

    def get_scar_alerts(self) -> dict:
        """
        Fetches active SCAR alerts directly from the Python service.
        Note: We use the cached alerts from DB via GET /scar/alerts to avoid 
        spamming Binance on every loop, since SCAR events develop over hours/days.
        """
        url = f"{self.base_url}/scar/alerts"
        try:
            response = requests.get(url, params={"threshold": 0}, timeout=5)
            if response.status_code == 200:
                alerts = response.json()
                # Return dictionary for O(1) lookups: { "BTCUSDT": scar_data }
                return {a["symbol"]: a for a in alerts}
        except Exception as e:
            logger.error(f"Error fetching SCAR alerts: {e}")
        return {}

    def get_nexus15_prediction(self, symbol: str, limit: int = 300) -> Optional[Dict[str, Any]]:
        """
        Fetches the Nexus-15 prediction for a symbol.
        Sends 15m candles (from SQLite cache, already in correct format) to the AI service.
        Returns None silently on ANY error — never crashes the agent cycle.
        """
        klines = self.fetcher.get_klines_for_nexus(symbol, limit=limit)
        if not klines or len(klines) < 25:
            logger.warning(f"Not enough klines to analyze {symbol} with Nexus-15 ({len(klines) if klines else 0} candles).")
            return None

        url = f"{self.base_url}/nexus15/analyze"
        payload = {
            "symbol": symbol,
            "timeframe": "15m",
            "candles": klines  # Already has 'timestamp' field from KlineCache.get_klines()
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"[Nexus-15] {symbol}: confidence={data.get('ai_confidence')}% dir={data.get('direction')}")
                return data
            else:
                logger.error(f"[Nexus-15] {symbol} HTTP {response.status_code}: {response.text[:200]}")
        except requests.exceptions.Timeout:
            logger.warning(f"[Nexus-15] Timeout for {symbol} (>15s). Skipping.")
        except requests.exceptions.ConnectionError:
            logger.warning(f"[Nexus-15] AI service unreachable at {self.base_url}. Is Docker running?")
        except Exception as e:
            logger.error(f"[Nexus-15] Unexpected error for {symbol}: {e}")

        return None


    def get_nexus5_prediction(self, symbol: str, limit: int = 500) -> Optional[Dict[str, Any]]:
        """
        Fetches the NEXUS-5 prediction for a symbol (5m candles, Phase 1/2 detection).
        Returns None silently on ANY error — never crashes the agent cycle.
        """
        klines = self.fetcher.get_klines_for_nexus(symbol, interval="5m", limit=limit)
        if not klines or len(klines) < 30:
            return None

        url = f"{self.base_url}/nexus5/analyze"
        payload = {
            "symbol": symbol,
            "timeframe": "5m",
            "candles": klines
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.debug(
                    f"[Nexus-5] {symbol}: phase={data.get('phase')} "
                    f"conf={data.get('ai_confidence')}% dir={data.get('direction')}"
                )
                return data
            else:
                logger.debug(f"[Nexus-5] {symbol} HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            logger.warning(f"[Nexus-5] Timeout for {symbol} (>10s). Skipping.")
        except requests.exceptions.ConnectionError:
            logger.warning(f"[Nexus-5] AI service unreachable at {self.base_url}. Is Docker running?")
        except Exception as e:
            logger.error(f"[Nexus-5] Unexpected error for {symbol}: {e}")

        return None


    @staticmethod
    def evaluate_nexus5_timing(n5_data: dict, n15_direction: str) -> dict:
        """
        Evaluates NEXUS-5 timing for entry decisions.

        Sweet spot (25-65%): The spring is loaded but hasn't fired. Boost confluence.
        Confirmed (65-80%): Window closing, small boost.
        Too late (>80%): Move already happened. Consider reversal (exhaustion top/bottom).

        Returns: {nexus5_ok, nexus5_boost, nexus5_timing_note, nexus5_reversal}
        """
        if not n5_data:
            return {
                "nexus5_ok": True, "nexus5_boost": 0,
                "nexus5_timing_note": "no_data", "nexus5_reversal": False,
                "nexus5_phase": None, "nexus5_confidence": 0,
            }

        phase = n5_data.get("phase", "IDLE")
        conf = n5_data.get("ai_confidence", 0)
        n5_dir = n5_data.get("direction", "NEUTRAL")
        phase_score = n5_data.get("phase_score", 0)

        base = {
            "nexus5_ok": True, "nexus5_boost": 0,
            "nexus5_reversal": False,
            "nexus5_phase": phase, "nexus5_confidence": conf,
        }

        # Phase IDLE: no timing signal, neutral
        if phase == "IDLE":
            return {**base, "nexus5_timing_note": "idle"}

        # Minimum phase score threshold
        if phase_score < config.NEXUS5_MIN_PHASE_SCORE:
            return {**base, "nexus5_timing_note": f"low_phase_score({phase_score:.0f})"}

        # SWEET SPOT: compression or early ignition (25-65%)
        if config.NEXUS5_SWEET_SPOT_MIN <= conf <= config.NEXUS5_SWEET_SPOT_MAX:
            boost = config.NEXUS5_CONFLUENCE_BOOST * (1.0 - conf / config.NEXUS5_SWEET_SPOT_MAX)
            return {**base, "nexus5_boost": boost, "nexus5_timing_note": f"sweet_spot({phase},{conf:.0f}%)"}

        # CONFIRMED: ignition confirmed, window closing (65-80%)
        if config.NEXUS5_SWEET_SPOT_MAX < conf <= config.NEXUS5_LATE_ENTRY_MAX:
            return {**base, "nexus5_boost": 3.0, "nexus5_timing_note": f"confirmed({phase},{conf:.0f}%)"}

        # TOO LATE: > 80%, consider reversal
        if conf > config.NEXUS5_REVERSAL_MIN:
            return {**base, "nexus5_timing_note": f"too_late({phase},{conf:.0f}%)", "nexus5_reversal": True}

        # Below minimum
        return {**base, "nexus5_timing_note": f"below_min({conf:.0f}%)"}


    def calculate_confluence(self, symbol: str, scar_data: dict, nexus_data: dict, nexus5_data: dict = None) -> dict:
        """
        Full confluence score using ALL available signals:
          - Nexus-15 AI confidence          (max 40 pts)
          - Nexus-15 group scores avg       (max 20 pts)  ← NEW: uses all 6 groups
          - SCAR whale signal               (max 20 pts)
          - Regime alignment                (±5 pts)      ← NEW
          - Volume explosion bonus          (+5 pts)      ← NEW
          - RSI overbought/oversold penalty (-5 pts)      ← NEW
          - SCAR + Nexus alignment bonus    (+10 pts)
        Total max: 100 pts | Entry threshold: MIN_CONFLUENCE_SCORE (35)
        """
        score   = 0.0
        reasons = []

        # ── Extract Nexus-15 fields ──────────────────────────────
        nexus_confidence  = nexus_data.get("ai_confidence",        0)       if nexus_data else 0
        nexus_direction   = nexus_data.get("direction",     "NEUTRAL")      if nexus_data else "NEUTRAL"
        regime            = nexus_data.get("regime",         "Ranging")     if nexus_data else "Ranging"
        volume_explosion  = nexus_data.get("volume_explosion",    False)    if nexus_data else False
        group_scores      = nexus_data.get("group_scores",           {})    if nexus_data else {}
        features          = nexus_data.get("features",               {})    if nexus_data else {}
        est_range         = nexus_data.get("estimated_range_percent", 2.0)  if nexus_data else 2.0
        # ── Timestamps para VETO #4 (stale_nexus_signal) ────────────────
        # scored_at: momento exacto en que calculate_confluence corre para este símbolo.
        # price_at_signal: last_close de la última vela en el kline — precio que vio Nexus.
        import time as _time
        scored_at_ts     = _time.time()
        last_close_kline = float(features.get("last_close", 0) or 0)

        # ── SCAR ────────────────────────────────────────────────
        scar_score = scar_data.get("score_grial", 0) if scar_data else 0


        # 1. Nexus AI Confidence → max 40 pts
        nexus_pts = nexus_confidence * 0.4
        score    += nexus_pts
        reasons.append(f"Nexus={nexus_confidence:.1f}%→+{nexus_pts:.1f}")

        # 2. Group Scores average → max 20 pts
        #    Uses all 6 Nexus-15 analytical groups exactly as the dashboard shows
        if group_scores:
            g_vals = [
                group_scores.get("g1_price_action", 0),   # Price Action & Velas
                group_scores.get("g2_smc_ict",      0),   # SMC/ICT Institutional
                group_scores.get("g3_wyckoff",      0),   # Wyckoff Intraday
                group_scores.get("g4_fractals",     0),   # Fractals & Structure
                group_scores.get("g5_volume",       0),   # Volume Profile & Order Flow
                group_scores.get("g6_ml",           0),   # ML Features
            ]
            active = [g for g in g_vals if g > 0]
            if active:
                avg_group  = sum(active) / len(active)
                group_pts  = avg_group * 0.20   # 100% avg → 20 pts
                score     += group_pts
                reasons.append(
                    f"Groups(PA={g_vals[0]:.0f}%,SMC={g_vals[1]:.0f}%,"
                    f"Wyck={g_vals[2]:.0f}%,Frac={g_vals[3]:.0f}%,"
                    f"Vol={g_vals[4]:.0f}%,ML={g_vals[5]:.0f}%)→+{group_pts:.1f}"
                )

        # 3. SCAR Whale Signal → max 20 pts
        if scar_score > 0:
            scar_pts  = scar_score * 4
            score    += scar_pts
            reasons.append(f"SCAR={scar_score}/5→+{scar_pts:.1f}")

        # 4. Regime alignment → ±5 pts
        if nexus_direction == "BULLISH":
            if regime in ("BullTrend",):
                score += 5
                reasons.append("BullTrend+BULLISH→+5")
            elif regime == "BearTrend":
                score -= 5
                reasons.append("BearTrend vs BULLISH→-5")
        elif nexus_direction == "BEARISH":
            if regime == "BearTrend":
                score += 5
                reasons.append("BearTrend+BEARISH→+5")
            elif regime == "BullTrend":
                score -= 5
                reasons.append("BullTrend vs BEARISH→-5")

        # 5. Volume Explosion bonus → +5 pts
        if volume_explosion:
            score += 5
            reasons.append("VolumeExplosion→+5")

        # 6. RSI filter → -5 pts if entering against extremes
        rsi = features.get("rsi_14", 50)
        if nexus_direction == "BULLISH" and rsi > 75:
            score -= 5
            reasons.append(f"OverboughtRSI={rsi:.0f}→-5")
        elif nexus_direction == "BEARISH" and rsi < 25:
            score -= 5
            reasons.append(f"OversoldRSI={rsi:.0f}→-5")

        # 7. SCAR + Nexus alignment → +10 or ×0.5
        if scar_score >= config.MIN_SCAR_SCORE:
            if nexus_direction == "BULLISH":
                score += 10
                reasons.append("SCAR+Nexus aligned→+10")
            elif nexus_direction == "BEARISH":
                score *= 0.5
                reasons.append("SCAR bullish vs Nexus BEARISH→×0.5")

        # 8. Standalone Nexus trigger
        #    High-confidence Nexus signal guarantees minimum threshold even without SCAR
        if nexus_confidence >= config.MIN_NEXUS_CONFIDENCE and score < config.MIN_CONFLUENCE_SCORE:
            score = config.MIN_CONFLUENCE_SCORE
            reasons.append(f"StandaloneNexus≥{config.MIN_NEXUS_CONFIDENCE}%→floor={config.MIN_CONFLUENCE_SCORE}")

        # 9. NEXUS-5 Timing Filter — determines WHEN to enter
        #    Sweet spot (25-65%): boost score. Too late (>80%): consider reversal.
        n5_timing = self.evaluate_nexus5_timing(nexus5_data, nexus_direction)
        n5_boost = n5_timing.get("nexus5_boost", 0)
        n5_reversal = n5_timing.get("nexus5_reversal", False)
        n5_note = n5_timing.get("nexus5_timing_note", "no_data")

        if n5_boost > 0:
            score += n5_boost
            reasons.append(f"Nexus5({n5_note})→+{n5_boost:.1f}")

        score = round(min(100.0, max(0.0, score)), 2)

        # Determine trade direction
        trade_direction = nexus_direction
        if trade_direction == "NEUTRAL" and scar_score >= config.MIN_SCAR_SCORE:
            trade_direction = "BULLISH"  # SCAR default bias (whales pump)

        # NEXUS-5 Reversal: if confidence > 80%, the move already happened.
        # Consider entering in the OPPOSITE direction (exhaustion top/bottom).
        if n5_reversal and trade_direction != "NEUTRAL":
            n5_conf = n5_timing.get("nexus5_confidence", 0)
            n5_dir = (nexus5_data or {}).get("direction", "NEUTRAL")
            reversed_dir = "BEARISH" if n5_dir == "BULLISH" else "BULLISH" if n5_dir == "BEARISH" else trade_direction
            if reversed_dir != trade_direction:
                trade_direction = reversed_dir
                reasons.append(f"Nexus5REVERSAL({n5_dir}@{n5_conf:.0f}%)→{reversed_dir}")
                logger.info(
                    f"[Nexus5-REVERSAL] {symbol}: {n5_dir} @ {n5_conf:.0f}% = too late, "
                    f"flipping to {reversed_dir} (exhaustion entry)"
                )

        side = 0 if trade_direction == "BULLISH" else 1

        logger.info(
            f"[{symbol}] Score={score} Dir={trade_direction} | {' | '.join(reasons)}"
        )

        return {
            "symbol":            symbol,
            "confluence_score":  score,
            "trade_direction":   trade_direction,
            "side":              side,
            "source":            "nexus",
            "scar_score":        scar_score,
            "nexus_confidence":  nexus_confidence,
            "nexus_direction":   nexus_direction,
            "regime":            regime,
            "volume_explosion":  volume_explosion,
            "group_scores":      group_scores,
            "rsi":               rsi,
            "distance_to_ma7_pct": features.get("distance_to_ma7_pct", 0),
            "estimated_range_pct": est_range,
            "reasons":           reasons,
            # VETO #4 staleness data — inyectado en el momento del cálculo
            "scored_at":         scored_at_ts,
            "scored_at_age_s":   0.0,  # se actualiza en verge_agent al ejecutar
            "price_at_signal":   last_close_kline,
            # NEXUS-5 Timing data
            "nexus5_phase":       n5_timing.get("nexus5_phase"),
            "nexus5_confidence":  n5_timing.get("nexus5_confidence", 0),
            "nexus5_timing_note": n5_note,
            "nexus5_boost":       n5_boost,
            "nexus5_reversal":    n5_reversal,
        }

