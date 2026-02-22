import { mapEnumToOptions } from '@abp/ng.core';

export enum TradingStyle {
  Scalping = 0,
  DayTrading = 1,
  SwingTrading = 2,
  PositionTrading = 3,
  HODL = 4,
  GridTrading = 5,
  Arbitrage = 6,
  Algorithmic = 7,
  Auto = 8,
}

export const tradingStyleOptions = mapEnumToOptions(TradingStyle);
