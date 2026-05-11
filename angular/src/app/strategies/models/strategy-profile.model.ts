export interface StrategyProfile {
  id?: string;
  name: string;
  description?: string;
  color?: string;
  isActive: boolean;

  // Filtros de Entrada
  minConfluenceScore: number;
  minNexusConfidence: number;
  maxRsiLong: number;
  minRsiShort: number;
  maxMa7DistancePct: number;
  macdRequired?: string; // 'none' | 'positive' | 'negative'
  allowedSources?: string[]; // 'Nexus', 'LSE', 'Bridge'
  allowLong: boolean;
  allowShort: boolean;

  // Gestión de Riesgo
  marginPerTrade: number;
  tpMultiplier: number;
  slMultiplier: number;
  minRR: number;
  maxOpenPositions: number;
  maxTradeDurationCandles: number;

  // Filtros Avanzados
  activeHoursStart?: string;
  activeHoursEnd?: string;
  enabledDays?: string[]; // 'Mon', 'Tue', etc.
  extremeRsiVeto: boolean;

  // Métricas (opcional para visualización)
  winRate?: number;
  totalTrades?: number;
  netPnL?: number;
  avgRR?: number;
}
