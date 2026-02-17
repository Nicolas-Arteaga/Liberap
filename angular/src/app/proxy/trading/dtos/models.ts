
export interface EnhancedAnalysisDto {
  rsi: number;
  sentiment: SentimentAnalysisDto;
  summary?: string;
  recommendation?: string;
}

export interface SentimentAnalysisDto {
  sentiment?: string;
  confidence: number;
  scores: Record<string, number>;
}
