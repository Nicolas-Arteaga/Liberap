import { mapEnumToOptions } from '@abp/ng.core';

export enum TradeStatus {
  Open = 0,
  Win = 1,
  Loss = 2,
  BreakEven = 3,
  Canceled = 4,
  Expired = 5,
}

export const tradeStatusOptions = mapEnumToOptions(TradeStatus);
