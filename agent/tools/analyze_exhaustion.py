import psycopg2
import json
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5433'),
        dbname=os.getenv('DB_NAME', 'Verge'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASS', 'postgres')
    )

def main():
    print("Iniciando análisis de trades para detectar patrones de agotamiento...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Error conectando a la DB: {e}")
        return
    
    cur.execute("""
        SELECT "Symbol", "Status", "AgentDecisionJson", "OpenedAt", "ClosedAt", "EntryPrice", "ClosePrice"
        FROM "SimulatedTrades"
        WHERE "AgentDecisionJson" IS NOT NULL
          AND ("Status" = 1 OR "Status" = 2 OR "Status" = 3)
    """)
    
    rows = cur.fetchall()
    
    wins = []
    losses = []
    
    for row in rows:
        symbol, status, agent_json, opened_at, closed_at, entry_price_db, close_price = row
        try:
            data = json.loads(agent_json)
        except Exception:
            continue
            
        candidate = data.get("candidate", {})
        conf_score = candidate.get("confluence_score", 0)
        
        # Umbral de score para el análisis (45 para obtener suficiente data)
        if conf_score < 45:
            continue
            
        metrics = extract_metrics(candidate, data)
        if not metrics:
            continue
            
        metrics["symbol"] = symbol
        metrics["duration_m"] = (closed_at - opened_at).total_seconds() / 60 if closed_at and opened_at else 0
        metrics["status"] = "WIN" if status == 1 else "LOSS"
        
        if metrics["status"] == "WIN":
            wins.append(metrics)
        else:
            losses.append(metrics)
            
    print(f"Total WIN trades (Score >= 45): {len(wins)}")
    print(f"Total LOSS trades (Score >= 45): {len(losses)}")
    
    if not wins and not losses:
        print("No se encontraron trades con datos de auditoría suficientes.")
        return

    # Helpers
    def avg(lst, key):
        vals = [d[key] for d in lst if d.get(key) is not None]
        return sum(vals)/len(vals) if vals else 0
        
    def pct_diff(w, l):
        return ((w - l) / l * 100) if l != 0 else 0

    print("\n=== 1. COMPARATIVA WIN vs LOSS ===")
    keys = ["upper_wick_ratio", "lower_wick_ratio", "body_ratio", "close_pos_in_range", 
            "dist_to_ma99", "volume_ratio", "atr_percent", "duration_m"]
            
    for k in keys:
        w_avg = avg(wins, k)
        l_avg = avg(losses, k)
        diff = pct_diff(w_avg, l_avg)
        print(f"{k.ljust(20)} | WIN: {w_avg:.3f} | LOSS: {l_avg:.3f} | DIFF: {diff:+.1f}%")

    def count_flag(lst, key):
        return sum(1 for d in lst if d.get(key))
        
    w_fvg = count_flag(wins, "fvg_detected") / len(wins) * 100 if wins else 0
    l_fvg = count_flag(losses, "fvg_detected") / len(losses) * 100 if losses else 0
    w_upthrust = count_flag(wins, "upthrust_flag") / len(wins) * 100 if wins else 0
    l_upthrust = count_flag(losses, "upthrust_flag") / len(losses) * 100 if losses else 0
    
    print(f"\nFVG Present (%)       | WIN: {w_fvg:.1f}% | LOSS: {l_fvg:.1f}%")
    print(f"Upthrust Present (%)  | WIN: {w_upthrust:.1f}% | LOSS: {l_upthrust:.1f}%")
    
    print("\n=== 2. PATRONES DE ENTRADA TARDIA (LOSS) ===")
    late_entries = [d for d in losses if d.get("upper_wick_ratio", 0) > 0.4 and d.get("close_pos_in_range", 1) < 0.6]
    print(f"Trades LOSS que tienen upper_wick > 0.4 y close_pos < 0.6: {len(late_entries)} de {len(losses)}")

    print("\n=== 3. CLUSTERING DE LOSS ===")
    exhaustion = [d for d in losses if d.get("upthrust_flag") or d.get("upper_wick_ratio", 0) > 0.5]
    weak_momentum = [d for d in losses if not d.get("upthrust_flag") and d.get("upper_wick_ratio", 0) <= 0.5 and d.get("volume_ratio", 0) < 1.5]
    print(f"A) Exhaustion Entries (Wick > 0.5 o Upthrust): {len(exhaustion)}")
    print(f"B) Weak Momentum (Low Vol & Normal Wicks): {len(weak_momentum)}")

    print("\n=== 4. OUTPUT FINAL: REGLAS PROPUESTAS ===")
    all_trades = wins + losses
        
    def rule_1(d):
        return d.get("upper_wick_ratio", 0) > 0.45 and d.get("close_pos_in_range", 1) < 0.55 and d.get("body_ratio", 1) < 0.6
        
    affected = [d for d in all_trades if rule_1(d)]
    affected_losses = [d for d in affected if d["status"] == "LOSS"]
    affected_wins = [d for d in affected if d["status"] == "WIN"]
    
    print("REGLA 1 (Exhaustion Wick):")
    print("IF confluence_score >= 75 AND upper_wick_ratio > 0.45 AND close_position_in_range < 0.55 AND body_ratio < 0.6 THEN WAIT")
    print(f"Trades afectados: {len(affected)} (De los cuales LOSS: {len(affected_losses)}, WIN: {len(affected_wins)})")
    if affected:
        winrate_saved = len(affected_losses) / len(affected) * 100
        print(f"Evita {winrate_saved:.1f}% de perdidas en estos setups.\n")

def extract_metrics(candidate, data):
    try:
        audit = candidate.get("agent_audit_context", {})
        nx15 = audit.get("nexus15", {})
        features = nx15.get("features", {})
        
        upper_wick = features.get("upper_wick_ratio", 0)
        lower_wick = features.get("lower_wick_ratio", 0)
        body = features.get("candle_body_ratio", 1)
        
        direction = nx15.get("direction", "BULLISH")
        
        if direction == "BULLISH":
            close_pos = 1.0 - upper_wick
        else:
            close_pos = lower_wick
            
        dist_to_ma99 = features.get("distance_to_ma99_pct", 0)
        
        return {
            "upper_wick_ratio": upper_wick,
            "lower_wick_ratio": lower_wick,
            "body_ratio": body,
            "close_pos_in_range": close_pos,
            "dist_to_ma99": dist_to_ma99,
            "volume_ratio": features.get("volume_ratio_20", 0),
            "vol_surge": features.get("volume_surge_bullish", False),
            "fvg_detected": features.get("fair_value_gap", False),
            "upthrust_flag": features.get("upthrust_detected", False),
            "atr_percent": features.get("atr_percent", 0),
        }
    except Exception as e:
        return None

if __name__ == "__main__":
    main()
