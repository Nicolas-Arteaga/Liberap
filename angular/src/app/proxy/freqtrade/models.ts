
export interface FreqtradeCreateBotDto {
  pair: string;
  timeframe: string;
  stakeAmount: number;
  tpPercent: number;
  slPercent: number;
  leverage: number;
  strategy?: string;
}

export interface FreqtradeProfitDto {
  totalProfit: number;
  todayProfit: number;
  winRate: number;
  totalTrades: number;
}

export interface FreqtradeStatusDto {
  isRunning: boolean;
  currentPair?: string;
  openTradesCount: number;
  runtimeSeconds: number;
}

export interface FreqtradeTradeDto {
  id: number;
  pair?: string;
  amount: number;
  openRate: number;
  currentRate: number;
  pnl: number;
  openDate?: string;
}
