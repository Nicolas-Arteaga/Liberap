
export interface AdnCompressionItemDto {
  symbol?: string;
  timeframe?: string;
  phase?: string; // 'COILED' | 'PULLBACK_TO_MA7' | 'EXTENDED' | 'EXHAUSTED'
  direction?: string; // 'LONG' | 'SHORT' | 'NONE'
  ma7Crossings: number;
  compressionCandles: number;
  ignitionMultiplier: number;
  candlesSinceIgnition: number;
  currentPrice: number;
  ma7Now: number;
  ma25Now: number;
  ma99Now: number;
  distToMa7Pct: number;
  distToMa25Pct: number;
  touchedMa25SinceIgnition: boolean;
  reasons: string[];
}

export interface AdnCompressionScanResponseDto {
  top10: AdnCompressionItemDto[];
  scannedCount: number;
  qualifiedCount: number;
  analyzedAt?: string;
}
