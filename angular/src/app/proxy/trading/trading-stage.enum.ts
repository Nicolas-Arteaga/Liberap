import { mapEnumToOptions } from '@abp/ng.core';

export enum TradingStage {
  Evaluating = 1,
  Prepared = 2,
  BuyActive = 3,
  SellActive = 4,
}

export const tradingStageOptions = mapEnumToOptions(TradingStage);
