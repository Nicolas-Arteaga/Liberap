export interface PairBotInfo {
  symbol: string;
  score: number;
  prediction: number;
  bias: string;
  atr: number;
  recommendedAction: string;
  // Adding for V2
  status?: string; 
  trainingProgress?: number;
}

export type BotStatus = 'Running' | 'Paused' | 'Stopped' | 'Dry-Run';
export type StrategyType = 'Scalping' | 'Grid' | 'DCA';

export interface SimulatedOrder {
  id: string;
  name: string;
  symbol: string;
  type: StrategyType;
  direction: 'LONG' | 'SHORT';
  status: BotStatus;
  entryTime: Date;
  entryPrice: number;
  currentPrice: number;
  entryScore: number;
  prediction: number;
  atr: number;
  sl: number;
  tp: number;
  leverage: number;
  capital: number;
  pnl: number;
  pnlPercent: number;
}
