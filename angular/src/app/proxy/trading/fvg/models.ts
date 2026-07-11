
export interface VolumeProfileBinDto {
  priceLow: number;
  priceHigh: number;
  volume: number;
  isPoc: boolean;
  isHvn: boolean;
}

export interface FvgZoneDto {
  id?: string;
  direction?: string; // bullish | bearish
  top: number;
  bottom: number;
  gapPct: number;
  formedAt?: string;
  formedAtMs: number;
  candleIndex: number;
  fillProgressPct: number;
  pocConfluence: boolean;
  pocDistancePct: number;
  entryStatus?: string; // 'IN_ZONE' | 'APPROACHING' | 'EXHAUSTED' | 'FAR' | 'TP_HIT'
  distToEntryPct: number;
  tpProgressPct: number;
  confluenceScore: number;
  slPrice: number;
  tpPrice: number;
  isIfvg: boolean;
  sourceInterval?: string;
}

export interface FvgAnalyzeResponseDto {
  symbol?: string;
  interval?: string;
  analyzedAt?: string;
  currentPrice: number;
  pocPrice: number;
  zones: FvgZoneDto[];
  volumeProfile: VolumeProfileBinDto[];
}

export interface FvgScanItemDto {
  symbol?: string;
  direction?: string;
  top: number;
  bottom: number;
  gapPct: number;
  currentPrice: number;
  pocConfluence: boolean;
  pocDistancePct: number;
  entryStatus?: string; // 'IN_ZONE' | 'APPROACHING' | 'FAR'
  distToEntryPct: number;
  tpPrice: number;
  confluenceScore: number;
  fillProgressPct: number;
  formedAt?: string;
}

export interface FvgScanResponseDto {
  top5: FvgScanItemDto[];
  scannedCount: number;
  analyzedAt?: string;
}

export interface FvgCascadeResultDto {
  symbol?: string;
  cascadeStatus?: string; // 'NONE' | 'AWAITING_CONFIRMATION' | 'AWAITING_EXECUTION' | 'READY'
  biasZone?: FvgZoneDto;
  confirmationZone?: FvgZoneDto;
  executionZone?: FvgZoneDto;
  entryPriceZone?: FvgZoneDto;
  currentPrice: number;
  confluenceScore: number;
  analyzedAt?: string;
}

export interface FvgCascadeScanResponseDto {
  top5: FvgCascadeResultDto[];
  scannedCount: number;
  analyzedAt?: string;
}
