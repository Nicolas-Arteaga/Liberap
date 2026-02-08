import { mapEnumToOptions } from '@abp/ng.core';

export enum OrderType {
  Market = 0,
  Limit = 1,
}

export const orderTypeOptions = mapEnumToOptions(OrderType);
