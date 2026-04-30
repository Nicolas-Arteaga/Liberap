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
            response = requests.get(url, params={"threshold": config.MIN_SCAR_SCORE}, timeout=5)
            if response.status_code == 200:
                alerts = response.json()
                # Return dictionary for O(1) lookups: { "BTCUSDT": scar_data }
                return {a["symbol"]: a for a in alerts}
        except Exception as e:
            logger.error(f"Error fetching SCAR alerts: {e}")
        return {}

    def get_nexus15_prediction(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the Nexus-15 prediction for a symbol.
        Sends 15m candles (from SQLite cache, already in correct format) to the AI service.
        Returns None silently on ANY error — never crashes the agent cycle.
        """
        klines = self.fetcher.get_klines_for_nexus(symbol)
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


    def calculate_confluence(self, symbol: str, scar_data: dict, nexus_data: dict) -> dict:
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

        score = round(min(100.0, max(0.0, score)), 2)

        # Determine trade direction
        trade_direction = nexus_direction
        if trade_direction == "NEUTRAL" and scar_score >= config.MIN_SCAR_SCORE:
            trade_direction = "BULLISH"  # SCAR default bias (whales pump)

        side = 0 if trade_direction == "BULLISH" else 1

        logger.info(
            f"[{symbol}] Score={score} Dir={trade_direction} | {' | '.join(reasons)}"
        )

        return {
            "symbol":            symbol,
            "confluence_score":  score,
            "trade_direction":   trade_direction,
            "side":              side,
            "scar_score":        scar_score,
            "nexus_confidence":  nexus_confidence,
            "nexus_direction":   nexus_direction,
            "regime":            regime,
            "volume_explosion":  volume_explosion,
            "group_scores":      group_scores,
            "rsi":               rsi,
            "estimated_range_pct": est_range,
            "reasons":           reasons,
        }

