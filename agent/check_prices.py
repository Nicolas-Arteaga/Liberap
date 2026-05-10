
import sqlite3
import time
import os

DB_PATH = "agent/data/klines.db"

def check():
    if not os.path.exists(DB_PATH):
        print("DB not found")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    symbol = "ICPUSDT"
    row = conn.execute("SELECT * FROM live_prices WHERE symbol = ?", (symbol,)).fetchone()
    
    if row:
        age = time.time() - row["updated_at"]
        print(f"Symbol: {row['symbol']}")
        print(f"Price: {row['close']}")
        print(f"Source: {row['source']}")
        print(f"Age: {age:.1f}s")
        print(f"Update time: {row['updated_at']}")
    else:
        print(f"Symbol {symbol} not found in live_prices")
    
    conn.close()

if __name__ == "__main__":
    check()
