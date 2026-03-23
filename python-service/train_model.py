import ccxt
import pandas as pd
import numpy as np
import time
import os
import requests
import argparse
from datetime import datetime, timedelta

def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=200", timeout=10)
        data = r.json()['data']
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df['fng_value'] = df['value'].astype(float)
        return df[['timestamp', 'fng_value']]
    except:
        return None

def download_multi_tf_data(symbol="BTC/USDT", tf="1h", limit=5000):
    exchange = ccxt.binance({
        'timeout': 30000,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    print(f"📡 Downloading {limit} candles for {symbol} ({tf})...")
    
    # Range based on timeframe
    days_back = 180 if tf == "1h" else 60 if tf == "15m" else 30
    since = exchange.parse8601((datetime.now() - timedelta(days=days_back)).isoformat()) 
    
    all_ohlcv = []
    chunk_size = 1000
    ms_map = {"1h": 3600000, "15m": 900000, "5m": 300000}
    ms = ms_map.get(tf, 3600000)

    try:
        while len(all_ohlcv) < limit:
            chunk = exchange.fetch_ohlcv(symbol, tf, since=since, limit=chunk_size)
            if not chunk: break
            all_ohlcv.extend(chunk)
            since = chunk[-1][0] + ms
            time.sleep(0.1)
    except Exception as e:
        print(f"⚠️ API Error: {e}")

    if not all_ohlcv: return None

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Zero fallback for features
    df['funding_rate_val'] = 0.0
    df['oi_val'] = df['volume']
    
    return df

def extract_features_v2(df, tf, fng_df=None):
    import ta
    df = df.copy()
    
    # Adjust windows for fast/slow timeframes
    window_scale = 1 if tf == "1h" else 2 if tf == "15m" else 3
    
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range() / df['close']
    
    df['funding_rate'] = df.get('funding_rate_val', 0.0).fillna(0.0)
    df['oi_change'] = df['oi_val'].pct_change().fillna(0.0)
    
    # Short vs Long term volume
    vol_ma = df['volume'].rolling(20 * window_scale).mean()
    df['vol_ratio'] = df['volume'] / (vol_ma + 1e-9)
    
    shadow = (df['high'] - df['low']) / df['close']
    df['liq_proxy'] = (shadow * df['volume'] / (vol_ma + 1e-9)) * 10
    
    # Multi-TF Trend Filter
    trend_window = 80 if tf == "1h" else 40 # 40 candles of 15m = 10h context
    df['trend_4h'] = (df['close'] > df['close'].rolling(trend_window).mean()).astype(int)

    if fng_df is not None:
        df = pd.merge_asof(df.sort_values('timestamp'), fng_df.sort_values('timestamp'), on='timestamp', direction='backward')
    else:
        df['fng_value'] = 50.0
        
    return df.dropna()

def label_data_v2(df, tf):
    df = df.copy()
    # Scalping target: 0.2% in 15min. Swing target: 0.5% in 1h.
    target_pct = 0.005 if tf == "1h" else 0.003 if tf == "15m" else 0.002
    lookahead = 1 if tf == "1h" else 2 if tf == "15m" else 3 # Look ahead 1-3 bars
    
    df['next_close'] = df['close'].shift(-lookahead)
    df['price_change'] = (df['next_close'] - df['close']) / df['close']
    df['label'] = (df['price_change'] > target_pct).astype(int)
    return df.dropna()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tf", default="1h", choices=["5m", "15m", "1h"])
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    fng = get_fear_greed()
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    all_data = []
    
    for s in symbols:
        try:
            raw = download_multi_tf_data(s, args.tf, args.limit)
            if raw is not None:
                feat = extract_features_v2(raw, args.tf, fng)
                lab = label_data_v2(feat, args.tf)
                lab['symbol_tag'] = s
                all_data.append(lab)
        except Exception as e:
            print(f"❌ Error {s}: {e}")
            
    if all_data:
        final = pd.concat(all_data)
        out_file = f"dataset_{args.tf}.csv"
        final.to_csv(out_file, index=False)
        print(f"✅ Dataset {out_file} ready ({len(final)} samples).")
    else:
        print("❌ CRITICAL: No data generated.")
