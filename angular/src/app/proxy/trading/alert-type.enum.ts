import { mapEnumToOptions } from '@abp/ng.core';

export enum AlertType {
  Stage1 = 0,
  Stage2 = 1,
  Stage3 = 2,
  Stage4 = 3,
  Custom = 4,
  System = 5,
}

export const alertTypeOptions = mapEnumToOptions(AlertType);
