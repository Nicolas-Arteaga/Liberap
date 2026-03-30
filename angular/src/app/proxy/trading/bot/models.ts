
export interface BotActivityLogDto {
  symbol?: string;
  message?: string;
  type?: string;
  timestamp?: string;
}

export interface BotEquityPointDto {
  time?: string;
  balance: number;
  pnL: number;
}

export interface BotTradeDto {
  id?: string;
  userId?: string;
  symbol?: string;
  direction?: string;
  timeframe?: string;
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  trailingStopPrice?: number;
  leverage: number;
  margin: number;
  positionSize: number;
  status?: string;
  partialCloseDone: boolean;
  trailingActive: boolean;
  partialPnl?: number;
  finalPnl?: number;
  totalPnl?: number;
  closeReason?: string;
  atr: number;
  atrPercent: number;
  slPercent: number;
  scannerScore: number;
  openedAt?: string;
  partialClosedAt?: string;
  closedAt?: string;
  durationMinutes?: number;
  simulatedTradeId?: string;
}

export interface ScalpingBotConfigDto {
  enabled: boolean;
  timeframe?: string;
  dynamicSymbols: boolean;
  topSymbolsCount: number;
  whitelistSymbols: string[];
  blacklistSymbols: string[];
  riskPercent: number;
  minScore: number;
  maxOpenPositions: number;
  minLeverage: number;
  maxLeverage: number;
  partialCloseRR: number;
  finalTpRR: number;
  allowQuietPeriodTrading: boolean;
  requireTrendConfirmation: boolean;
  botName?: string;
}

export interface ScalpingBotStatusDto {
  isRunning: boolean;
  config: ScalpingBotConfigDto;
  openPositions: number;
  maxPositions: number;
  dailyPnl: number;
  dailyTrades: number;
  dailyWins: number;
  dailyLosses: number;
  dailyWinRate: number;
  activeSymbols: string[];
  lastCycleAt?: string;
  openTrades: BotTradeDto[];
  recentLogs: BotActivityLogDto[];
}
