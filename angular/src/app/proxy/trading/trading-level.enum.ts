import { mapEnumToOptions } from '@abp/ng.core';

export enum TradingLevel {
  Beginner = 0,
  Intermediate = 1,
  Advanced = 2,
  Expert = 3,
}

export const tradingLevelOptions = mapEnumToOptions(TradingLevel);
