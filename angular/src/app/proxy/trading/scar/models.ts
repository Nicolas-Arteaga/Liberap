
export interface ScarAccuracyDto {
  tokenSymbol?: string;
  totalPredictions: number;
  totalHits: number;
  totalFalseAlarms: number;
  systemHitRate: number;
  avgTraderRoi: number;
  lastUpdated?: string;
}

export interface ScarPredictionDto {
  id: number;
  tokenSymbol?: string;
  alertDate?: string;
  scoreGrial: number;
  priceAtAlert: number;
  estimatedHours?: number;
  status?: string;
  maxPrice24h?: number;
  patternDetected: number;
  traderRoiPct: number;
  resultDate?: string;
}

export interface ScarResultDto {
  symbol?: string;
  scoreGrial: number;
  prediction?: string;
  estimatedHours?: number;
  flagWhaleWithdrawal: boolean;
  flagSupplyDrying: boolean;
  flagPriceStable: boolean;
  flagFundingNegative: boolean;
  flagSilence: boolean;
  daysSinceLastPump?: number;
  estimatedNextWindow?: string;
  withdrawalDaysCount: number;
  totalWithdrawnUsd: number;
  mode?: string;
  analyzedAt?: string;
}

export interface ScarTemplateAdjustmentDto {
  id: number;
  tokenSymbol?: string;
  adjustmentDate?: string;
  oldAvgDays: number;
  newAvgDays: number;
  reason?: string;
}

export interface ScarTopSetupDto {
  symbol?: string;
  scoreGrial: number;
  prediction?: string;
  estimatedHours?: number;
  mode?: string;
}
