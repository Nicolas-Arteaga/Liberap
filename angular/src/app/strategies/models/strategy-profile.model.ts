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

  // Ejecución real contra Binance (Testnet/Mainnet), reemplaza el hardcodeo
  // que antes solo mataba por id/nombre de estrategia en el agente.
  broadcastToBinance?: boolean;

  // Gestión de salida Trail-1 (ROUND 36-42, ver TRAIL1_STRATEGY_ROUND42.md):
  // al llegar a +100/+150/+200bp de excursión favorable, mueve el SL a
  // breakeven/+50bp/+100bp respectivamente. Solo aplica si además
  // "TrailStop:Enabled" está en true en el backend (interruptor maestro).
  useTrailStop?: boolean;

  // Métricas (opcional para visualización)
  winRate?: number;
  totalTrades?: number;
  netPnL?: number;
  avgRR?: number;
}
