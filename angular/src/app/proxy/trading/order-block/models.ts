
export interface ObZoneDto {
  id?: string;
  direction?: string; // bullish | bearish
  top: number;
  bottom: number;
  bosPrice: number;
  formedAt?: string;
  formedAtMs: number;
  candleIndex: number;
  entryStatus?: string; // 'IN_ZONE' | 'APPROACHING' | 'FAR'
  distToEntryPct: number;
  pocConfluence: boolean;
  pocDistancePct: number;
  confluenceScore: number;
  slPrice: number;
  tpPrice: number;
  tpDistancePct: number;
  validatedStable: boolean;
}

export interface ObAnalyzeResponseDto {
  symbol?: string;
  interval?: string;
  analyzedAt?: string;
  currentPrice: number;
  zones: ObZoneDto[];
}

export interface ObScanItemDto {
  symbol?: string;
  direction?: string;
  top: number;
  bottom: number;
  currentPrice: number;
  pocConfluence: boolean;
  pocDistancePct: number;
  entryStatus?: string;
  distToEntryPct: number;
  slPrice: number;
  tpPrice: number;
  tpDistancePct: number;
  confluenceScore: number;
  formedAt?: string;
  validatedStable: boolean;
}

export interface ObScanResponseDto {
  top5: ObScanItemDto[];
  scannedCount: number;
  analyzedAt?: string;
  actionableCount: number;
}
