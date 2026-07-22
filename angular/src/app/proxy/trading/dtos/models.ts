import type { EntityDto, FullAuditedEntityDto } from '@abp/ng.core';
import type { SignalDirection } from '../signal-direction.enum';
import type { TradeStatus } from '../trade-status.enum';
import type { SignalConfidence } from '../signal-confidence.enum';
import type { MarketRegimeType } from '../market-regime-type.enum';
import type { TradingStage } from '../trading-stage.enum';

export interface AlertHistoryDto extends FullAuditedEntityDto<string> {
  symbol?: string;
  style?: string;
  direction: number;
  entryPrice: number;
  targetPrice: number;
  stopLossPrice: number;
  confidence: number;
  estimatedTimeMinutes: number;
  expectedDrawdownPct: number;
  reasoningJson?: string;
  rawDataJson?: string;
  emittedAt?: string;
  expiresAt?: string;
  status?: string;
  actualExitPrice?: number;
  actualPnlPct?: number;
  timeToResolutionMinutes?: number;
  alertTier?: string;
  alertType?: string;
  isRead: boolean;
  directionName?: string;
  tierDisplayName?: string;
}

export interface BinanceTradeResultDto {
  success: boolean;
  message?: string;
}

export interface CloseBinanceTradeInputDto {
  symbol?: string;
}

export interface CreateUpdateStrategyProfileDto {
  name?: string;
  description?: string;
  color?: string;
  isActive: boolean;
  minConfluenceScore: number;
  minNexusConfidence: number;
  maxRsiLong: number;
  minRsiShort: number;
  maxMa7DistancePct: number;
  requireMacdPositive?: boolean;
  allowedSources?: string;
  allowLong: boolean;
  allowShort: boolean;
  marginPerTrade: number;
  tpMultiplier: number;
  slMultiplier: number;
  minRR: number;
  maxOpenPositions: number;
  maxTradeDurationCandles: number;
  activeHoursStart?: string;
  activeHoursEnd?: string;
  enabledDays: string[];
  extremeRsiVeto: boolean;
  maxEntrySlippagePct: number;
  lseMaxEntrySlippagePct: number;
  minTpDistancePct: number;
  minSlDistancePct: number;
  minEstimatedRangePct: number;
  maxNexusSignalAgeSeconds: number;
  nexusMaxPriceDriftPct: number;
  strategyType?: string;
  patternParamsJson?: string;
  broadcastToBinance: boolean;
}

export interface EnhancedAnalysisDto {
  rsi: number;
  sentiment: SentimentAnalysisDto;
  summary?: string;
  recommendation?: string;
}

export interface EquityPointDto {
  timestamp?: string;
  balance: number;
}

export interface OpenBinanceTradeInputDto {
  symbol?: string;
  side?: string;
  quantity: number;
  tpPrice?: number;
  slPrice?: number;
}

export interface OpenTradeInputDto {
  symbol?: string;
  side?: SignalDirection;
  amount: number;
  leverage: number;
  tpPrice?: number;
  slPrice?: number;
  tradingSignalId?: string;
  exchange?: string;
  agentDecisionJson?: string;
  strategyProfileId?: string;
  ma7DistancePctAtEntry?: number;
}

export interface SentimentAnalysisDto {
  sentiment?: string;
  confidence: number;
  scores: Record<string, number>;
}

export interface SignalRegimeStatDto {
  regime?: string;
  wins: number;
  losses: number;
  winRate: number;
  totalPnL: number;
}

export interface SignalStatsDto {
  symbol?: string;
  totalSignals: number;
  wins: number;
  losses: number;
  winRate: number;
  totalRealizedPnL: number;
  averagePnLPerTrade: number;
  expectancy: number;
  averageDurationMinutes: number;
  equityCurve: number[];
  byRegime: SignalRegimeStatDto[];
}

