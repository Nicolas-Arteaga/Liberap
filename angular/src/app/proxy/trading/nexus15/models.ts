
export interface Nexus15FeaturesDto {
  candleBodyRatio: number;
  upperWickRatio: number;
  lowerWickRatio: number;
  consecutiveBullBars: number;
  orderBlockDetected: boolean;
  fairValueGap: boolean;
  bosDetected: boolean;
  wyckoffPhase?: string;
  springDetected: boolean;
  upthrustDetected: boolean;
  fractalHigh5: boolean;
  fractalLow5: boolean;
  trendStructure: number;
  volumeRatio20: number;
  cvdDelta: number;
  volumeSurgeBullish: boolean;
  pocProximity: number;
  rsi14: number;
  macdHistogram: number;
  atrPercent: number;
  volumeExplosion?: boolean;
  explosionBullish?: boolean;
  explosionBearish?: boolean;
}

export interface Nexus15GroupScoresDto {
  g1PriceAction: number;
  g2SmcIct: number;
  g3Wyckoff: number;
  g4Fractals: number;
  g5Volume: number;
  g6Ml: number;
}

export interface Nexus15ResultDto {
  symbol?: string;
  timeframe?: string;
  analyzedAt?: string;
  aiConfidence: number;
  direction?: string;
  recommendation?: string;
  next5CandlesProb: number;
  next15CandlesProb: number;
  next20CandlesProb: number;
  estimatedRangePercent: number;
  regime?: string;
  volumeExplosion?: boolean;
  groupScores: Nexus15GroupScoresDto;
  features: Nexus15FeaturesDto;
  detectivity: Record<string, string>;
}
