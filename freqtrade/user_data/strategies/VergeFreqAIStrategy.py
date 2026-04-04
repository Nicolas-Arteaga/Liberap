"""
VergeFreqAIStrategy — Phase 1 Stub
====================================
FreqAI strategy using XGBoostRegressor for scalping on Binance Futures.

Architecture:
  • Features: RSI, MACD, Bollinger Bands, EMA cross, volume delta
  • FreqAI model: XGBoostRegressor (predict next-N-candle % change)
  • Filters: DI threshold, SVM outlier removal
  • Entry signal: &roi_1 target met + FreqAI prediction positive
  • Phase 2 (TODO): Inject Verge Super Score from Redis for confirmation
  • Phase 3 (TODO): Whale watcher signal from Verge .NET backend

Dependencies:
  pip install -r freqtrade/requirements-freqai.txt
  (XGBoost is included in the develop docker image)
"""

import logging
from datetime import datetime, timedelta
from functools import reduce
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import redis
import json
import os
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import CategoricalParameter, DecimalParameter, IntParameter, merge_informative_pair
from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)


class VergeFreqAIStrategy(IStrategy):
    """
    Verge FreqAI Scalping Strategy — Phase 1

    Uses XGBoostRegressor to predict short-term price direction
    on Binance Futures (USDT-margined) at 5m timeframe.
    """

    # ─── Strategy Metadata ────────────────────────────────────────────────────
    INTERFACE_VERSION = 3

    # Minimal ROI — let FreqAI handle most exits, but keep a safety net
    minimal_roi = {
        "0": 0.03,    # 3% profit target
        "60": 0.02,   # after 60 min: 2%
        "120": 0.01,  # after 120 min: 1%
        "240": 0,     # after 240 min: break even
    }

    # Stoploss
    stoploss = -0.02  # 2% hard stop

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True

    # Time in force
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True,
    }

    # Timeframe
    timeframe = "5m"
    informative_timeframes = ["15m", "1h"]

    # Can this strategy go short?
    can_short = True

    # FreqAI required
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # FreqAI config
    freqai_info: Dict = {}

    # ─── Hyperopt Parameters ──────────────────────────────────────────────────
    # Prediction threshold to enter long
    long_threshold = DecimalParameter(0.01, 0.05, default=0.02, space="buy", optimize=True)
    # Prediction threshold to enter short
    short_threshold = DecimalParameter(-0.05, -0.01, default=-0.02, space="sell", optimize=True)
    # RSI overbought/oversold
    rsi_buy = IntParameter(20, 45, default=35, space="buy", optimize=True)
    rsi_sell = IntParameter(55, 80, default=65, space="sell", optimize=True)

    # ─── Feature Engineering ──────────────────────────────────────────────────

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Build features that will be expanded across all informative timeframes
        and correlated pairs automatically by FreqAI.
        """

        # Momentum
        dataframe["%-rsi"] = ta.RSI(dataframe, timeperiod=period)

        # Trend
        dataframe["%-ema_fast"] = ta.EMA(dataframe, timeperiod=period)
        dataframe["%-ema_slow"] = ta.EMA(dataframe, timeperiod=period * 3)
        dataframe["%-ema_cross"] = (
            dataframe["%-ema_fast"] - dataframe["%-ema_slow"]
        ) / dataframe["close"]

        # Volatility
        bb_upper, bb_mid, bb_lower = ta.BBANDS(dataframe["close"], timeperiod=period)
        dataframe["%-bb_upper"] = bb_upper
        dataframe["%-bb_lower"] = bb_lower
        dataframe["%-bb_width"] = (bb_upper - bb_lower) / bb_mid
        dataframe["%-bb_percentage"] = (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)

        # Volume
        dataframe["%-volume_mean"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )

        # MACD
        macd, macdsignal, macdhist = ta.MACD(dataframe["close"])
        dataframe["%-macd"] = macd
        dataframe["%-macdsignal"] = macdsignal
        dataframe["%-macdhist"] = macdhist

        # Stochastic RSI
        fastk, fastd = ta.STOCHRSI(dataframe["close"], timeperiod=period)
        dataframe["%-stochrsi_k"] = fastk
        dataframe["%-stochrsi_d"] = fastd

        # Price relative to range
        dataframe["%-high_low_ratio"] = (
            dataframe["high"] - dataframe["low"]
        ) / dataframe["close"]

        # Candle body ratio
        dataframe["%-body_ratio"] = abs(
            dataframe["close"] - dataframe["open"]
        ) / (dataframe["high"] - dataframe["low"] + 1e-8)

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Features that are expanded across informative timeframes but NOT corr pairs.
        """
        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_price"] = dataframe["close"]
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Features that are added ONCE, not expanded.
        """
        # Time features
        dataframe["%-day_of_week"] = (dataframe["date"].dt.dayofweek) / 6
        dataframe["%-hour_of_day"] = (dataframe["date"].dt.hour) / 23

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define the regression target: % price change over the next N candles.
        FreqAI will train a model to predict this value.
        """
        # Target: percentage change over the next 24 candles (2h at 5m)
        dataframe["&-future_return"] = (
            dataframe["close"].shift(-24) - dataframe["close"]
        ) / dataframe["close"]
        return dataframe

    # ─── Indicators ───────────────────────────────────────────────────────────

    # ─── Initialization ───────────────────────────────────────────────────────

    def bot_start(self, **kwargs) -> None:
        """
        Called once when the bot starts. Initialize Redis connection.
        """
        redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            logger.info(f"VergeFreqAIStrategy: Connected to Redis at {redis_url}")
        except Exception as e:
            logger.error(f"VergeFreqAIStrategy: Could not connect to Redis: {e}")
            self.redis_client = None

    # ─── Indicators ───────────────────────────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Let FreqAI handle all feature engineering.
        Only add additional non-FreqAI indicators here.
        """
        # FreqAI runs prediction here — injects &-future_return column
        dataframe = self.freqai.start(dataframe, metadata, self)

        # Additional confirmation indicator: ATR for volatility filter
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        # --- VERGE INTEGRATION ---
        # Publish the latest prediction to Redis so the Dashboard shows it
        if self.redis_client and not dataframe.empty:
            last_row = dataframe.iloc[-1]
            if 'do_predict' in last_row and last_row['do_predict'] == 1:
                # Convert FreqAI prediction into a 0-100 Super Score
                # Prediction is % change, e.g. 0.02 (2%). We map it:
                # > 5% -> 100, 0% -> 50, < -5% -> 0
                pred = last_row['&-future_return']
                score = min(max(int((pred + 0.05) * 1000), 0), 100)
                
                payload = {
                    "symbol": metadata['pair'],
                    "score": score,
                    "prediction": round(float(pred * 100), 2),
                    "bias": "Bullish" if pred > 0 else "Bearish",
                    "atr": round(float(last_row['atr_pct'] * 100), 2)
                }
                
                try:
                    self.redis_client.publish("verge:superscore", json.dumps(payload))
                    
                    # Also log to verge:bot_log for the Dashboard feed
                    msg = f"🔍 {metadata['pair']}: Model updated. Score: {score}, Bias: {payload['bias']}"
                    self.redis_client.publish("verge:bot_log", msg)
                except Exception as e:
                    logger.error(f"Error publishing to Redis: {e}")

        return dataframe

    # ─── Entry Signals ────────────────────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry logic based on FreqAI regression prediction.
        Phase 2: Will add Verge Super Score confirmation from Redis.
        """

        enter_long_conditions = [
            dataframe["do_predict"] == 1,                          # FreqAI confident
            dataframe["&-future_return"] > self.long_threshold.value,  # Predicted gain
            dataframe["volume"] > 0,
        ]

        enter_short_conditions = [
            dataframe["do_predict"] == 1,
            dataframe["&-future_return"] < self.short_threshold.value,  # Predicted drop
            dataframe["volume"] > 0,
        ]

        dataframe.loc[
            reduce(lambda x, y: x & y, enter_long_conditions),
            ["enter_long", "enter_tag"],
        ] = (1, "freqai_long")

        dataframe.loc[
            reduce(lambda x, y: x & y, enter_short_conditions),
            ["enter_short", "enter_tag"],
        ] = (1, "freqai_short")

        return dataframe

    # ─── Exit Signals ─────────────────────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit when FreqAI prediction flips or DI threshold signals noise.
        """

        exit_long_conditions = [
            dataframe["do_predict"] == 1,
            dataframe["&-future_return"] < 0,  # Model now predicts negative
        ]

        exit_short_conditions = [
            dataframe["do_predict"] == 1,
            dataframe["&-future_return"] > 0,  # Model now predicts positive
        ]

        dataframe.loc[
            reduce(lambda x, y: x & y, exit_long_conditions),
            ["exit_long", "exit_tag"],
        ] = (1, "freqai_flip")

        dataframe.loc[
            reduce(lambda x, y: x & y, exit_short_conditions),
            ["exit_short", "exit_tag"],
        ] = (1, "freqai_flip")

        return dataframe

    # ─── Custom Exit Logic ────────────────────────────────────────────────────

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[float]:
        """
        Dynamic stoploss: tighten after 1h if in profit.
        Phase 2: Will use Verge whale_watcher signal to exit early.
        """
        trade_duration = (current_time - trade.open_date_utc).seconds / 60

        # After 60 min with some profit, tighten stop
        if trade_duration > 60 and current_profit > 0.01:
            return -0.005  # 0.5% trailing from here

        return None  # Use default stoploss

    # ─── TODO: Phase 2 Integration Points ────────────────────────────────────
    # The following methods are stubs that will be wired to the Verge backend.

    def _get_verge_super_score(self, pair: str) -> Optional[float]:
        """
        Phase 2: Fetch Verge Super Score from Redis (published by verge-dotnet-backend).
        Redis key: verge:super_score:{pair}
        Returns: float 0..100 or None if unavailable.
        """
        # TODO: import redis; r = redis.from_url(os.environ.get('REDIS_URL'))
        # score = r.get(f"verge:super_score:{pair.replace('/', '_')}")
        # return float(score) if score else None
        return None

    def _get_whale_signal(self, pair: str) -> Optional[str]:
        """
        Phase 2: Fetch whale watcher signal from Redis.
        Redis key: verge:whale_signal:{pair}
        Returns: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | None
        """
        # TODO: import redis; r = redis.from_url(os.environ.get('REDIS_URL'))
        # signal = r.get(f"verge:whale_signal:{pair.replace('/', '_')}")
        # return signal.decode() if signal else None
        return None
