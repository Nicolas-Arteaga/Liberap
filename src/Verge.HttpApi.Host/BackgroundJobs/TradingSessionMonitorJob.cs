using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;
using Verge.Trading.DTOs;
using Verge.Trading.Integrations;
using Verge.Trading.DecisionEngine;
using Verge.Trading.DecisionEngine.Cache;
using Verge.Trading.DecisionEngine.Factory;

namespace Verge.Trading;

public class TradingSessionMonitorJob : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<TradingSessionMonitorJob> _logger;

    public TradingSessionMonitorJob(IServiceProvider serviceProvider, ILogger<TradingSessionMonitorJob> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 Trading Session Monitor Job started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            _logger.LogInformation("⏰ Job cycle starting at {time}", DateTime.UtcNow);
            try
            {
                await MonitorActiveSessionsAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in job cycle");
            }

            _logger.LogInformation("😴 Job sleeping for 30 seconds...");
            await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
    }

    private async Task MonitorActiveSessionsAsync()
    {
        _logger.LogInformation("🔍 MonitorActiveSessionsAsync() (Phase 2) starting...");

        using var scope = _serviceProvider.CreateScope();
        var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var pythonService = scope.ServiceProvider.GetRequiredService<IPythonIntegrationService>();
        var fngService = scope.ServiceProvider.GetRequiredService<IFearAndGreedService>();
        var freeNewsService = scope.ServiceProvider.GetRequiredService<IFreeCryptoNewsService>();
        var geckoService = scope.ServiceProvider.GetRequiredService<ICoinGeckoService>();
        var decisionEngine = scope.ServiceProvider.GetRequiredService<ITradingDecisionEngine>();
        var autoEvaluator = scope.ServiceProvider.GetRequiredService<AutoEvaluatorService>();
        var snapshotCache = scope.ServiceProvider.GetRequiredService<MarketSnapshotCache>();
        var analysisLogRepo = scope.ServiceProvider.GetRequiredService<IRepository<AnalysisLog, Guid>>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

        using var uow = unitOfWorkManager.Begin();

        var activeSessions = await sessionRepository.GetListAsync(x => x.IsActive && x.CurrentStage < TradingStage.SellActive);
        if (!activeSessions.Any())
        {
            _logger.LogInformation("ℹ️ No active sessions found.");
            return;
        }

        // 1. Fetch GLOBAL Macro Data (Once per cycle)
        _logger.LogInformation("🌍 Fetching Global Macro Data...");
        var fng = await fngService.GetCurrentFearAndGreedAsync();
        
        // 2. Discovery: Identify all required Symbol/Timeframe pairs
        var requiredGroups = new HashSet<(string symbol, string timeframe)>();
        var sessionStrategies = new Dictionary<Guid, TradingStrategy>(); // SessionId -> Strategy

        foreach (var session in activeSessions)
        {
            var strategy = await strategyRepository.FirstOrDefaultAsync(x => x.TraderProfileId == session.TraderProfileId && x.IsActive);
            if (strategy == null) continue;
            sessionStrategies[session.Id] = strategy;

            if (session.Symbol != "AUTO")
            {
                requiredGroups.Add((session.Symbol, session.Timeframe));
            }
            else
            {
                var candidates = strategy.GetSelectedCryptos();
                if (candidates == null || !candidates.Any())
                {
                    _logger.LogWarning("⚠️ AUTO session {Id} for TraderProfile {ProfileId} has no portfolio coins configured.", session.Id, strategy.TraderProfileId);
                    continue;
                }
                
                foreach (var symbol in candidates)
                {
                    requiredGroups.Add((symbol, session.Timeframe));
                    
                    // Discover HTF for AUTO candidates
                    var profile = TradingStyleProfileFactory.GetProfile(strategy.Style);
                    var htf = profile.GetConfirmationTimeframe(session.Timeframe);
                    if (!string.IsNullOrEmpty(htf) && htf != session.Timeframe)
                    {
                        requiredGroups.Add((symbol, htf));
                    }
                }
            }

            // Identify HTF for non-AUTO sessions
            var sessionProfile = TradingStyleProfileFactory.GetProfile(strategy.Style);
            var sessionHtf = sessionProfile.GetConfirmationTimeframe(session.Timeframe);
            if (!string.IsNullOrEmpty(sessionHtf) && sessionHtf != session.Timeframe && session.Symbol != "AUTO")
            {
                requiredGroups.Add((session.Symbol, sessionHtf));
            }
        }

        // 3. Batch Fetching: Fetch data for all required groups
        var groupDataCache = new Dictionary<(string symbol, string timeframe), (List<MarketCandleModel> candles, DecisionEngine.MarketContext context)>();

        foreach (var group in requiredGroups)
        {
            try
            {
                var symbol = group.symbol;
                var timeframe = group.timeframe;

                // 3.1 Check Cache First (Optimizations)
                var candles = await marketDataManager.GetCandlesAsync(symbol, timeframe, 100);
                if (candles == null || !candles.Any()) continue;

                var lastCandleTimestamp = candles.Max(c => c.Timestamp);
                var cachedContext = await snapshotCache.GetAsync(symbol, timeframe, lastCandleTimestamp);
                
                if (cachedContext != null)
                {
                    groupDataCache[group] = (candles, cachedContext);
                    _logger.LogDebug("📦 Cache hit for {Symbol} {Timeframe}", symbol, timeframe);
                    continue;
                }

                _logger.LogInformation("📉 Fetching Fresh Data for {Symbol} {Timeframe}...", symbol, timeframe);
                var oi = await marketDataManager.GetOpenInterestAsync(symbol);
                var gecko = await geckoService.GetTokenDataAsync(symbol);
                var newsResult = await freeNewsService.GetNewsAsync(symbol);
                var news = newsResult?.News ?? new List<CryptoNewsItem>();
                
                var sentiment = await freeNewsService.GetSentimentAsync(symbol);

                var regime = await pythonService.DetectMarketRegimeAsync(symbol, timeframe, candles);
                var technicals = await pythonService.AnalyzeTechnicalsAsync(symbol, timeframe, candles);

                var context = new DecisionEngine.MarketContext
                {
                    FearAndGreed = fng,
                    News = news,
                    GlobalSentiment = sentiment,
                    CoinGeckoData = gecko,
                    OpenInterest = oi,
                    MarketRegime = regime,
                    Technicals = technicals,
                    Candles = candles
                };

                // Store in Cache
                await snapshotCache.SetAsync(symbol, timeframe, lastCandleTimestamp, context);
                groupDataCache[group] = (candles, context);
            }
            catch (Exception ex)
            {
                _logger.LogWarning($"⚠️ Failed to fetch data for {group.symbol} {group.timeframe}: {ex.Message}");
            }
        }

        // 4. Evaluation: Process each session
        foreach (var session in activeSessions)
        {
            if (!sessionStrategies.TryGetValue(session.Id, out var strategy)) continue;

            try
            {
                // 4.1 Evaluation Logic: Multidimensional AUTO or Generic
                bool isAutoMode = session.Symbol == "AUTO" || 
                                  strategy.Style == TradingStyle.Auto || 
                                  strategy.DirectionPreference == SignalDirection.Auto;

                if (!isAutoMode)
                {
                    var groupKey = (session.Symbol, session.Timeframe);
                    if (!groupDataCache.TryGetValue(groupKey, out var data)) continue;

                    // Attach HTF Context if exists
                    var profile = TradingStyleProfileFactory.GetProfile(strategy.Style);
                    var htfName = profile.GetConfirmationTimeframe(session.Timeframe);
                    var htfKey = (session.Symbol, htfName);
                    
                    if (groupDataCache.TryGetValue(htfKey, out var htfData))
                    {
                        data.context.HigherTimeframeContext = htfData.context;
                    }

                    var evalResult = decisionEngine.Evaluate(session, strategy.Style, data.context);
                    bool stageChanged = ProcessDecision(session, evalResult, strategy, data.candles.Last().Close);
                    await CreateAnalysisLogAsync(analysisLogRepo, session, evalResult, data.candles.Last().Close, data.context);

                    // Always update session to persist History (Phase 2)
                    await sessionRepository.UpdateAsync(session);
                }
                else
                {
                    // NEW: Multidimensional AUTO Evaluator
                    var contextsOnly = groupDataCache.ToDictionary(k => k.Key, v => v.Value.context);
                    var bestOpportunity = await autoEvaluator.FindBestOpportunityAsync(session, strategy, contextsOnly);

                    if (bestOpportunity != null)
                    {
                        var best = bestOpportunity;
                        _logger.LogInformation("🤖 AUTO winner for Session {Id}: {Symbol} | Style: {Style} | Score: {Score}", 
                            session.Id, best.Symbol, best.Style, best.Result.Score);

                        // ALWAYS persist the analysis log for the best opportunity (consistent with fixed-symbol behavior)
                        await CreateAnalysisLogAsync(analysisLogRepo, session, best.Result, best.Context.Candles.Last().Close, best.Context);

                        // Update session if it's a candidate for action
                        if (best.Result.Decision != DecisionEngine.TradingDecision.Ignore)
                        {
                            // If we enter or prepare, we adopt the winning symbol
                            if (best.Result.Decision >= DecisionEngine.TradingDecision.Prepare)
                            {
                                session.Symbol = best.Symbol;
                            }

                            bool stageChanged = ProcessDecision(session, best.Result, strategy, best.Context.Candles.Last().Close);
                        }

                        // Always update session (persist history and EvaluationHistoryJson)
                        await sessionRepository.UpdateAsync(session);
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error evaluating session {Id} ({Symbol})", session.Id, session.Symbol);
            }
        }

        await uow.CompleteAsync();
        _logger.LogInformation("🏁 Monitoring cycle completed.");
    }

    private bool ProcessDecision(TradingSession session, DecisionEngine.DecisionResult result, TradingStrategy strategy, decimal currentPrice)
    {
        var oldStage = session.CurrentStage;
        bool changed = false;

        switch (result.Decision)
        {
            case DecisionEngine.TradingDecision.Entry:
                if (session.CurrentStage == TradingStage.Evaluating || session.CurrentStage == TradingStage.Prepared)
                {
                    session.CurrentStage = TradingStage.BuyActive;
                    session.EntryPrice = currentPrice;
                    CalculateTargets(session, strategy, currentPrice);
                    changed = true;
                }
                break;

            case DecisionEngine.TradingDecision.Prepare:
                if (session.CurrentStage == TradingStage.Evaluating)
                {
                    session.CurrentStage = TradingStage.Prepared;
                    changed = true;
                }
                break;
        }

        if (changed)
        {
            _logger.LogInformation("🚀 Stage Advanced for {Symbol}: {Old} -> {New} (Score: {Score})", 
                session.Symbol, oldStage, session.CurrentStage, result.Score);
        }

        return changed;
    }

    private void CalculateTargets(TradingSession session, TradingStrategy strategy, decimal currentPrice)
    {
        bool isLong = strategy.DirectionPreference == SignalDirection.Long;
        decimal tpFactor = strategy.TakeProfitPercentage / 100;
        decimal slFactor = strategy.StopLossPercentage / 100;

        if (isLong)
        {
            session.TakeProfitPrice = currentPrice * (1 + tpFactor);
            session.StopLossPrice = currentPrice * (1 - slFactor);
        }
        else
        {
            session.TakeProfitPrice = currentPrice * (1 - tpFactor);
            session.StopLossPrice = currentPrice * (1 + slFactor);
        }
    }

    private async Task CreateAnalysisLogAsync(
        IRepository<AnalysisLog, Guid> repo, 
        TradingSession session, 
        DecisionEngine.DecisionResult result,
        decimal price,
        DecisionEngine.MarketContext context)
    {
        string emoji = result.Decision switch {
            DecisionEngine.TradingDecision.Entry => "🚀",
            DecisionEngine.TradingDecision.Prepare => "⚡",
            DecisionEngine.TradingDecision.Context => "🔍",
            _ => "💤"
        };

        string confidenceLabel = result.Confidence.ToString().ToUpper();
        string message = $"{emoji} [{result.Decision}] Score: {result.Score}/100 | Confianza: {confidenceLabel} | Regimen: {context.MarketRegime?.Regime.ToString() ?? "N/A"} | Price: ${price:N2}";

        if (result.Reason.Contains("INVALIDATED"))
        {
            message = result.Reason; // Keep the alert clear
        }

        var logData = new {
            score = result.Score,
            decision = result.Decision.ToString(),
            confidence = result.Confidence.ToString(),
            regime = context.MarketRegime?.Regime,
            rsi = context.Technicals?.Rsi,
            fng = context.FearAndGreed?.Value,
            reason = result.Reason,
            weighted = result.WeightedScores
        };

        var log = new AnalysisLog(
            Guid.NewGuid(),
            session.TraderProfileId,
            session.Id,
            session.Symbol,
            message,
            result.Score >= 70 ? "success" : (result.Score >= 50 ? "warning" : "info"),
            DateTime.UtcNow,
            JsonSerializer.Serialize(logData)
        );

        await repo.InsertAsync(log);
    }
}
