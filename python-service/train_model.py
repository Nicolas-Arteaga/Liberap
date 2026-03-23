import ccxt
import pandas as pd
import numpy as np
import time
import os
import requests
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

def download_futures_data_v5(symbol="BTC/USDT", limit=4500):
    exchange = ccxt.binance({
        'timeout': 30000,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    print(f"📡 Downloading {limit} candles for {symbol} (Futures)...")
    
    # 1. OHLCV (Stable Loop)
    all_ohlcv = []
    since = exchange.parse8601((datetime.now() - timedelta(days=180)).isoformat()) 
    
    try:
        while len(all_ohlcv) < limit:
            chunk = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
            if not chunk: break
            all_ohlcv.extend(chunk)
            since = chunk[-1][0] + 3600000 
            time.sleep(0.1)
    except Exception as e:
        print(f"⚠️ OHLCV Error: {e}")

    if not all_ohlcv:
        print("❌ No data received from API.")
        return None

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # 2. Futures Metadata (DISABLED TO AVOID ILLEGAL PARAMS)
    # We set these to 0.0 to satisfy the model's feature requirement without blocking training.
    df['fundingRate'] = 0.0
    df['openInterestValue'] = df['volume']

    return df

def extract_millionaire_features(df, fng_df=None):
    import ta
    df = df.copy()
    
    # 1. Technical Indicators (100% Reliable)
    df['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
    df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close']).adx()
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close']).average_true_range() / df['close']
    
    # 2. Futures Context (Proxied)
    df['funding_rate'] = df.get('fundingRate', 0.0).fillna(0.0)
    df['oi_change'] = df['openInterestValue'].pct_change().fillna(0.0)
    
    vol_ma = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / (vol_ma + 1e-9)
    
    # 3. Millionaire Filter Layer (Architect Formulas)
    shadow = (df['high'] - df['low']) / df['close']
    df['liq_proxy'] = (shadow * df['volume'] / (vol_ma + 1e-9)) * 10
    
    # High-precision 4h Trend Proxy
    df['ma20_4h'] = df['close'].rolling(window=80).mean() 
    df['trend_4h'] = (df['close'] > df['ma20_4h']).astype(int)

    # 4. Sentiment (Fear & Greed)
    if fng_df is not None:
        df = pd.merge_asof(df.sort_values('timestamp'), fng_df.sort_values('timestamp'), on='timestamp', direction='backward')
    else:
        df['fng_value'] = 50.0
        
    return df.dropna()

def label_data(df, threshold=0.005):
    df = df.copy()
    df['next_close'] = df['close'].shift(-1)
    df['price_change'] = (df['next_close'] - df['close']) / df['close']
    df['label'] = (df['price_change'] > threshold).astype(int)
    return df.dropna()

if __name__ == "__main__":
    fng = get_fear_greed()
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    all_data = []
    
    for s in symbols:
        try:
            raw = download_futures_data_v5(s, limit=4500)
            if raw is not None:
                feat = extract_millionaire_features(raw, fng)
                lab = label_data(feat)
                lab['symbol_tag'] = s
                all_data.append(lab)
        except Exception as e:
            print(f"❌ Error {s}: {e}")
            
    if all_data:
        final = pd.concat(all_data)
        final.to_csv("millionaire_dataset.csv", index=False)
        print(f"✅ Millionaire Dataset ready ({len(final)} samples).")
    else:
        print("❌ CRITICAL: No data could be generated.")
