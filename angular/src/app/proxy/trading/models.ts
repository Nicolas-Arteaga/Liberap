import type { AnalysisLogType } from './analysis-log-type.enum';
import type { FullAuditedEntityDto, PagedAndSortedResultRequestDto } from '@abp/ng.core';
import type { AlertType } from './alert-type.enum';
import type { SignalDirection } from './signal-direction.enum';
import type { RiskTolerance } from './risk-tolerance.enum';
import type { TradingStyle } from './trading-style.enum';
import type { OrderType } from './order-type.enum';
import type { TradeStatus } from './trade-status.enum';
import type { SignalConfidence } from './signal-confidence.enum';
import type { TradingLevel } from './trading-level.enum';
import type { TradingStage } from './trading-stage.enum';
import type { MarketRegimeType } from './market-regime-type.enum';

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
  profitFactor: number;
  maxDrawdown: number;
  sharpeRatio: number;
  sortinoRatio: number;
  equityCurveJson?: string;
  initialCapital: number;
  totalFeesPaid: number;
  totalSlippageLoss: number;
  expectancy: number;
  tradeFrequencyPerDay: number;
}

export interface ComparativeEvaluationReportDto {
  results: ComparativeEvaluationResultDto[];
  evaluationDate?: string;
}

export interface ComparativeEvaluationResultDto {
  symbol?: string;
  tradingStyle?: string;
  baseline: BacktestResultDto;
  optimized: BacktestResultDto;
  winRateImprovement: number;
  profitFactorImprovement: number;
  sharpeRatioImprovement: number;
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

export interface GetMarketDataInput {
  symbol?: string;
  limit: number;
}

export interface GetSignalsInput extends PagedAndSortedResultRequestDto {
  status?: TradeStatus;
  confidence?: SignalConfidence;
}

export interface LiveShadowReportDto {
  evaluationDate?: string;
  symbol?: string;
  totalSignalsGenerated: number;
  averageLatentDelay?: string;
  signalDeviationPercentage: number;
  passedLiveShadow: boolean;
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
  structure?: string;
  bosDetected: boolean;
}

export interface MarketCandleDto {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface MarketOrderBookDto {
  bids: OrderBookEntryDto[];
  asks: OrderBookEntryDto[];
}

export interface MonteCarloReportDto {
  evaluationDate?: string;
  symbol?: string;
  iterations: number;
  initialCapital: number;
  averageEndingCapital: number;
  worstCaseDrawdown: number;
  probabilityOfRuin: number;
  passedRuinRisk: boolean;
}

export interface OpportunityDto {
  symbol?: string;
  confidence: number;
  signal?: string;
  reason?: string;
  entryMinPrice?: number;
  entryMaxPrice?: number;
  entryMin?: number;
  entryMax?: number;
}

export interface OrderBookEntryDto {
  price: number;
  amount: number;
}

export interface PaperTradingReportDto {
  evaluationDate?: string;
  symbol?: string;
  environment?: string;
  simulatedDays: number;
  totalExecutedTrades: number;
  theoreticalBacktest: BacktestResultDto;
  realizedProfitFactor: number;
  deviationPercentage: number;
  passedPaperTrading: boolean;
}

export interface RecentTradeDto {
  id: number;
  price: number;
  amount: number;
  time: number;
  isBuyerMaker: boolean;
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
  weightOverrides: Record<string, number>;
  entryThresholdOverride?: number;
  trailingMultiplierOverride?: number;
  feePercentage: number;
  slippagePercentage: number;
  initialCapital: number;
}

export interface StartSessionDto {
  symbol?: string;
  timeframe?: string;
}

export interface StressTestEventDto {
  eventName?: string;
  startDate?: string;
  endDate?: string;
  result: BacktestResultDto;
  survived: boolean;
}

export interface StressTestReportDto {
  evaluationDate?: string;
  symbol?: string;
  events: StressTestEventDto[];
  passedAllEvents: boolean;
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
  selectedStyle?: TradingStyle;
  selectedDirection?: SignalDirection;
  netProfit?: number;
  outcome?: TradeStatus;
  exitReason?: string;
  lastEvaluationTimestamp?: number;
  stageChangedTimestamp?: string;
  score?: number;
  trailingStopPrice?: number;
  isBreakEvenActive: boolean;
  partialTpsCount: number;
  initialStopLoss?: number;
  currentInvestment: number;
  initialScore?: number;
  initialRegime?: MarketRegimeType;
  initialConfidence?: SignalConfidence;
  initialVolatility?: number;
  initialVolumeMcapRatio?: number;
  entryHour?: number;
  entryDayOfWeek?: any;
  whaleInfluenceScore?: number;
  whaleSentiment?: string;
  macroQuietPeriod?: boolean;
  macroReason?: string;
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

export interface WalkForwardReportDto {
  evaluationDate?: string;
  symbol?: string;
  tradingStyle?: string;
  windows: WalkForwardWindowDto[];
  passedAllWindows: boolean;
}

export interface WalkForwardWindowDto {
  windowName?: string;
  trainingStart?: string;
  trainingEnd?: string;
  testingStart?: string;
  testingEnd?: string;
  trainingResult: BacktestResultDto;
  testingResult: BacktestResultDto;
  passedProfitFactor: boolean;
}
export interface SymbolTickerDto {
  symbol?: string;
  lastPrice: number;
  priceChange: number;
  priceChangePercent: number;
  volume: number;
  highPrice: number;
  lowPrice: number;
}
