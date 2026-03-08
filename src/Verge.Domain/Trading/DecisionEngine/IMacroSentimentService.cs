using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading.DecisionEngine;

public interface IMacroSentimentService
{
    Task<MacroAnalysisResult> GetMacroSentimentAsync();
    Task SyncEconomicCalendarAsync();
}

public class MacroAnalysisResult
{
    public List<MacroEvent> ActiveEvents { get; set; } = new();
    public List<MacroEvent> UpcomingEvents { get; set; } = new();
    public bool IsInQuietPeriod { get; set; }
    public string QuietPeriodReason { get; set; }
    public DateTime? NextHighImpactEventTime { get; set; }
    public int FearAndGreedIndex { get; set; }
}

public class MacroEvent
{
    public string Name { get; set; } // CPI, FED Interest Rate, NFP
    public string Impact { get; set; } // High, Medium, Low
    public DateTime EventTime { get; set; }
    public string Currency { get; set; } // USD, EUR, etc.
}
