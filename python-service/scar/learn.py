"""
SCAR Feedback Loop — Learning Module
Records predictions, evaluates them after 7 days, and adjusts templates using EMA.
"""
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
import requests
from typing import List, Dict, Optional

from . import data_store

logger = logging.getLogger("SCAR_LEARN")

BINANCE_API = "https://api.binance.com"
COINGECKO_API = "https://api.coingecko.com/api/v3"

# Environment variables
SCAR_LEARNING_MODE = os.environ.get("SCAR_LEARNING_MODE", "false").lower() == "true"
SCAR_COOLDOWN_DAYS = int(os.environ.get("SCAR_COOLDOWN_DAYS", 10))

def record_prediction(symbol: str, score: int, price: float, estimated_hours: Optional[int] = None):
    """Fire-and-forget hook to record high-score predictions."""
    conn = data_store._get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO scar_predictions
                (token_symbol, alert_date, score_grial, price_at_alert, estimated_hours)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, now, score, price, estimated_hours))
        conn.commit()
        logger.info("📝 SCAR prediction recorded for %s (Score: %d, Price: %.4f)", symbol, score, price)
    except Exception as e:
        logger.error("❌ Failed to record SCAR prediction for %s: %s", symbol, e)
    finally:
        conn.close()


def _get_max_price_24h_binance(symbol: str, alert_date: datetime) -> Optional[float]:
    """Get the maximum high price in the 24 hours following the alert_date."""
    # Convert alert_date to milliseconds
    start_time = int(alert_date.timestamp() * 1000)
    end_time = int((alert_date + timedelta(hours=24)).timestamp() * 1000)
    
    try:
        r = requests.get(
            f"{BINANCE_API}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": "1h",
                "startTime": start_time,
                "endTime": end_time,
                "limit": 24
            },
            timeout=10
        )
        r.raise_for_status()
        klines = r.json()
        if not klines:
            return None
            
        highs = [float(k[2]) for k in klines]
        return max(highs)
    except Exception as e:
        logger.warning("Binance price check failed for %s: %s", symbol, e)
        return None


