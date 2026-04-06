using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.DecisionEngine;

public class MacroSentimentService : IMacroSentimentService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<MacroSentimentService> _logger;
    private List<MacroEvent> _cachedEvents = new();
    private int _fearAndGreedIndex = 50;
    private DateTime _lastSync = DateTime.MinValue;

    public MacroSentimentService(IHttpClientFactory httpClientFactory, ILogger<MacroSentimentService> logger)
    {
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task<MacroAnalysisResult> GetMacroSentimentAsync()
    {
        // Auto-sync if more than 1 hour old
        if ((DateTime.UtcNow - _lastSync).TotalHours > 1)
        {
            await SyncEconomicCalendarAsync();
        }

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
        result.FearAndGreedIndex = _fearAndGreedIndex;

        return result;
    }

    public async Task SyncEconomicCalendarAsync()
    {
        _logger.LogInformation("🌍 Syncing Macro Data & Fear/Greed Index...");

        try
        {
            var client = _httpClientFactory.CreateClient();
            
            // 1. Fear & Greed Index from alternative.me
            var fngResponse = await client.GetAsync("https://api.alternative.me/fng/");
            if (fngResponse.IsSuccessStatusCode)
            {
                var content = await fngResponse.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(content);
                var valueStr = doc.RootElement.GetProperty("data")[0].GetProperty("value").GetString();
                if (int.TryParse(valueStr, out int val))
                {
                    _fearAndGreedIndex = val;
                }
            }

            // 2. ECONOMIC CALENDAR (Simulation/Mock for now, as free APIs are limited)
            // In a full implementation, we'd scrape or use a paid/freemium API like Finnhub
            var today = DateTime.UtcNow.Date;
            _cachedEvents = new List<MacroEvent>(); // DISABLED HARDCODED MOCKS TO UNBLOCK SCANNER

            _lastSync = DateTime.UtcNow;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error syncing Macro data");
        }
    }
}
