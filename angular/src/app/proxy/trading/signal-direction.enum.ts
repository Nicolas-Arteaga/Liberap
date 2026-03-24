import { mapEnumToOptions } from '@abp/ng.core';

export enum SignalDirection {
  Long = 0,
  Short = 1,
  Auto = 2,
  Ignore = 3,
}

export const signalDirectionOptions = mapEnumToOptions(SignalDirection);
