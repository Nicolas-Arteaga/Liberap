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
}

export interface SimulationPerformanceDto {
  totalGain: number;
  winRate: number;
  totalTrades: number;
  avgPerTrade: number;
  equityCurve: EquityPointDto[];
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
