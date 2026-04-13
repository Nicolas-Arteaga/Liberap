using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace Verge.Trading.Nexus15;

public class Nexus15ResponseModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("timeframe")]
    public string Timeframe { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
    [JsonPropertyName("ai_confidence")]
    public double AiConfidence { get; set; }     // 0-100
    [JsonPropertyName("direction")]
    public string Direction { get; set; }         // BULLISH / BEARISH / NEUTRAL
    [JsonPropertyName("recommendation")]
    public string Recommendation { get; set; }    // Long / Short / Wait
    [JsonPropertyName("next_5_candles_prob")]
    public double Next5CandlesProb { get; set; }
    [JsonPropertyName("next_15_candles_prob")]
    public double Next15CandlesProb { get; set; }
    [JsonPropertyName("next_20_candles_prob")]
    public double Next20CandlesProb { get; set; }
    [JsonPropertyName("estimated_range_percent")]
    public double EstimatedRangePercent { get; set; }
    [JsonPropertyName("regime")]
    public string Regime { get; set; }
    [JsonPropertyName("group_scores")]
    public Nexus15GroupScoresModel GroupScores { get; set; }
    [JsonPropertyName("features")]
    public Nexus15FeaturesModel Features { get; set; }
    [JsonPropertyName("detectivity")]
    public Dictionary<string, string> Detectivity { get; set; }
}

public class Nexus15GroupScoresModel
{
    [JsonPropertyName("g1_price_action")]
    public double G1PriceAction { get; set; }
    [JsonPropertyName("g2_smc_ict")]
    public double G2SmcIct { get; set; }
    [JsonPropertyName("g3_wyckoff")]
    public double G3Wyckoff { get; set; }
    [JsonPropertyName("g4_fractals")]
    public double G4Fractals { get; set; }
    [JsonPropertyName("g5_volume")]
    public double G5Volume { get; set; }
    [JsonPropertyName("g6_ml")]
    public double G6Ml { get; set; }
}

public class Nexus15FeaturesModel
{
    [JsonPropertyName("candle_body_ratio")]
    public double CandleBodyRatio { get; set; }
    [JsonPropertyName("upper_wick_ratio")]
    public double UpperWickRatio { get; set; }
    [JsonPropertyName("lower_wick_ratio")]
    public double LowerWickRatio { get; set; }
    [JsonPropertyName("consecutive_bull_bars")]
    public int ConsecutiveBullBars { get; set; }
    [JsonPropertyName("order_block_detected")]
    public bool OrderBlockDetected { get; set; }
    [JsonPropertyName("fair_value_gap")]
    public bool FairValueGap { get; set; }
    [JsonPropertyName("bos_detected")]
    public bool BosDetected { get; set; }
    [JsonPropertyName("wyckoff_phase")]
    public string WyckoffPhase { get; set; }
    [JsonPropertyName("spring_detected")]
    public bool SpringDetected { get; set; }
    [JsonPropertyName("upthrust_detected")]
    public bool UpthrustDetected { get; set; }
    [JsonPropertyName("fractal_high_5")]
    public bool FractalHigh5 { get; set; }
    [JsonPropertyName("fractal_low_5")]
    public bool FractalLow5 { get; set; }
    [JsonPropertyName("trend_structure")]
    public int TrendStructure { get; set; }
    [JsonPropertyName("volume_ratio_20")]
    public double VolumeRatio20 { get; set; }
    [JsonPropertyName("cvd_delta")]
    public double CvdDelta { get; set; }
    [JsonPropertyName("volume_surge_bullish")]
    public bool VolumeSurgeBullish { get; set; }
    [JsonPropertyName("poc_proximity")]
    public double PocProximity { get; set; }
    [JsonPropertyName("rsi_14")]
    public double Rsi14 { get; set; }
    [JsonPropertyName("macd_histogram")]
    public double MacdHistogram { get; set; }
    [JsonPropertyName("atr_percent")]
    public double AtrPercent { get; set; }
}

public interface IPythonNexus15Service
{
    Task<Nexus15ResponseModel?> AnalyzeNexus15Async(string symbol, List<MarketCandleModel> candles);
}
