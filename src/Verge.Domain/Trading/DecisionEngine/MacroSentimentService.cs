using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Verge.Trading.DecisionEngine;

public class MacroSentimentService : IMacroSentimentService
{
    private List<MacroEvent> _cachedEvents = new();
    private DateTime _lastSync = DateTime.MinValue;

    public async Task<MacroAnalysisResult> GetMacroSentimentAsync()
    {
        // Ensure we have some mock events if sync never ran
        if (!_cachedEvents.Any()) await SyncEconomicCalendarAsync();

        var now = DateTime.UtcNow;
        var result = new MacroAnalysisResult();

        // 1. Find High Impact events within 30 minutes (Quiet Period)
        var highImpactUpcoming = _cachedEvents
            .Where(e => e.Impact == "High" && e.EventTime > now && e.EventTime <= now.AddMinutes(30))
            .ToList();

        var highImpactActive = _cachedEvents
            .Where(e => e.Impact == "High" && e.EventTime <= now && now <= e.EventTime.AddMinutes(30))
            .ToList();

        if (highImpactUpcoming.Any())
        {
            result.IsInQuietPeriod = true;
            result.QuietPeriodReason = $"📅 QUIET PERIOD: High impact event '{highImpactUpcoming.First().Name}' in {Math.Round((highImpactUpcoming.First().EventTime - now).TotalMinutes)} mins.";
        }
        else if (highImpactActive.Any())
        {
            result.IsInQuietPeriod = true;
            result.QuietPeriodReason = $"📅 QUIET PERIOD: High impact event '{highImpactActive.First().Name}' currently active. Cooling down for 30m.";
        }

        result.ActiveEvents = highImpactActive;
        result.UpcomingEvents = _cachedEvents.Where(e => e.EventTime > now).OrderBy(e => e.EventTime).Take(5).ToList();
        result.NextHighImpactEventTime = _cachedEvents.Where(e => e.Impact == "High" && e.EventTime > now).OrderBy(e => e.EventTime).Select(e => e.EventTime).FirstOrDefault();

        return result;
    }

    public Task SyncEconomicCalendarAsync()
    {
        // SIMULATION: Sync with API (e.g., ForexFactory, Investing.com RSS)
        // For development, we create fake recurring tokens for high volatility.
        var today = DateTime.UtcNow.Date;
        
        _cachedEvents = new List<MacroEvent>
        {
            new MacroEvent { Name = "FED Interest Rate Decision", Impact = "High", Currency = "USD", EventTime = today.AddHours(14).AddMinutes(30).ToUniversalTime() },
            new MacroEvent { Name = "CPI Data Release", Impact = "High", Currency = "USD", EventTime = today.AddHours(10).AddMinutes(30).ToUniversalTime() },
            new MacroEvent { Name = "NFP Employment Report", Impact = "High", Currency = "USD", EventTime = today.AddDays(1).AddHours(8).ToUniversalTime() },
            new MacroEvent { Name = "EU Central Bank Speech", Impact = "Medium", Currency = "EUR", EventTime = today.AddHours(11).ToUniversalTime() }
        };

        _lastSync = DateTime.UtcNow;
        return Task.CompletedTask;
    }
}
