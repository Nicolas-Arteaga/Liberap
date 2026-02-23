import type { AnalysisLogType } from './analysis-log-type.enum';
import type { EntityDto, FullAuditedEntityDto, PagedAndSortedResultRequestDto } from '@abp/ng.core';
import type { AlertType } from './alert-type.enum';
import type { SignalDirection } from './signal-direction.enum';
import type { RiskTolerance } from './risk-tolerance.enum';
import type { TradingStyle } from './trading-style.enum';
import type { OrderType } from './order-type.enum';
import type { TradeStatus } from './trade-status.enum';
import type { SignalConfidence } from './signal-confidence.enum';
import type { TradingLevel } from './trading-level.enum';
import type { TradingStage } from './trading-stage.enum';

export interface AnalysisLogDto {
  symbol?: string;
  message?: string;
  level?: string;
  timestamp?: string;
  logType?: AnalysisLogType;
  dataJson?: string;
}

export interface BacktestResultDto extends FullAuditedEntityDto<string> {
  tradingStrategyId?: string;
  symbol?: string;
  timeframe?: string;
  startDate?: string;
  endDate?: string;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  totalProfit: number;
  maxDrawdown: number;
  sharpeRatio: number;
  equityCurveJson?: string;
}

export interface ConnectExchangeDto {
  exchangeName?: string;
  apiKey?: string;
  apiSecret?: string;
}

export interface CreateUpdateTradingAlertDto {
  symbol?: string;
  triggerPrice: number;
  message?: string;
  type?: AlertType;
  channels: string[];
}

export interface CreateUpdateTradingStrategyDto {
  name?: string;
  directionPreference?: SignalDirection;
  selectedCryptos: string[];
  leverage: number;
  capital: number;
  riskLevel?: RiskTolerance;
  autoStopLoss: boolean;
  takeProfitPercentage: number;
  stopLossPercentage: number;
  notificationsEnabled: boolean;
  isAutoMode: boolean;
  customSymbols: string[];
  style?: TradingStyle;
  styleParametersJson?: string;
}

export interface ExchangeConnectionDto extends FullAuditedEntityDto<string> {
  exchangeName?: string;
  isConnected: boolean;
  lastSyncTime?: string;
}

export interface ExecuteTradeDto {
  symbol?: string;
  direction?: SignalDirection;
  amount: number;
  leverage: number;
  takeProfitPercentage: number;
  stopLossPercentage: number;
  orderType?: OrderType;
}

export interface GetHistoryInput extends PagedAndSortedResultRequestDto {
  symbol?: string;
  startDate?: string;
  endDate?: string;
}

export interface GetMarketCandlesInput {
  symbol?: string;
  interval?: string;
  limit: number;
}

export interface GetSignalsInput extends PagedAndSortedResultRequestDto {
  status?: TradeStatus;
  confidence?: SignalConfidence;
}

export interface MarketAnalysisDto {
  symbol?: string;
  rsi: number;
  trend?: string;
  confidence: number;
  signal?: string;
  sentiment?: string;
  timestamp?: string;
  description?: string;
}

export interface MarketCandleDto {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface OpportunityDto {
  symbol?: string;
  confidence: number;
  signal?: string;
  reason?: string;
  entryMin?: number;
  entryMax?: number;
}

export interface RecommendedStyleDto {
  style?: TradingStyle;
  reason?: string;
}

export interface RunBacktestDto {
  tradingStrategyId?: string;
  symbol?: string;
  timeframe?: string;
  startDate?: string;
  endDate?: string;
}

export interface StartSessionDto {
  symbol?: string;
  timeframe?: string;
}

export interface TradeOrderDto extends FullAuditedEntityDto<string> {
  symbol?: string;
  direction?: SignalDirection;
  amount: number;
  leverage: number;
  entryPrice: number;
  exitPrice?: number;
  takeProfitPrice: number;
  stopLossPrice: number;
  orderType?: OrderType;
  status?: TradeStatus;
  profitLoss: number;
  executionDate?: string;
  closeDate?: string;
}

export interface TraderProfileDto extends FullAuditedEntityDto<string> {
  userId?: string;
  name?: string;
  email?: string;
  level?: TradingLevel;
  riskTolerance?: RiskTolerance;
  totalProfit: number;
  accuracy: number;
  activeStrategiesCount: number;
}

export interface TradingAlertDto extends FullAuditedEntityDto<string> {
  symbol?: string;
  triggerPrice: number;
  message?: string;
  type?: AlertType;
  isActive: boolean;
  channels: string[];
}

export interface TradingSessionDto extends FullAuditedEntityDto<string> {
  symbol?: string;
  timeframe?: string;
  currentStage?: TradingStage;
  startTime?: string;
  isActive: boolean;
  entryPrice?: number;
  takeProfitPrice?: number;
  stopLossPrice?: number;
}

export interface TradingSignalDto extends EntityDto<string> {
  symbol?: string;
  direction?: SignalDirection;
  entryPrice: number;
  confidence?: SignalConfidence;
  profitPotential: number;
  analyzedDate?: string;
  status?: TradeStatus;
}

export interface TradingStrategyDto extends FullAuditedEntityDto<string> {
  traderProfileId?: string;
  name?: string;
  directionPreference?: SignalDirection;
  selectedCryptos: string[];
  leverage: number;
  capital: number;
  riskLevel?: RiskTolerance;
  autoStopLoss: boolean;
  takeProfitPercentage: number;
  stopLossPercentage: number;
  notificationsEnabled: boolean;
  isAutoMode: boolean;
  customSymbols: string[];
  style?: TradingStyle;
  styleParametersJson?: string;
}

export interface UpdateTraderProfileDto {
  name?: string;
  level?: TradingLevel;
  riskTolerance?: RiskTolerance;
}
