import { mapEnumToOptions } from '@abp/ng.core';

export enum RiskTolerance {
  Low = 0,
  Medium = 1,
  High = 2,
}

export const riskToleranceOptions = mapEnumToOptions(RiskTolerance);
