
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

export interface ScarTopSetupDto {
  symbol?: string;
  scoreGrial: number;
  prediction?: string;
  estimatedHours?: number;
  mode?: string;
}
