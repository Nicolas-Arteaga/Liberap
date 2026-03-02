import { mapEnumToOptions } from '@abp/ng.core';

export enum MarketRegimeType {
  BullTrend = 0,
  BearTrend = 1,
  Ranging = 2,
  HighVolatility = 3,
  LowVolatility = 4,
}

export const marketRegimeTypeOptions = mapEnumToOptions(MarketRegimeType);
