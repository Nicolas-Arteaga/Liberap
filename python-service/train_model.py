import ccxt
import pandas as pd
import time
import os
from datetime import datetime, timedelta

def download_historical_data(symbol="BTC/USDT", timeframe="1h", limit=1000):
    """
    Downloads historical data from Binance for training.
    """
    exchange = ccxt.binance()
    print(f"📡 Downloading {limit} candles for {symbol} ({timeframe})...")
    
    since = exchange.parse8601((datetime.now() - timedelta(days=180)).isoformat())
    all_ohlcv = []
    
    while len(all_ohlcv) < limit:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + exchange.parse_timeframe(timeframe) * 1000
        time.sleep(exchange.rateLimit / 1000)
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def label_data(df, threshold=0.005): # X = 0.5%
    """
    Labels data for XGBoost: 
    1 if price increases by more than 0.5% in the next hour.
    0 otherwise.
    """
    # Look ahead 1 candle (assuming 1h timeframe)
    df['next_close'] = df['close'].shift(-1)
    df['price_change'] = (df['next_close'] - df['close']) / df['close']
    
    # Label: 1 if change > threshold, else 0
    df['label'] = df['price_change'].apply(lambda x: 1 if x > threshold else 0)
    
    # Remove last row (no next_close)
    return df.dropna()

def extract_features(df):
    """
    Basic Feature Engineering for the MVP.
    """
    import ta
    
    # Returns
    df['returns'] = df['close'].pct_change()
    
    # Technical Indicators
    df['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
    macd = ta.trend.MACD(df['close'])
    df['macd_diff'] = macd.macd_diff()
    df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close']).adx()
    
    # NEW: Volatility and Momentum
    df['roc'] = ta.momentum.ROCIndicator(df['close'], window=12).roc()
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['volatility'] = df['close'].rolling(window=24).std() / df['close'] # Normalizado
    
    # Volume Relative to Moving Average
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma']
    
    return df.dropna()

if __name__ == "__main__":
    # Example Workflow
    symbol = "BTC/USDT"
    data = download_historical_data(symbol, limit=5000)
    data = extract_features(data)
    data = label_data(data)
    
    save_path = f"historical_{symbol.replace('/', '_')}.csv"
    data.to_csv(save_path, index=False)
    print(f"✅ Data saved to {save_path}. Ready for XGBoost training!")
