using System.Collections.Generic;

namespace Verge.Trading.Scar;

public class ScarPredictionDto
{
    public int Id { get; set; }
    public string TokenSymbol { get; set; }
    public string AlertDate { get; set; }
    public int ScoreGrial { get; set; }
    public double PriceAtAlert { get; set; }
    public int? EstimatedHours { get; set; }
    public string Status { get; set; }   // pending | hit | hit_strong | false_alarm | manual_override
    public double? MaxPrice24h { get; set; }
    public int PatternDetected { get; set; }
    public double TraderRoiPct { get; set; }
    public string? ResultDate { get; set; }
}

public class ScarAccuracyDto
{
    public string? TokenSymbol { get; set; }    // null = global
    public int TotalPredictions { get; set; }
    public int TotalHits { get; set; }
    public int TotalFalseAlarms { get; set; }
    public double SystemHitRate { get; set; }
    public double AvgTraderRoi { get; set; }
    public string LastUpdated { get; set; }
}

public class ScarFeedbackRequest
{
    public string Result { get; set; }  // "hit" | "false_alarm" | "ignore"
}

public class ScarTemplateAdjustmentDto
{
    public int Id { get; set; }
    public string TokenSymbol { get; set; }
    public string AdjustmentDate { get; set; }
    public double OldAvgDays { get; set; }
    public double NewAvgDays { get; set; }
    public string Reason { get; set; }
}