export interface SimulatedTradeDto extends EntityDto<string> {
  userId?: string;
  symbol?: string;
  side?: SignalDirection;
  leverage: number;
  size: number;
  amount: number;
  entryPrice: number;
  markPrice: number;
  liquidationPrice: number;
  margin: number;
  marginRate: number;
  unrealizedPnl: number;
  roiPercentage: number;
  status?: TradeStatus;
  closePrice?: number;
  realizedPnl?: number;
  tpPrice?: number;
  slPrice?: number;
  entryFee: number;
  exitFee: number;
  totalFundingPaid: number;
  openedAt?: string;
  closedAt?: string;
  tradingSignalId?: string;
  exchange?: string;
  agentDecisionJson?: string;
  strategyProfileId?: string;
  maxAdversePrice?: number;
  maxFavorablePrice?: number;
  exitReason?: string;
  ma7DistancePctAtEntry?: number;
  btcPriceAtClose?: number;
  exitAuditJson?: string;
  tpProgressPct?: number;
  maxTpProgressPct?: number;
  maxSlProgressPct?: number;
}

export interface SimulationPerformanceDto {
  totalGain: number;
  winRate: number;
  totalTrades: number;
  avgPerTrade: number;
  equityCurve: EquityPointDto[];
}

export interface StrategyProfileDto extends EntityDto<string> {
  userId?: string;
  name?: string;
  description?: string;
  color?: string;
  isActive: boolean;
  minConfluenceScore: number;
  minNexusConfidence: number;
  maxRsiLong: number;
  minRsiShort: number;
  maxMa7DistancePct: number;
  requireMacdPositive?: boolean;
  allowedSources?: string;
  allowLong: boolean;
  allowShort: boolean;
  marginPerTrade: number;
  tpMultiplier: number;
  slMultiplier: number;
  minRR: number;
  maxOpenPositions: number;
  maxTradeDurationCandles: number;
  activeHoursStart?: string;
  activeHoursEnd?: string;
  enabledDays: string[];
  extremeRsiVeto: boolean;
  maxEntrySlippagePct: number;
  lseMaxEntrySlippagePct: number;
  minTpDistancePct: number;
  minSlDistancePct: number;
  minEstimatedRangePct: number;
  maxNexusSignalAgeSeconds: number;
  nexusMaxPriceDriftPct: number;
  strategyType?: string;
  patternParamsJson?: string;
  broadcastToBinance: boolean;
  winRate: number;
  totalTrades: number;
  netPnL: number;
  avgRR: number;
}

export interface TargetZoneDto {
  low: number;
  high: number;
}

export interface TradingSignalDto extends EntityDto<string> {
  symbol?: string;
  direction?: SignalDirection;
  entryPrice: number;
  confidence?: SignalConfidence;
  profitPotential: number;
  analyzedDate?: string;
  status?: TradeStatus;
  realizedPnL?: number;
  regime?: MarketRegimeType;
  exitPrice?: number;
  exitTime?: string;
  durationMinutes?: number;
  equityAfter?: number;
  score?: number;
}

export interface UpdateExitInfoInputDto {
  exitReason?: string;
  btcPriceAtClose?: number;
  exitAuditJson?: string;
}

export interface UpdateMaxAdversePriceInputDto {
  maxAdversePrice: number;
}

export interface UpdateMaxFavorablePriceInputDto {
  maxFavorablePrice: number;
}

export interface UpdateTpSlInputDto {
  tpPrice?: number;
  slPrice?: number;
}

export interface VergeAlertDto {
  id?: string;
  type?: string;
  title?: string;
  message?: string;
  timestamp?: string;
  read: boolean;
  crypto?: string;
  price?: number;
  confidence?: SignalConfidence;
  direction?: SignalDirection;
  stage?: TradingStage;
  score?: number;
  targetZone: TargetZoneDto;
  riskRewardRatio?: number;
  winProbability?: number;
  historicSampleSize?: number;
  patternSignal?: string;
  stopLoss?: number;
  takeProfit?: number;
  whaleInfluenceScore?: number;
  isSqueeze?: boolean;
  structure?: string;
  bosDetected: boolean;
  chochDetected: boolean;
  liquidityZones: number[];
  severity?: string;
  icon?: string;
  agentOpinions: Record<string, string>;
}
