using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Verge.Trading.DecisionEngine.Cache;
using Verge.Trading.DecisionEngine.Factory;
using Verge.Trading.DecisionEngine.Profiles;
using Volo.Abp.DependencyInjection;

namespace Verge.Trading.DecisionEngine;

public class AutoEvaluatorService : ITransientDependency
{
    private readonly ITradingDecisionEngine _engine;
    private readonly MarketSnapshotCache _cache;
    private readonly ILogger<AutoEvaluatorService> _logger;

    public AutoEvaluatorService(
        ITradingDecisionEngine engine,
        MarketSnapshotCache cache,
        ILogger<AutoEvaluatorService> logger)
    {
        _engine = engine;
        _cache = cache;
        _logger = logger;
    }

    public async Task<AutoEvaluationResult?> FindBestOpportunityAsync(
        TradingSession session, 
        TradingStrategy strategy, 
        Dictionary<(string symbol, string timeframe), MarketContext> dataCache)
    {
        var symbols = strategy.IsAutoMode || session.Symbol == "AUTO" 
            ? strategy.GetSelectedCryptos() 
            : new List<string> { session.Symbol };

        if (!symbols.Any()) symbols = new List<string> { "BTCUSDT" };

        var styles = strategy.Style == TradingStyle.Auto
            ? new[] { TradingStyle.Scalping, TradingStyle.DayTrading, TradingStyle.SwingTrading, TradingStyle.PositionTrading, TradingStyle.GridTrading, TradingStyle.HODL }
            : new[] { strategy.Style };

        var directions = strategy.DirectionPreference == SignalDirection.Auto
            ? new[] { SignalDirection.Long, SignalDirection.Short }
            : new[] { strategy.DirectionPreference };

        AutoEvaluationResult? best = null;
        var timeframe = session.Timeframe;

        foreach (var symbol in symbols)
        {
            if (!dataCache.TryGetValue((symbol, timeframe), out var context)) continue;

            foreach (var style in styles)
            {
                var profile = TradingStyleProfileFactory.GetProfile(style);
                
                // Temporary Symbol switch for evaluation (DecisionEngine uses session.Symbol in logs/reasons)
                var originalSymbol = session.Symbol;
                session.Symbol = symbol;

                foreach (var direction in directions)
                {
                    var evalResult = _engine.Evaluate(session, style, context);
                    
                    if (best == null || evalResult.Score > best.Result.Score)
                    {
                        best = new AutoEvaluationResult
                        {
                            Symbol = symbol,
                            Style = style,
                            Direction = direction,
                            Result = evalResult,
                            Context = context
                        };

                        // Early Exit: If we found a very strong entry (> Threshold + 10), we stop searching
                        if (evalResult.Decision == TradingDecision.Entry && evalResult.Score >= profile.EntryThreshold + 10)
                        {
                            _logger.LogInformation("🚀 Early exit triggered for AUTO session {Id}: Found excellent setup on {Symbol} with {Style}", session.Id, symbol, style);
                            session.Symbol = originalSymbol; // Restore before exit
                            return best;
                        }
                    }
                }
                session.Symbol = originalSymbol; // Restore
            }
        }

        return best;
    }
}

public class AutoEvaluationResult
{
    public string Symbol { get; set; } = string.Empty;
    public TradingStyle Style { get; set; }
    public SignalDirection Direction { get; set; }
    public DecisionResult Result { get; set; } = null!;
    public MarketContext Context { get; set; } = null!;
}
