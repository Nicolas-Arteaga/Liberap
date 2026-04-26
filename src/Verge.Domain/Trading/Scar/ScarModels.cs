using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Verge.Trading.Scar;

public class ScarResponseModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }

    [JsonPropertyName("score_grial")]
    public int ScoreGrial { get; set; }

    [JsonPropertyName("prediction")]
    public string Prediction { get; set; }

    [JsonPropertyName("estimated_hours")]
    public int? EstimatedHours { get; set; }

    [JsonPropertyName("flag_whale_withdrawal")]
    public bool FlagWhaleWithdrawal { get; set; }

    [JsonPropertyName("flag_supply_drying")]
    public bool FlagSupplyDrying { get; set; }

    [JsonPropertyName("flag_price_stable")]
    public bool FlagPriceStable { get; set; }

    [JsonPropertyName("flag_funding_negative")]
    public bool FlagFundingNegative { get; set; }

    [JsonPropertyName("flag_silence")]
    public bool FlagSilence { get; set; }

    [JsonPropertyName("days_since_last_pump")]
    public int? DaysSinceLastPump { get; set; }

    [JsonPropertyName("estimated_next_window")]
    public string EstimatedNextWindow { get; set; }

    [JsonPropertyName("withdrawal_days_count")]
    public int WithdrawalDaysCount { get; set; }

    [JsonPropertyName("total_withdrawn_usd")]
    public double TotalWithdrawnUsd { get; set; }

    [JsonPropertyName("mode")]
    public string Mode { get; set; }

    [JsonPropertyName("analyzed_at")]
    public string AnalyzedAt { get; set; }
}

public class ScarTopSetupModel
{
    [JsonPropertyName("symbol")]
    public string Symbol { get; set; }

    [JsonPropertyName("score_grial")]
    public int ScoreGrial { get; set; }

    [JsonPropertyName("prediction")]
    public string Prediction { get; set; }

    [JsonPropertyName("estimated_hours")]
    public int? EstimatedHours { get; set; }

    [JsonPropertyName("mode")]
    public string Mode { get; set; }
}

public class ScarPredictionModel
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("token_symbol")]
    public string TokenSymbol { get; set; }

    [JsonPropertyName("alert_date")]
    public string AlertDate { get; set; }

    [JsonPropertyName("score_grial")]
    public int ScoreGrial { get; set; }

    [JsonPropertyName("price_at_alert")]
    public double PriceAtAlert { get; set; }

    [JsonPropertyName("estimated_hours")]
    public int? EstimatedHours { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; }

    [JsonPropertyName("max_price_24h")]
    public double? MaxPrice24h { get; set; }

    [JsonPropertyName("pattern_detected")]
    public int PatternDetected { get; set; }

    [JsonPropertyName("trader_roi_pct")]
    public double TraderRoiPct { get; set; }

    [JsonPropertyName("result_date")]
    public string? ResultDate { get; set; }
}

public class ScarAccuracyModel
{
    [JsonPropertyName("token_symbol")]
    public string? TokenSymbol { get; set; }

    [JsonPropertyName("total_predictions")]
    public int TotalPredictions { get; set; }

    [JsonPropertyName("total_hits")]
    public int TotalHits { get; set; }

    [JsonPropertyName("total_false_alarms")]
    public int TotalFalseAlarms { get; set; }

    [JsonPropertyName("system_hit_rate")]
    public double SystemHitRate { get; set; }

    [JsonPropertyName("avg_trader_roi")]
    public double AvgTraderRoi { get; set; }

    [JsonPropertyName("last_updated")]
    public string LastUpdated { get; set; }
}

public class ScarTemplateAdjustmentModel
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("token_symbol")]
    public string TokenSymbol { get; set; }

    [JsonPropertyName("adjustment_date")]
    public string AdjustmentDate { get; set; }

    [JsonPropertyName("old_avg_days")]
    public double OldAvgDays { get; set; }

    [JsonPropertyName("new_avg_days")]
    public double NewAvgDays { get; set; }

    [JsonPropertyName("reason")]
    public string Reason { get; set; }
}
