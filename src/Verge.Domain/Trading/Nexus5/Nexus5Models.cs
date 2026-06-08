using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace Verge.Trading.Nexus5;

/// <summary>
/// Model that maps the JSON response from the Python /nexus5/analyze endpoint.
/// Uses explicit JsonPropertyName attributes for snake_case → PascalCase mapping.
/// </summary>
public class Nexus5ResponseModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }
    [JsonPropertyName("timeframe")]
    public string Timeframe { get; set; }
    [JsonPropertyName("analyzed_at")]
    public DateTime AnalyzedAt { get; set; }
    [JsonPropertyName("ai_confidence")]
    public double AiConfidence { get; set; }
    [JsonPropertyName("direction")]
    public string Direction { get; set; }
    [JsonPropertyName("recommendation")]
    public string Recommendation { get; set; }
    [JsonPropertyName("phase")]
    public string Phase { get; set; }
    [JsonPropertyName("phase_score")]
    public double PhaseScore { get; set; }
    [JsonPropertyName("entry_timeframe")]
    public string EntryTimeframe { get; set; }
    [JsonPropertyName("compression_state")]
    public bool CompressionState { get; set; }
    [JsonPropertyName("ignition_detected")]
    public bool IgnitionDetected { get; set; }
    [JsonPropertyName("bypass_active")]
    public bool BypassActive { get; set; }
    [JsonPropertyName("next_3_candles_prob")]
    public double Next3CandlesProb { get; set; }
    [JsonPropertyName("next_5_candles_prob")]
    public double Next5CandlesProb { get; set; }
    [JsonPropertyName("next_10_candles_prob")]
    public double Next10CandlesProb { get; set; }
    [JsonPropertyName("estimated_range_percent")]
    public double EstimatedRangePercent { get; set; }
    [JsonPropertyName("regime")]
    public string Regime { get; set; }
    [JsonPropertyName("volume_explosion")]
    public bool VolumeExplosion { get; set; }
    [JsonPropertyName("group_scores")]
    public Nexus5GroupScoresModel GroupScores { get; set; }
    [JsonPropertyName("features")]
    public Nexus5FeaturesModel Features { get; set; }
    [JsonPropertyName("detectivity")]
    public Dictionary<string, string> Detectivity { get; set; }
}

public class Nexus5GroupScoresModel
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

public class Nexus5FeaturesModel
{
    // G1: Price Action — Ruptura Sniper
    [JsonPropertyName("compression_range")]
    public double CompressionRange { get; set; }
    [JsonPropertyName("ignition_candle")]
    public bool IgnitionCandle { get; set; }
    [JsonPropertyName("efficiency_check")]
    public double EfficiencyCheck { get; set; }
    // G2: SMC/ICT — Desplazamiento
    [JsonPropertyName("displacement_fvg")]
    public bool DisplacementFvg { get; set; }
    [JsonPropertyName("micro_choch")]
    public bool MicroChoch { get; set; }
    [JsonPropertyName("instant_order_block")]
    public bool InstantOrderBlock { get; set; }
    // G3: Wyckoff — Fases de Resorte
    [JsonPropertyName("compression_zone")]
    public bool CompressionZone { get; set; }
    [JsonPropertyName("sos_detected")]
    public bool SosDetected { get; set; }
    [JsonPropertyName("jumping_creek")]
    public bool JumpingCreek { get; set; }
    // G4: Fractales — Micro-Tendencia
    [JsonPropertyName("fractal_high_break")]
    public bool FractalHighBreak { get; set; }
    [JsonPropertyName("ema7_angle")]
    public double Ema7Angle { get; set; }
    [JsonPropertyName("hh_hl_sequence")]
    public bool HhHlSequence { get; set; }
    // G5: Volume & Order Flow
    [JsonPropertyName("relative_vol_multiplier")]
    public double RelativeVolMultiplier { get; set; }
    [JsonPropertyName("vol_intensity")]
    public double VolIntensity { get; set; }
    [JsonPropertyName("buying_imbalance")]
    public double BuyingImbalance { get; set; }
    // G6: ML — Anomalías
    [JsonPropertyName("atr_expansion")]
    public double AtrExpansion { get; set; }
    [JsonPropertyName("z_score")]
    public double ZScore { get; set; }
    [JsonPropertyName("rsi_velocity")]
    public double RsiVelocity { get; set; }

    // ── ESTRUCTURAL ANALYSIS — Reglas de Oro (v8.0) ───────────────────────────
    [JsonPropertyName("slope_ma50")]
    public double SlopeMa50 { get; set; }
    [JsonPropertyName("slope_ma99")]
    public double SlopeMa99 { get; set; }
    [JsonPropertyName("gravity_ma99_safe")]
    public bool GravityMa99Safe { get; set; }
    [JsonPropertyName("vol_ratio")]
    public double VolRatio { get; set; }
    [JsonPropertyName("compression_viper")]
    public bool CompressionViper { get; set; }
    [JsonPropertyName("ma50_horizontal")]
    public bool Ma50Horizontal { get; set; }
    [JsonPropertyName("ma50_ma99_distance")]
    public double Ma50Ma99Distance { get; set; }
    [JsonPropertyName("price_to_ma99_pct")]
    public double PriceToMa99Pct { get; set; }
}

public interface IPythonNexus5Service
{
    Task<Nexus5ResponseModel?> AnalyzeNexus5Async(string symbol, List<MarketCandleModel> candles);
}