def _get_max_price_24h_coingecko(symbol: str, alert_date: datetime) -> Optional[float]:
    """Fallback to CoinGecko for max price if Binance fails (or pair is delisted)."""
    # Simple mapping for common symbols
    cg_id = symbol.lower().replace("usdt", "").replace("busd", "")
    start_time = int(alert_date.timestamp())
    end_time = int((alert_date + timedelta(hours=24)).timestamp())
    
    try:
        r = requests.get(
            f"{COINGECKO_API}/coins/{cg_id}/market_chart/range",
            params={
                "vs_currency": "usd",
                "from": start_time,
                "to": end_time
            },
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        prices = data.get("prices", [])
        if not prices:
            return None
            
        return max([p[1] for p in prices])
    except Exception as e:
        logger.warning("CoinGecko price check failed for %s: %s", symbol, e)
        return None


def _get_max_price_24h(symbol: str, alert_date: datetime) -> Optional[float]:
    price = _get_max_price_24h_binance(symbol, alert_date)
    if price is None:
        price = _get_max_price_24h_coingecko(symbol, alert_date)
    return price


def evaluate_predictions():
    """Batch job to evaluate pending predictions > 7 days old."""
    logger.info("🔄 Running SCAR prediction evaluation...")
    conn = data_store._get_conn()
    try:
        # Get pending predictions older than 7 days
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        rows = conn.execute("""
            SELECT * FROM scar_predictions 
            WHERE status = 'pending' AND alert_date <= ?
        """, (seven_days_ago,)).fetchall()
        
        for row in rows:
            pred_id = row["id"]
            symbol = row["token_symbol"]
            alert_date_str = row["alert_date"]
            price_at_alert = float(row["price_at_alert"])
            
            try:
                alert_date = datetime.fromisoformat(alert_date_str)
            except ValueError:
                # Handle legacy format or errors
                alert_date = datetime.strptime(alert_date_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                
            max_price_24h = _get_max_price_24h(symbol, alert_date)
            
            status = 'pending'
            pattern_detected = 0
            trader_roi_pct = 0.0
            
            if max_price_24h is not None and price_at_alert > 0:
                # Calculate ROI with slippage
                trader_roi_pct = ((max_price_24h - price_at_alert) / price_at_alert) * 0.85
                ratio = max_price_24h / price_at_alert
                
                if ratio >= 2.5: # +150%
                    status = 'hit_strong'
                    pattern_detected = 1
                elif ratio >= 2.0: # +100%
                    status = 'hit'
                    pattern_detected = 1
                else:
                    # Check if > 8 days (expired)
                    eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
                    if alert_date < eight_days_ago:
                        status = 'false_alarm'
            else:
                # No price data. Check if expired.
                eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
                if alert_date < eight_days_ago:
                    status = 'false_alarm' # or maybe 'ignored' / 'data_missing'
            
            if status != 'pending':
                now_str = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE scar_predictions 
                    SET status = ?, result_date = ?, max_price_24h = ?, pattern_detected = ?, trader_roi_pct = ?
                    WHERE id = ?
                """, (status, now_str, max_price_24h, pattern_detected, trader_roi_pct, pred_id))
                
                # If hit, set cooldown
                if pattern_detected == 1:
                    cooldown_date = (datetime.now(timezone.utc) + timedelta(days=SCAR_COOLDOWN_DAYS)).isoformat()
                    data_store.set_cooldown(symbol, cooldown_date)
                    logger.info("🧊 Set cooldown for %s until %s", symbol, cooldown_date)
                
                # Apply EMA adjustment
                _adjust_template(conn, symbol, status)
                
                # Update Accuracy
                _update_accuracy(conn, symbol, status, trader_roi_pct)
                
        conn.commit()
    except Exception as e:
        logger.error("❌ SCAR evaluation error: %s", e)
    finally:
        conn.close()


def _adjust_template(conn: sqlite3.Connection, symbol: str, status: str):
    template = data_store.get_template_or_default(symbol)
    total_cycles = template.get("total_cycles", 0)
    
    # Increase cycle count if it was a hit
    if status in ('hit', 'hit_strong'):
        total_cycles += 1
        
    if total_cycles < 3:
        logger.info("Not adjusting template for %s: only %d cycles (need 3)", symbol, total_cycles)
        # Just update the total_cycles if changed
        conn.execute("UPDATE scar_templates SET total_cycles = ? WHERE token_symbol = ?", (total_cycles, symbol))
        return
        
    old_avg = float(template.get("avg_withdrawal_days", 10.0))
    # We don't have the exact "actual_days" of withdrawal for this cycle in the prediction table directly,
    # so we'll just reinforce the current avg if hit, or decay it slightly if false alarm, or we could
    # query scar_daily_signals to count withdrawal flags.
    
    # For simplicity, if we don't have actual_days, we'll skip EMA or use a proxy.
    # In a full implementation, you'd calculate actual_days from scar_daily_signals.
    # We will simulate actual_days = old_avg for hit (meaning it was accurate),
    # or actual_days = old_avg + 3 for false alarm (meaning it took longer or didn't happen).
    
    actual_days = old_avg # placeholder
    if status == 'hit_strong':
        new_avg = 0.8 * actual_days + 0.2 * old_avg # Strongly trust
    elif status == 'hit':
        new_avg = 0.7 * actual_days + 0.3 * old_avg
    else: # false_alarm
        actual_days = old_avg + 3 # assume it needs more days
        new_avg = 0.9 * old_avg + 0.1 * actual_days
        
    if SCAR_LEARNING_MODE:
        conn.execute("""
            UPDATE scar_templates SET avg_withdrawal_days = ?, total_cycles = ? WHERE token_symbol = ?
        """, (new_avg, total_cycles, symbol))
        conn.execute("""
            INSERT INTO scar_template_adjustments (token_symbol, adjustment_date, old_avg_days, new_avg_days, reason, learning_mode)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (symbol, datetime.now(timezone.utc).isoformat(), old_avg, new_avg, status))
        logger.info("📈 Adjusted template for %s: %.1f -> %.1f", symbol, old_avg, new_avg)
    else:
        conn.execute("UPDATE scar_templates SET total_cycles = ? WHERE token_symbol = ?", (total_cycles, symbol))
        conn.execute("""
            INSERT INTO scar_template_adjustments (token_symbol, adjustment_date, old_avg_days, new_avg_days, reason, learning_mode)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (symbol, datetime.now(timezone.utc).isoformat(), old_avg, new_avg, status))
        logger.info("🧪 [Dry-Run] Would adjust template for %s: %.1f -> %.1f", symbol, old_avg, new_avg)


def _update_accuracy(conn: sqlite3.Connection, symbol: str, status: str, roi: float):
    # Upsert logic for accuracy
    row = conn.execute("SELECT * FROM scar_accuracy WHERE token_symbol = ?", (symbol,)).fetchone()
    
    hits = 1 if status in ('hit', 'hit_strong') else 0
    false_alarms = 1 if status == 'false_alarm' else 0
    
    if not row:
        total = 1
        system_hit_rate = (hits / total) * 100
        conn.execute("""
            INSERT INTO scar_accuracy (token_symbol, total_predictions, total_hits, total_false_alarms, system_hit_rate, avg_trader_roi, last_updated)
            VALUES (?, 1, ?, ?, ?, ?, ?)
        """, (symbol, hits, false_alarms, system_hit_rate, roi if hits else 0, datetime.now(timezone.utc).isoformat()))
    else:
        total = row["total_predictions"] + 1
        new_hits = row["total_hits"] + hits
        new_false = row["total_false_alarms"] + false_alarms
        system_hit_rate = (new_hits / total) * 100
        
        # Recalculate avg roi for hits only (simple running average approximation if we don't recalculate from all rows)
        avg_roi = row["avg_trader_roi"]
        if hits:
            avg_roi = ((avg_roi * row["total_hits"]) + roi) / new_hits if new_hits > 0 else 0
            
        conn.execute("""
            UPDATE scar_accuracy 
            SET total_predictions = ?, total_hits = ?, total_false_alarms = ?, system_hit_rate = ?, avg_trader_roi = ?, last_updated = ?
            WHERE token_symbol = ?
        """, (total, new_hits, new_false, system_hit_rate, avg_roi, datetime.now(timezone.utc).isoformat(), symbol))


def get_predictions(status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    conn = data_store._get_conn()
    try:
        query = "SELECT * FROM scar_predictions"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY alert_date DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_accuracy_metrics(symbol: Optional[str] = None) -> Dict:
    conn = data_store._get_conn()
    try:
        if symbol:
            row = conn.execute("SELECT * FROM scar_accuracy WHERE token_symbol = ?", (symbol,)).fetchone()
            return dict(row) if row else {}
        else:
            # Global metrics
            row = conn.execute("""
                SELECT 
                    SUM(total_predictions) as total_predictions,
                    SUM(total_hits) as total_hits,
                    SUM(total_false_alarms) as total_false_alarms,
                    AVG(avg_trader_roi) as avg_trader_roi
                FROM scar_accuracy
            """).fetchone()
            
            if not row or row["total_predictions"] is None:
                return {"total_predictions": 0, "total_hits": 0, "total_false_alarms": 0, "system_hit_rate": 0.0, "avg_trader_roi": 0.0}
            
            total = row["total_predictions"] or 0
            hits = row["total_hits"] or 0
            hit_rate = (hits / total * 100) if total > 0 else 0.0
            
            return {
                "token_symbol": None,
                "total_predictions": total,
                "total_hits": hits,
                "total_false_alarms": row["total_false_alarms"] or 0,
                "system_hit_rate": hit_rate,
                "avg_trader_roi": row["avg_trader_roi"] or 0.0,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
    finally:
        conn.close()


def get_adjustments(limit: int = 20) -> List[Dict]:
    conn = data_store._get_conn()
    try:
        rows = conn.execute("SELECT * FROM scar_template_adjustments ORDER BY adjustment_date DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
