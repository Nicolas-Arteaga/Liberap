using System.Collections.Generic;

namespace Verge.Trading.Scar;

public class ScarResultDto
{
    public string Symbol { get; set; }
    public int ScoreGrial { get; set; }           // 0 a 5
    public string Prediction { get; set; }        // "PUMP INMINENTE", "En monitoreo", "Sin señal"
    public int? EstimatedHours { get; set; }

    public bool FlagWhaleWithdrawal { get; set; }
    public bool FlagSupplyDrying { get; set; }
    public bool FlagPriceStable { get; set; }
    public bool FlagFundingNegative { get; set; }
    public bool FlagSilence { get; set; }

    public int? DaysSinceLastPump { get; set; }
    public string EstimatedNextWindow { get; set; }
    public int WithdrawalDaysCount { get; set; }
    public double TotalWithdrawnUsd { get; set; }
    public string Mode { get; set; }              // "degraded" | "onchain"
    public string AnalyzedAt { get; set; }
}

public class ScarTopSetupDto
{
    public string Symbol { get; set; }
    public int ScoreGrial { get; set; }
    public string Prediction { get; set; }
    public int? EstimatedHours { get; set; }
    public string Mode { get; set; }
}
