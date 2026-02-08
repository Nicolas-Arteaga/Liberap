import { mapEnumToOptions } from '@abp/ng.core';

export enum SignalConfidence {
  High = 0,
  Medium = 1,
  Low = 2,
}

export const signalConfidenceOptions = mapEnumToOptions(SignalConfidence);
