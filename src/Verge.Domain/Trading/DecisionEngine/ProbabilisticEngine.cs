using System;
using System.Linq;
using System.Threading.Tasks;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.DecisionEngine;

public class ProbabilisticEngine : DomainService, IProbabilisticEngine
{
    private readonly IRepository<TradingSession, Guid> _sessionRepository;

    public ProbabilisticEngine(IRepository<TradingSession, Guid> sessionRepository)
    {
        _sessionRepository = sessionRepository;
    }

    public async Task<WinRateResult> GetWinRateAsync(
        TradingStyle style, 
        string symbol, 
        MarketRegimeType regime, 
        int score, 
        DateTime entryTime)
    {
        var query = await _sessionRepository.GetQueryableAsync();

        // 1. Core Filters: Closed sessions with the same style
        var baseQuery = query.Where(s => !s.IsActive && s.Outcome != null && s.SelectedStyle == style);

        // 2. Contextual Filters (Softened to ensure some sample size)
        var contextualSessions = baseQuery.Where(s => 
            s.InitialRegime == regime && 
            Math.Abs((s.InitialScore ?? 0) - score) <= 15).ToList();

        // 3. Time-based dimensionality (NY, London, Asia)
        string timeWindow = GetTimeWindow(entryTime);
        var matchingSessions = contextualSessions.Where(s => 
            s.EntryHour.HasValue && GetTimeWindowFromHour(s.EntryHour.Value) == timeWindow).ToList();

        // 4. Calculation
        int total = matchingSessions.Count;
        if (total < 5) // Fallback to broader context if sample size is too small
        {
            matchingSessions = contextualSessions;
            total = matchingSessions.Count;
        }

        if (total == 0)
        {
            return new WinRateResult { Probability = 0.5, SampleSize = 0, ConfidenceLevel = "Low" };
        }

        int wins = matchingSessions.Count(s => s.Outcome == TradeStatus.Win);
        double probability = (double)wins / total;

        return new WinRateResult
        {
            Probability = Math.Round(probability, 2),
            SampleSize = total,
            ConfidenceLevel = total > 20 ? "High" : (total > 10 ? "Medium" : "Low")
        };
    }

    private string GetTimeWindow(DateTime time)
    {
        return GetTimeWindowFromHour(time.Hour);
    }

    private string GetTimeWindowFromHour(int hour)
    {
        if (hour >= 13 && hour < 21) return "NY";
        if (hour >= 8 && hour < 16) return "London";
        return "Asia";
    }
}
