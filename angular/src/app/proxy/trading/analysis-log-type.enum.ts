import { mapEnumToOptions } from '@abp/ng.core';

export enum AnalysisLogType {
  Standard = 0,
  OpportunityRanking = 1,
  AlertContext = 2,
  AlertPrepare = 3,
  AlertEntry = 4,
  AlertInvalidated = 5,
  AlertExit = 6,
}

export const analysisLogTypeOptions = mapEnumToOptions(AnalysisLogType);
