from freqtrade.strategy import IStrategy
import ta.trend

class VergeTestStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'
    max_open_trades = 3

    minimal_roi = { "0": 0.05, "100": 0.01, "200": 0.0 }
    stoploss = -0.10

    def populate_indicators(self, dataframe, metadata):
        dataframe['ema7'] = ta.trend.ema_indicator(dataframe['close'], window=7)
        dataframe['ema25'] = ta.trend.ema_indicator(dataframe['close'], window=25)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[(dataframe['ema7'] > dataframe['ema25']), 'enter_long'] = 1
        dataframe.loc[(dataframe['ema7'] < dataframe['ema25']), 'enter_short'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[(dataframe['ema7'] < dataframe['ema25']), 'exit_long'] = 1
        dataframe.loc[(dataframe['ema7'] > dataframe['ema25']), 'exit_short'] = 1
        return dataframe
