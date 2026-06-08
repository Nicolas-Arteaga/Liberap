
export interface Nexus5FeaturesDto {
  compressionRange: number;
  ignitionCandle: boolean;
  efficiencyCheck: number;
  displacementFvg: boolean;
  microChoch: boolean;
  instantOrderBlock: boolean;
  compressionZone: boolean;
  sosDetected: boolean;
  jumpingCreek: boolean;
  fractalHighBreak: boolean;
  ema7Angle: number;
  hhHlSequence: boolean;
  relativeVolMultiplier: number;
  volIntensity: number;
  buyingImbalance: number;
  atrExpansion: number;
  zScore: number;
  rsiVelocity: number;
}

export interface Nexus5GroupScoresDto {
  g1PriceAction: number;
  g2SmcIct: number;
  g3Wyckoff: number;
  g4Fractals: number;
  g5Volume: number;
  g6Ml: number;
}

export interface Nexus5ResultDto {
  symbol?: string;
  timeframe?: string;
  analyzedAt?: string;
  aiConfidence: number;
  direction?: string;
  recommendation?: string;
  phase?: string;
  phaseScore: number;
  entryTimeframe?: string;
  compressionState: boolean;
  ignitionDetected: boolean;
  bypassActive: boolean;
  next3CandlesProb: number;
  next5CandlesProb: number;
  next10CandlesProb: number;
  estimatedRangePercent: number;
  regime?: string;
  volumeExplosion: boolean;
  groupScores: Nexus5GroupScoresDto;
  features: Nexus5FeaturesDto;
  detectivity: Record<string, string>;
}
