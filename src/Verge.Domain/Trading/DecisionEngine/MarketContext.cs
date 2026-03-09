using System;
using System.Collections.Generic;
using System.Linq;
using Verge.Trading.Integrations;
using Verge.Trading;

namespace Verge.Trading.DecisionEngine;

public class MarketContext
{
    // Macro
    public FearAndGreedResult? FearAndGreed { get; set; }
    
    // Sentiment (FreeCryptoNews + AI)
    public List<CryptoNewsItem> News { get; set; } = new();
    public SentimentAnalysis? GlobalSentiment { get; set; }
    
    // Fundaments (CoinGecko)
    public CoinGeckoResult? CoinGeckoData { get; set; }
    
    // Advanced Metrics
    public MarketOpenInterestModel? OpenInterest { get; set; }
    
    // AI / Data Science (Python)
    public RegimeResponseModel? MarketRegime { get; set; }
    public TechnicalsResponseModel? Technicals { get; set; }
    public WhaleAnalysisResult? WhaleData { get; set; }
    public InstitutionalAnalysisResult? InstitutionalData { get; set; }
    public MacroAnalysisResult? MacroData { get; set; }
    
    // Raw Data for internal calculations
    public List<MarketCandleModel> Candles { get; set; } = new();

    // Multi-Timeframe Confirmation
    public MarketContext? HigherTimeframeContext { get; set; }

    public DateTime GetLastUpdated()
    {
        if (Candles == null || !Candles.Any()) return DateTime.MinValue;
        var maxTimestamp = Candles.Max(c => c.Timestamp);
        return DateTimeOffset.FromUnixTimeSeconds(maxTimestamp).DateTime;
    }
}

public class DecisionResult
{
    public TradingDecision Decision { get; set; }
    public SignalConfidence Confidence { get; set; }
    public int Score { get; set; } // 0-100
    public string Reason { get; set; } = string.Empty;
    public Dictionary<string, float> WeightedScores { get; set; } = new();
    public decimal? EntryMinPrice { get; set; }
    public decimal? EntryMaxPrice { get; set; }
    
    // Institutional 1% metrics
    public double? RiskRewardRatio { get; set; }
    public double? WinProbability { get; set; }
    public int? HistoricSampleSize { get; set; }
    public string? PatternSignal { get; set; }
    public double? WhaleInfluenceScore { get; set; }
    public string? WhaleSentiment { get; set; }
    public bool? MacroQuietPeriod { get; set; }
    public string? MacroReason { get; set; }
    public float? TrailingMultiplier { get; set; }
    public decimal? StopLossPrice { get; set; }
    public decimal? TakeProfitPrice { get; set; }
}

public enum TradingDecision
{
    Ignore,     // Score < 30
    Context,    // Score 30-49 (Stay in Evaluating)
    Prepare,    // Score 50-69 (Advance to Prepared)
    Entry       // Score >= 70 (Advance to BuyActive)
}
