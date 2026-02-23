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
                // 4.0 Check for TP/SL Exits (Sprint 1)
                if (session.CurrentStage == TradingStage.BuyActive)
                {
                    bool exited = await CheckTradeExitsAsync(session, strategy, groupDataCache, sessionRepository, analysisLogRepo);
                    if (exited) continue;
                }

                // 4.1 Evaluation Logic: Multidimensional AUTO or Generic
                bool isAutoMode = session.Symbol == "AUTO" || 
                                  strategy.Style == TradingStyle.Auto || 
                                  strategy.DirectionPreference == SignalDirection.Auto;

                if (!isAutoMode)
                {
                    var groupKey = (session.Symbol, session.Timeframe);
                    if (!groupDataCache.TryGetValue(groupKey, out var data)) continue;

                    // 4.0.1 Incremental Evaluation (Sprint 3)
                    var lastCandleTime = data.candles.Last().Timestamp;
                    if (session.LastEvaluationTimestamp.HasValue && session.LastEvaluationTimestamp.Value >= lastCandleTime)
                    {
                        _logger.LogInformation("⏩ Skipping evaluation for {Symbol}: Data unchanged since {Time}", session.Symbol, lastCandleTime);
                        continue;
                    }


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

                    // Update timestamp (Sprint 3)
                    session.LastEvaluationTimestamp = data.candles.Last().Timestamp;

                    // Always update session to persist History (Phase 2)
                    await sessionRepository.UpdateAsync(session);
                }
                else
                {
                    // NEW: Multidimensional AUTO Evaluator with Ranking (Phase 3)
                    var contextsOnly = groupDataCache.ToDictionary(k => k.Key, v => v.Value.context);
                    
                    // Fetch top opportunities for ranking
                    var allOpportunities = await autoEvaluator.FindTopOpportunitiesAsync(session, strategy, contextsOnly, 10);
                    var bestOpportunity = allOpportunities.FirstOrDefault();

                    // 1. Log Opportunity Ranking (Top 3)
                    var top3 = allOpportunities.Take(3).ToList();
                    if (top3.Any())
                    {
                        var rankingData = new {
                            top = top3.Select(o => new {
                                symbol = o.Symbol,
                                style = o.Style.ToString(),
                                direction = o.Direction.ToString(),
                                score = o.Result.Score,
                                confidence = o.Result.Confidence.ToString()
                            }).ToList()
                        };

                        var rankingLog = new AnalysisLog(
                            Guid.NewGuid(),
                            session.TraderProfileId,
                            session.Id,
                            "AUTO",
                            "📈 Top 3 Oportunidades detectadas",
                            "info",
                            DateTime.UtcNow,
                            AnalysisLogType.OpportunityRanking,
                            JsonSerializer.Serialize(rankingData)
                        );
                        await analysisLogRepo.InsertAsync(rankingLog);
                    }

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
                            // If we enter or prepare, we adopt the winning symbol, style, and direction
                            if (best.Result.Decision >= DecisionEngine.TradingDecision.Prepare)
                            {
                                session.Symbol = best.Symbol;
                                session.SelectedStyle = best.Style;
                                session.SelectedDirection = best.Direction;
                            }

                            bool stageChanged = ProcessDecision(session, best.Result, strategy, best.Context.Candles.Last().Close);
                        }

                        // Update timestamp for AUTO mode too (Sprint 3)
                        var maxTs = contextsOnly.Values.Max(c => c.Candles.Last().Timestamp);
                        session.LastEvaluationTimestamp = maxTs;

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
        // Use Adopted Direction if available, fallback to Strategy preference
        var direction = session.SelectedDirection ?? strategy.DirectionPreference;
        bool isLong = direction == SignalDirection.Long;
        
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
        // 1. Determine LogType based on Decision and Reason
        AnalysisLogType logType = AnalysisLogType.Standard;
        
        if (result.Reason.Contains("INVALIDATED"))
        {
            logType = AnalysisLogType.AlertInvalidated;
        }
        else
        {
            logType = result.Decision switch {
                DecisionEngine.TradingDecision.Entry => AnalysisLogType.AlertEntry,
                DecisionEngine.TradingDecision.Prepare => AnalysisLogType.AlertPrepare,
                DecisionEngine.TradingDecision.Context => result.Score >= 60 ? AnalysisLogType.AlertContext : AnalysisLogType.Standard,
                _ => AnalysisLogType.Standard
            };
        }

        // 2. Build Message with Emoji
        string emoji = logType switch {
            AnalysisLogType.AlertEntry => "🚀",
            AnalysisLogType.AlertPrepare => "⚡",
            AnalysisLogType.AlertContext => "🔍",
            AnalysisLogType.AlertInvalidated => "❌",
            AnalysisLogType.AlertExit => "💰",
            _ => "💤"
        };

        string confidenceLabel = result.Confidence.ToString().ToUpper();
        string message = $"{emoji} [{result.Decision}] Score: {result.Score}/100 | Confianza: {confidenceLabel} | Regimen: {context.MarketRegime?.Regime.ToString() ?? "N/A"} | Price: ${price:N2}";

        if (result.Decision >= DecisionEngine.TradingDecision.Prepare && result.EntryMinPrice.HasValue && result.EntryMaxPrice.HasValue)
        {
            message += $" | 🎯 Target: ${result.EntryMinPrice:N2}-${result.EntryMaxPrice:N2}";
        }

        if (logType == AnalysisLogType.AlertInvalidated)
        {
            message = result.Reason; // Keep the alert clear for invalidations
        }

        // 3. Enrich DataJson with Metadata
        var logData = new {
            score = result.Score,
            decision = result.Decision.ToString(),
            confidence = result.Confidence.ToString(),
            regime = context.MarketRegime?.Regime,
            rsi = context.Technicals?.Rsi,
            adx = context.Technicals?.Adx,
            fng = context.FearAndGreed?.Value,
            reason = result.Reason,
            weighted = result.WeightedScores,
            htfTrend = context.HigherTimeframeContext?.MarketRegime?.Regime.ToString(),
            entryMin = result.EntryMinPrice,
            entryMax = result.EntryMaxPrice
        };

        var log = new AnalysisLog(
            Guid.NewGuid(),
            session.TraderProfileId,
            session.Id,
            session.Symbol,
            message,
            result.Score >= 70 ? "success" : (result.Score >= 50 ? "warning" : "info"),
            DateTime.UtcNow,
            logType,
            JsonSerializer.Serialize(logData)
        );

        await repo.InsertAsync(log);
    }

    private async Task<bool> CheckTradeExitsAsync(
        TradingSession session, 
        TradingStrategy strategy, 
        Dictionary<(string symbol, string timeframe), (List<MarketCandleModel> candles, DecisionEngine.MarketContext context)> groupDataCache,
        IRepository<TradingSession, Guid> sessionRepo,
        IRepository<AnalysisLog, Guid> logRepo)
    {
        if (!groupDataCache.TryGetValue((session.Symbol, session.Timeframe), out var data)) return false;
        
        var currentPrice = data.candles.Last().Close;
        var direction = session.SelectedDirection ?? strategy.DirectionPreference;
        bool isLong = direction == SignalDirection.Long;
        
        bool exitTriggered = false;
        string exitMessage = "";
        
        if (isLong)
        {
            if (session.TakeProfitPrice.HasValue && currentPrice >= session.TakeProfitPrice.Value)
            {
                exitTriggered = true;
                exitMessage = $"💰 Take Profit alcanzado! Precio: ${currentPrice:N2}";
            }
            else if (session.StopLossPrice.HasValue && currentPrice <= session.StopLossPrice.Value)
            {
                exitTriggered = true;
                exitMessage = $"🛑 Stop Loss activado. Precio: ${currentPrice:N2}";
            }
        }
        else // SHORT
        {
            if (session.TakeProfitPrice.HasValue && currentPrice <= session.TakeProfitPrice.Value)
            {
                exitTriggered = true;
                exitMessage = $"💰 Take Profit alcanzado! Precio: ${currentPrice:N2}";
            }
            else if (session.StopLossPrice.HasValue && currentPrice >= session.StopLossPrice.Value)
            {
                exitTriggered = true;
                exitMessage = $"🛑 Stop Loss activado. Precio: ${currentPrice:N2}";
            }
        }
        
        if (exitTriggered)
        {
            _logger.LogInformation("📉 Exit Triggered for {Symbol}: {Message}", session.Symbol, exitMessage);
            
            // Calculate Telemetry (Sprint 2)
            decimal netProfit = 0;
            if (session.EntryPrice.HasValue && session.EntryPrice.Value > 0)
            {
                var entryPrice = session.EntryPrice.Value;
                var leverage = (decimal)strategy.Leverage;
                var capital = strategy.Capital;
                var quantity = (capital * leverage) / entryPrice;
                
                if (isLong)
                    netProfit = (currentPrice - entryPrice) * quantity;
                else
                    netProfit = (entryPrice - currentPrice) * quantity;
            }

            session.CurrentStage = TradingStage.SellActive;
            session.IsActive = false; // Deactivate once finished
            session.EndTime = DateTime.UtcNow;
            session.NetProfit = netProfit;
            session.Outcome = netProfit >= 0 ? TradeStatus.Win : TradeStatus.Loss;
            session.ExitReason = exitMessage.Contains("Profit") ? "TakeProfit" : "StopLoss";
            
            await sessionRepo.UpdateAsync(session);
            
            var exitLog = new AnalysisLog(
                Guid.NewGuid(),
                session.TraderProfileId,
                session.Id,
                session.Symbol,
                $"{exitMessage} | Ganancia: ${netProfit:N2} USDT",
                netProfit >= 0 ? "success" : "danger",
                DateTime.UtcNow,
                AnalysisLogType.AlertExit,
                JsonSerializer.Serialize(new { 
                    price = currentPrice, 
                    reason = session.ExitReason,
                    netProfit = netProfit,
                    outcome = session.Outcome.ToString()
                })
            );
            await logRepo.InsertAsync(exitLog);
            return true;
        }
        
        return false;
    }
}
