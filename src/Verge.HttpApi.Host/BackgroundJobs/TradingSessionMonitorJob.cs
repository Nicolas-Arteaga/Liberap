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
using Volo.Abp.EventBus.Distributed;
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
    private readonly ITickSpikeAlerter _spikeAlerter;

    public TradingSessionMonitorJob(IServiceProvider serviceProvider, ILogger<TradingSessionMonitorJob> logger, ITickSpikeAlerter spikeAlerter)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _spikeAlerter = spikeAlerter;
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

            _logger.LogInformation("😴 Job waiting for next cycle or ⚡ pulse spike...");
            
            // Institutional 1% Sprint 1: Wait for 30s OR an instant spike signal
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
            var delayTask = Task.Delay(TimeSpan.FromSeconds(30), cts.Token);
            var spikeTask = _spikeAlerter.WaitAsync(cts.Token);

            var finishedTask = await Task.WhenAny(delayTask, spikeTask);
            cts.Cancel(); // Stop the other task

            if (finishedTask == spikeTask)
            {
                _logger.LogWarning("⚡ [INSTITUTIONAL 1%] REACCIÓN INSTANTÁNEA: Pulso de mercado detectado en {Symbol}. Iniciando re-evaluación forzada.", _spikeAlerter.LastSpikedSymbol);
            }
            else
            {
                _logger.LogInformation("⏰ [STANDARD 10%] Ciclo de 30s completado. Evaluando estado del mercado...");
            }
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
        var profileRepository = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var macroService = scope.ServiceProvider.GetRequiredService<IMacroSentimentService>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();
        var eventBus = scope.ServiceProvider.GetRequiredService<IDistributedEventBus>();

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
        var macroData = await macroService.GetMacroSentimentAsync();
        
        // 2. Discovery: Identify all required Symbol/Timeframe pairs
        var requiredGroups = new HashSet<(string symbol, string timeframe)>();
        var sessionStrategies = new Dictionary<Guid, TradingStrategy>(); // SessionId -> Strategy
        var profileMap = new Dictionary<Guid, TraderProfile>(); // ProfileId -> Profile

        foreach (var session in activeSessions)
        {
            var strategy = await strategyRepository.FirstOrDefaultAsync(x => x.TraderProfileId == session.TraderProfileId && x.IsActive);
            if (strategy == null) continue;
            sessionStrategies[session.Id] = strategy;

            if (!profileMap.ContainsKey(session.TraderProfileId))
            {
                var traderProfile = await profileRepository.GetAsync(session.TraderProfileId);
                profileMap[session.TraderProfileId] = traderProfile;
            }

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
                    var styleProfile = TradingStyleProfileFactory.GetProfile(strategy.Style);
                    var htf = styleProfile.GetConfirmationTimeframe(session.Timeframe);
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
                    MacroData = macroData,
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
                var currentTraderProfile = profileMap[session.TraderProfileId];
                if (session.CurrentStage == TradingStage.BuyActive)
                {
                    bool exited = await CheckTradeExitsAsync(session, strategy, groupDataCache, sessionRepository, analysisLogRepo, eventBus, currentTraderProfile.UserId);
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

                    // 4.0.1 Incremental Evaluation Guard (Sprint 3)
                    // We only skip logging if Data is unchanged and score hasn't decayed enough.
                    var lastCandleTime = data.candles.Last().Timestamp;
                    bool dataUnchanged = session.LastEvaluationTimestamp.HasValue && session.LastEvaluationTimestamp.Value >= lastCandleTime;
                    
                    // Attach HTF Context if exists
                    var styleProfile = TradingStyleProfileFactory.GetProfile(strategy.Style);
                    var htfName = styleProfile.GetConfirmationTimeframe(session.Timeframe);
                    var htfKey = (session.Symbol, htfName);
                    
                    if (groupDataCache.TryGetValue(htfKey, out var htfData))
                    {
                        data.context.HigherTimeframeContext = htfData.context;
                    }

                    // Always evaluate to apply SetupDecay (Time-based)
                    var evalResult = await decisionEngine.EvaluateAsync(session, strategy.Style, data.context, isAutoMode);
                    
                    // 6. Force Context alert for Stage 1 evaluations so the frontend is notified
                    if (session.CurrentStage == TradingStage.Evaluating && evalResult.Decision == DecisionEngine.TradingDecision.Ignore)
                    {
                        evalResult.Decision = DecisionEngine.TradingDecision.Context;
                    }
                    
                    // 6. Force Context alert for Stage 1 evaluations
                    if (session.CurrentStage == TradingStage.Evaluating && evalResult.Decision == DecisionEngine.TradingDecision.Ignore)
                    {
                        evalResult.Decision = DecisionEngine.TradingDecision.Context;
                    }

                    // Decide if we should log/alert this cycle
                    // We log if: Data changed OR Stage changed OR it's been > 5 minutes
                    bool shouldLog = !dataUnchanged || (DateTime.UtcNow - session.StartTime).TotalMinutes % 5 < 0.2; 
                    
                    bool stageChanged = await ProcessDecision(session, evalResult, strategy, data.candles.Last().Close, eventBus, currentTraderProfile.UserId, data.context);
                    
                    if (shouldLog || stageChanged)
                    {
                        await CreateAnalysisLogAsync(analysisLogRepo, session, evalResult, data.candles.Last().Close, data.context, eventBus, currentTraderProfile.UserId);
                    }
                    
                    // Sprint 1 Patch: Detection of stagnancy (always runs)
                    await CheckSessionStagnancyAsync(session, strategy, eventBus, currentTraderProfile.UserId, analysisLogRepo);

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
                            rankings = top3.Select(o => new {
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

                        // 6. Force Context alert for Stage 1 evaluations so frontend is notified
                        if (session.CurrentStage == TradingStage.Evaluating && best.Result.Decision == DecisionEngine.TradingDecision.Ignore)
                        {
                            best.Result.Decision = DecisionEngine.TradingDecision.Context;
                        }

                        // ALWAYS persist the analysis log for the best opportunity (consistent with fixed-symbol behavior)
                        var traderProfileForAuto = profileMap[session.TraderProfileId];
                        await CreateAnalysisLogAsync(analysisLogRepo, session, best.Result, best.Context.Candles.Last().Close, best.Context, eventBus, traderProfileForAuto.UserId, null, best.Symbol, best.Direction);

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

                            bool stageChanged = await ProcessDecision(session, best.Result, strategy, best.Context.Candles.Last().Close, eventBus, traderProfileForAuto.UserId, best.Context);
                            
                            // Sprint 1 Patch: Detection of stagnancy in AUTO mode
                            await CheckSessionStagnancyAsync(session, strategy, eventBus, traderProfileForAuto.UserId, analysisLogRepo);
                        }

                        // Update timestamp for AUTO mode (Sprint 3)
                        var maxTs = contextsOnly.Values.Max(c => c.Candles.Last().Timestamp);
                        session.LastEvaluationTimestamp = maxTs;
 
                        // Always update session (persist history and EvaluationHistoryJson)
                        await sessionRepository.UpdateAsync(session);
                    }
                    
                    // Always run stagnancy check for AUTO mode even if no winner or bestOpportunity is null
                    await CheckSessionStagnancyAsync(session, strategy, eventBus, currentTraderProfile.UserId, analysisLogRepo);
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

    private async Task<bool> ProcessDecision(
        TradingSession session, 
        DecisionResult result, 
        TradingStrategy strategy, 
        decimal currentPrice, 
        IDistributedEventBus eventBus, 
        Guid identityUserId,
        DecisionEngine.MarketContext context)
    {
        var oldStage = session.CurrentStage;
        bool changed = false;

        switch (result.Decision)
        {
            case DecisionEngine.TradingDecision.Entry:
                if (session.CurrentStage == TradingStage.Prepared && result.EntryMaxPrice.HasValue && currentPrice >= result.EntryMaxPrice.Value)
                {
                    // EMITIR EVENTO DE ENTRY CONFIRMADO (Breakout)
                    var alertDto = new VergeAlertDto
                    {
                        Id = Guid.NewGuid().ToString(),
                        Type = "Stage3", // Entry
                        Title = $"🚀 Breakout Confirmado en {session.Symbol}!",
                        Message = $"El precio ha superado la zona superior (${result.EntryMaxPrice:N2}). Breakout detectado.",
                        Timestamp = DateTime.UtcNow,
                        Read = false,
                        Crypto = session.Symbol,
                        Price = currentPrice,
                        Confidence = result.Confidence,
                        Direction = session.SelectedDirection ?? strategy.DirectionPreference,
                        Stage = TradingStage.BuyActive,
                        TargetZone = new TargetZoneDto { Low = result.EntryMinPrice ?? 0, High = result.EntryMaxPrice ?? 0 },
                        Severity = "success",
                        Icon = "rocket-outline"
                    };
                    
                    _logger.LogInformation("🔔 [Breakout] Publicando alerta de Stage3 para sesión {Id}", session.Id);
                    await eventBus.PublishAsync(new AlertStateChangedEto
                    {
                        UserId = identityUserId,
                        SessionId = session.Id,
                        Alert = alertDto,
                        TriggeredAt = DateTime.UtcNow,
                        IsBreakout = true,
                        EntryZoneHigh = result.EntryMaxPrice,
                        EntryZoneLow = result.EntryMinPrice
                    });
                }

                if (session.CurrentStage == TradingStage.Evaluating || session.CurrentStage == TradingStage.Prepared)
                {
                    session.CurrentStage = TradingStage.BuyActive;
                    session.EntryPrice = currentPrice;
                    
                    // Feedback Loop (Sprint 4): Record Initial conditions
                    session.InitialScore = result.Score;
                    session.InitialRegime = context.MarketRegime?.Regime;
                    session.InitialConfidence = result.Confidence;
                    session.InitialVolatility = (decimal?)context.Technicals?.Atr;
                    session.InitialVolumeMcapRatio = (decimal?)(context.CoinGeckoData?.MarketCap > 0 ? context.CoinGeckoData.TotalVolume / context.CoinGeckoData.MarketCap : 0);
                    session.EntryHour = DateTime.UtcNow.Hour;
                    session.EntryDayOfWeek = DateTime.UtcNow.DayOfWeek;
                    session.InitialWeightedScoresJson = JsonSerializer.Serialize(result.WeightedScores);

                    // Sprint 5: Institutional persistence
                    session.WhaleInfluenceScore = result.WhaleInfluenceScore;
                    session.WhaleSentiment = result.WhaleSentiment;
                    session.MacroQuietPeriod = result.MacroQuietPeriod;
                    session.MacroReason = result.MacroReason;

                    CalculateTargets(session, strategy, currentPrice);
                    changed = true;
                }
                break;

            case DecisionEngine.TradingDecision.Prepare:
                if (session.CurrentStage == TradingStage.Evaluating)
                {
                    session.CurrentStage = TradingStage.Prepared;
                    session.StageChangedTimestamp = DateTime.UtcNow;
                    changed = true;
                }
                break;
        }

        if (session.CurrentStage == TradingStage.BuyActive && oldStage != TradingStage.BuyActive)
        {
            session.StageChangedTimestamp = DateTime.UtcNow;
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
        DecisionEngine.MarketContext context,
        IDistributedEventBus eventBus,
        Guid identityUserId,
        string? customMessage = null,
        string? overrideSymbol = null,
        SignalDirection? overrideDirection = null)
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
                DecisionEngine.TradingDecision.Context => AnalysisLogType.AlertContext,
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

        string logSymbol = overrideSymbol ?? session.Symbol;
        SignalDirection? logDirection = overrideDirection ?? result.Direction ?? session.SelectedDirection;
        string dirText = logDirection?.ToString().ToUpper() ?? "WAIT";
        string confidenceLabel = result.Confidence.ToString().ToUpper();
        
        string message = customMessage ?? $"{emoji} {logSymbol} {dirText} | Entry: ${price:N2} | SL: ${(result.StopLossPrice ?? 0):N2} | TP: ${(result.TakeProfitPrice ?? 0):N2} | Score: {result.Score}/100";

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
            entryMax = result.EntryMaxPrice,
            winProb = result.WinProbability,
            rr = result.RiskRewardRatio,
            sampleSize = result.HistoricSampleSize,
            pattern = result.PatternSignal,
            whaleInfluence = result.WhaleInfluenceScore,
            whaleSentiment = result.WhaleSentiment,
            macroQuiet = result.MacroQuietPeriod,
            macroReason = result.MacroReason
        };

        var log = new AnalysisLog(
            Guid.NewGuid(),
            session.TraderProfileId,
            session.Id,
            logSymbol,
            message,
            result.Score >= 70 ? "success" : (result.Score >= 50 ? "warning" : "info"),
            DateTime.UtcNow,
            logType,
            JsonSerializer.Serialize(logData)
        );

        await repo.InsertAsync(log);

        string mappedSeverity = log.Level;
        if (logType == AnalysisLogType.AlertInvalidated) mappedSeverity = "danger";
        else if (logType == AnalysisLogType.AlertPrepare) mappedSeverity = "warning";
        else if (logType == AnalysisLogType.AlertEntry) mappedSeverity = "success";

        var alertDto = new VergeAlertDto
        {
            Id = log.Id.ToString(),
            Type = GetAlertType(logType),
            Title = $"Análisis {logSymbol}",
            Message = log.Message.Contains(" | Score:") ? log.Message.Substring(0, log.Message.IndexOf(" | Score:")) : log.Message,
            Timestamp = log.Timestamp,
            Read = false,
            Crypto = logSymbol,
            Price = price,
            Confidence = result.Confidence,
            Direction = logDirection,
            Stage = session.CurrentStage,
            Score = result.Score,
            Severity = mappedSeverity,
            Icon = "analytics-outline",
            Structure = context.MarketRegime?.Structure,
            BosDetected = context.MarketRegime?.BosDetected ?? false,
            ChochDetected = context.MarketRegime?.ChochDetected ?? false,
            LiquidityZones = context.MarketRegime?.LiquidityZones ?? new List<float>()
        };
        
        if (result.EntryMinPrice.HasValue && result.EntryMaxPrice.HasValue)
        {
            alertDto.TargetZone = new TargetZoneDto { Low = result.EntryMinPrice.Value, High = result.EntryMaxPrice.Value };
        }

        alertDto.RiskRewardRatio = result.RiskRewardRatio;
        alertDto.WinProbability = result.WinProbability ?? result.Score; // 👈 Fallback to general AI Score
        alertDto.HistoricSampleSize = result.HistoricSampleSize;
        alertDto.PatternSignal = result.PatternSignal;
        alertDto.StopLoss = result.StopLossPrice;
        alertDto.TakeProfit = result.TakeProfitPrice;
        alertDto.AgentOpinions = result.AgentOpinions ?? new Dictionary<string, string>();

        _logger.LogInformation("🔔 [Analysis] Publicando alerta {Type} ({Crypto}) para sesión {Id}. [Opinions: {OpCount}, WinProb: {WinProb}%]", 
            alertDto.Type, alertDto.Crypto, session.Id, alertDto.AgentOpinions.Count, alertDto.WinProbability);

        await eventBus.PublishAsync(new AlertStateChangedEto
        {
            UserId = identityUserId,
            SessionId = session.Id,
            Alert = alertDto,
            TriggeredAt = DateTime.UtcNow,
            IsBreakout = false,
            EntryZoneHigh = result.EntryMaxPrice,
            EntryZoneLow = result.EntryMinPrice
        });
    }

    private string GetAlertType(AnalysisLogType logType) => logType switch
    {
        AnalysisLogType.AlertContext => "Stage1",
        AnalysisLogType.AlertPrepare => "Stage2",
        AnalysisLogType.AlertEntry => "Stage3",
        AnalysisLogType.AlertExit => "Stage4",
        AnalysisLogType.AlertInvalidated => "Custom",
        _ => "System"
    };

    private async Task<bool> CheckTradeExitsAsync(
        TradingSession session, 
        TradingStrategy strategy, 
        Dictionary<(string symbol, string timeframe), (List<MarketCandleModel> candles, DecisionEngine.MarketContext context)> groupDataCache,
        IRepository<TradingSession, Guid> sessionRepo,
        IRepository<AnalysisLog, Guid> logRepo,
        IDistributedEventBus eventBus,
        Guid identityUserId)
    {
        if (!groupDataCache.TryGetValue((session.Symbol, session.Timeframe), out var data)) return false;
        
        var currentPrice = data.candles.Last().Close;
        var direction = session.SelectedDirection ?? strategy.DirectionPreference;
        bool isLong = direction == SignalDirection.Long;
        var style = session.SelectedStyle ?? strategy.Style;
        var regime = data.context.MarketRegime;
        var atr = CalculateAtr(data.candles);

        // 1. Initialize Pro Stats (if first time)
        if (!session.InitialStopLoss.HasValue) session.InitialStopLoss = session.StopLossPrice;
        if (session.CurrentInvestment == 0) session.CurrentInvestment = strategy.Capital;

        // 2. Thresholds by Style
        decimal beThreshold = style switch { 
            TradingStyle.Scalping => 0.01m, 
            TradingStyle.DayTrading => 0.02m, 
            TradingStyle.SwingTrading => 0.03m, 
            _ => 0.05m 
        };
        float trailMultiplier = style switch {
            TradingStyle.Scalping => 1.0f,
            TradingStyle.DayTrading => 1.5f,
            TradingStyle.SwingTrading => 2.0f,
            _ => 3.0f
        };

        // 3. Logic: Calculate Current Metrics
        decimal entryPrice = session.EntryPrice ?? currentPrice;
        decimal priceChangePct = isLong ? (currentPrice - entryPrice) / entryPrice : (entryPrice - currentPrice) / entryPrice;
        bool isTrend = regime?.Regime == MarketRegimeType.BullTrend || regime?.Regime == MarketRegimeType.BearTrend;

        // 4. BREAK-EVEN Logic
        if (!session.IsBreakEvenActive && priceChangePct >= beThreshold)
        {
            session.StopLossPrice = entryPrice;
            session.IsBreakEvenActive = true;
            _logger.LogInformation("🛡️ [BE] Break-even Activo para {Symbol}", session.Symbol);
            await CreateAnalysisLogAsync(logRepo, session, new DecisionEngine.DecisionResult { Decision = DecisionEngine.TradingDecision.Context }, currentPrice, data.context, eventBus, identityUserId, "🛡️ BREAK-EVEN ACTIVADO: Operación protegida");
        }

        // 5. INTELLIGENT TRAILING STOP (Structural)
        if (regime != null && (regime.BosDetected || regime.ChochDetected))
        {
            decimal newTs = isLong ? (currentPrice - (decimal)trailMultiplier * atr) : (currentPrice + (decimal)trailMultiplier * atr);
            bool isBetter = isLong ? (newTs > (session.StopLossPrice ?? 0)) : (newTs < (session.StopLossPrice ?? decimal.MaxValue));
            
            if (isBetter)
            {
                session.TrailingStopPrice = newTs;
                session.StopLossPrice = newTs;
                _logger.LogInformation("📈 [TS] Trailing Stop Actualizado a {Price} por BOS", newTs);
                await CreateAnalysisLogAsync(logRepo, session, new DecisionEngine.DecisionResult { Decision = DecisionEngine.TradingDecision.Context }, currentPrice, data.context, eventBus, identityUserId, $"📈 TRAILING STOP ACTUALIZADO: ${newTs:N2} (Volatilidad estructural)");
            }
        }

        // 6. PARTIAL TAKE PROFITS & SCALE-IN
        if (session.TakeProfitPrice.HasValue)
        {
            decimal totalGoal = Math.Abs(session.TakeProfitPrice.Value - entryPrice);
            decimal currentProfitDistance = isLong ? (currentPrice - entryPrice) : (entryPrice - currentPrice);

            // TP1: 33% of target -> Close 25% and Move to BE
            if (session.PartialTpsCount < 1 && currentProfitDistance >= totalGoal * 0.33m)
            {
                session.PartialTpsCount = 1;
                session.CurrentInvestment *= 0.75m; // Liquida 25%
                if (!session.IsBreakEvenActive) { session.StopLossPrice = entryPrice; session.IsBreakEvenActive = true; }
                await CreateAnalysisLogAsync(logRepo, session, new DecisionEngine.DecisionResult { Decision = DecisionEngine.TradingDecision.Context }, currentPrice, data.context, eventBus, identityUserId, "💰 TP1 ALCANZADO: 25% cerrado. SL movido a entrada.");
            }
            // TP2: 66% of target -> Close another 33% (25% original) and activate TS
            else if (session.PartialTpsCount < 2 && currentProfitDistance >= totalGoal * 0.66m)
            {
                session.PartialTpsCount = 2;
                session.CurrentInvestment *= 0.66m; // Liquida otro ~25% original
                await CreateAnalysisLogAsync(logRepo, session, new DecisionEngine.DecisionResult { Decision = DecisionEngine.TradingDecision.Context }, currentPrice, data.context, eventBus, identityUserId, "💰 TP2 ALCANZADO: 50% total cobrado. Trailing Stop activado.");
            }
            // SCALE-IN: If BOS occurs after TP1 in Trend
            else if (session.PartialTpsCount >= 1 && (regime?.BosDetected ?? false) && isTrend)
            {
                session.CurrentInvestment *= 1.3m; // Reinvertir 30%
                await CreateAnalysisLogAsync(logRepo, session, new DecisionEngine.DecisionResult { Decision = DecisionEngine.TradingDecision.Context }, currentPrice, data.context, eventBus, identityUserId, "🚀 ESCALADO (Scale-in): Aumentando posición 30% por BOS en tendencia fuerte.");
            }
        }

        // 7. FINAL EXIT CHECK
        bool exitTriggered = false;
        string exitMessage = "";
        
        if (isLong)
        {
            if (session.TakeProfitPrice.HasValue && currentPrice >= session.TakeProfitPrice.Value)
            {
                exitTriggered = true;
                exitMessage = $"💰 TP3 Final alcanzado! Precio: ${currentPrice:N2}";
            }
            else if (session.StopLossPrice.HasValue && currentPrice <= session.StopLossPrice.Value)
            {
                exitTriggered = true;
                exitMessage = session.TrailingStopPrice.HasValue ? $"📈 Trailing Stop activado. Precio: ${currentPrice:N2}" : $"🛑 Stop Loss activado. Precio: ${currentPrice:N2}";
            }
        }
        else // SHORT
        {
            if (session.TakeProfitPrice.HasValue && currentPrice <= session.TakeProfitPrice.Value)
            {
                exitTriggered = true;
                exitMessage = $"💰 TP3 Final alcanzado! Precio: ${currentPrice:N2}";
            }
            else if (session.StopLossPrice.HasValue && currentPrice >= session.StopLossPrice.Value)
            {
                exitTriggered = true;
                exitMessage = session.TrailingStopPrice.HasValue ? $"📈 Trailing Stop activado. Precio: ${currentPrice:N2}" : $"🛑 Stop Loss activado. Precio: ${currentPrice:N2}";
            }
        }
        
        if (exitTriggered)
        {
            _logger.LogInformation("📉 Final Exit for {Symbol}: {Message}", session.Symbol, exitMessage);
            
            decimal netProfit = 0;
            if (session.EntryPrice.HasValue && session.EntryPrice.Value > 0)
            {
                var leverage = (decimal)strategy.Leverage;
                var quantity = (session.CurrentInvestment * leverage) / session.EntryPrice.Value;
                
                if (isLong)
                    netProfit = (currentPrice - session.EntryPrice.Value) * quantity;
                else
                    netProfit = (session.EntryPrice.Value - currentPrice) * quantity;
            }

            session.CurrentStage = TradingStage.SellActive;
            session.IsActive = false;
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
                $"{exitMessage} | Resultado Final: ${netProfit:N2} USDT",
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
            
            var alertDto = new VergeAlertDto
            {
                Id = exitLog.Id.ToString(),
                Type = "Stage4",
                Title = $"Sesión Finalizada: {session.Symbol}",
                Message = exitMessage,
                Timestamp = DateTime.UtcNow,
                Crypto = session.Symbol,
                Price = currentPrice,
                Severity = netProfit >= 0 ? "success" : "danger",
                Icon = netProfit >= 0 ? "cash-outline" : "warning-outline"
            };

            await eventBus.PublishAsync(new AlertStateChangedEto { UserId = identityUserId, SessionId = session.Id, Alert = alertDto });
            
            return true;
        }
        
        return false;
    }

    private async Task CheckSessionStagnancyAsync(TradingSession session, TradingStrategy strategy, IDistributedEventBus eventBus, Guid identityUserId, IRepository<AnalysisLog, Guid> logRepo)
    {
        var profile = TradingStyleProfileFactory.GetProfile(strategy.Style);
        var referenceTime = session.StageChangedTimestamp ?? session.StartTime;
        var timeInStage = DateTime.UtcNow - referenceTime;

        // Threshold: MaxStagnationMinutes (e.g., 30m for DayTrading)
        if (timeInStage.TotalMinutes > profile.MaxStagnationMinutes)
        {
            // Solo alertamos si: 
            // 1. No existe log reciente en 60 mins.
            // 2. OR acaba de reiniciar el backend (!HasValue)
            // 3. OR han pasado N minutos redondos desde que arrancó el backend (% 3 == 0) para forzar reactividad
            var lastStagnationLog = await logRepo.FirstOrDefaultAsync(x => 
                x.TradingSessionId == session.Id && 
                x.LogType == AnalysisLogType.AlertSystem && 
                x.Message.Contains("ESTANCADA") &&
                x.Timestamp > DateTime.UtcNow.AddMinutes(-60));
                
            bool isImmediateWarning = !session.LastEvaluationTimestamp.HasValue || (int)Math.Floor(timeInStage.TotalMinutes) % 3 == 0;

            if (lastStagnationLog == null || isImmediateWarning)
            {
                var stagnationMessage = $"⚠️ [INSTITUTIONAL 1%] CACERÍA ESTANCADA: {session.Symbol} no muestra señales claras en {Math.Floor(timeInStage.TotalMinutes)} min. ¿Considerás rotar moneda o finalizar?";
                
                _logger.LogWarning("🚨 Stagnancy detected for Session {Id}: {Symbol}", session.Id, session.Symbol);

                var alertDto = new VergeAlertDto
                {
                    Id = Guid.NewGuid().ToString(),
                    Type = "System",
                    Title = "⚠ ALERTA DE ESTANCAMIENTO",
                    Message = stagnationMessage,
                    Timestamp = DateTime.UtcNow,
                    Read = false,
                    Crypto = session.Symbol,
                    Stage = session.CurrentStage,
                    Severity = "warning",
                    Icon = "timer-outline"
                };

                await eventBus.PublishAsync(new AlertStateChangedEto
                {
                    UserId = identityUserId,
                    SessionId = session.Id,
                    Alert = alertDto,
                    TriggeredAt = DateTime.UtcNow
                });

                // Persist it as an AnalysisLog too
                await logRepo.InsertAsync(new AnalysisLog(
                    Guid.NewGuid(),
                    session.TraderProfileId,
                    session.Id,
                    session.Symbol,
                    stagnationMessage,
                    "warning",
                    DateTime.UtcNow,
                    AnalysisLogType.AlertSystem,
                    "{}"
                ));
            }
        }
    }

    private decimal CalculateAtr(List<MarketCandleModel> candles, int period = 14)
    {
        if (candles.Count < period + 1) return 0;
        
        var trs = new List<decimal>();
        for (int i = candles.Count - period; i < candles.Count; i++)
        {
            var high = candles[i].High;
            var low = candles[i].Low;
            var prevClose = candles[i - 1].Close;
            
            var tr = Math.Max(high - low, Math.Max(Math.Abs(high - prevClose), Math.Abs(low - prevClose)));
            trs.Add(tr);
        }
        
        return trs.Average();
    }
}
