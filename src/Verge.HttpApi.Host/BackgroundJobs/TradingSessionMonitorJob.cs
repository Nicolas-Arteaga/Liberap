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
                if (candidates == null || !candidates.Any()) candidates = new List<string> { "BTCUSDT" };
                
                foreach (var symbol in candidates)
                {
                    requiredGroups.Add((symbol, session.Timeframe));
                }
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

                var candles = await marketDataManager.GetCandlesAsync(symbol, timeframe, 100);
                if (candles == null || !candles.Any()) continue;

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
                if (session.Symbol != "AUTO")
                {
                    var groupKey = (session.Symbol, session.Timeframe);
                    if (!groupDataCache.TryGetValue(groupKey, out var data)) continue;

                    var evalResult = decisionEngine.Evaluate(session, strategy.Style, data.context);
                    bool stageChanged = ProcessDecision(session, evalResult, strategy, data.candles.Last().Close);
                    await CreateAnalysisLogAsync(analysisLogRepo, session, evalResult, data.candles.Last().Close, data.context);

                    if (stageChanged) await sessionRepository.UpdateAsync(session);
                }
                else
                {
                    // AUTO MODE: Evaluate all candidates and pick the best one
                    var candidates = strategy.GetSelectedCryptos();
                    if (candidates == null || !candidates.Any()) candidates = new List<string> { "BTCUSDT" };

                    (string symbol, DecisionEngine.DecisionResult result, List<MarketCandleModel> candles, DecisionEngine.MarketContext context)? bestEvaluation = null;

                    foreach (var symbol in candidates)
                    {
                        var groupKey = (symbol, session.Timeframe);
                        if (!groupDataCache.TryGetValue(groupKey, out var data)) continue;

                        // Create a temporary clone or just update symbol for evaluation
                        var originalSymbol = session.Symbol;
                        session.Symbol = symbol; 
                        var result = decisionEngine.Evaluate(session, strategy.Style, data.context);
                        session.Symbol = originalSymbol; // Restore

                        if (bestEvaluation == null || result.Score > bestEvaluation.Value.result.Score)
                        {
                            bestEvaluation = (symbol, result, data.candles, data.context);
                        }
                    }

                    if (bestEvaluation != null)
                    {
                        var best = bestEvaluation.Value;
                        _logger.LogInformation("🤖 AUTO session {Id}: Top candidate {Symbol} with score {Score}", session.Id, best.symbol, best.result.Score);

                        // If the best one triggers an entry or prepare, we take it
                        if (best.result.Decision != DecisionEngine.TradingDecision.Context)
                        {
                            session.Symbol = best.symbol; // Permanently assign the best symbol
                            bool stageChanged = ProcessDecision(session, best.result, strategy, best.candles.Last().Close);
                            await CreateAnalysisLogAsync(analysisLogRepo, session, best.result, best.candles.Last().Close, best.context);

                            if (stageChanged) await sessionRepository.UpdateAsync(session);
                        }
                        else
                        {
                            // Just log the best context for visualization in dashboard
                            await CreateAnalysisLogAsync(analysisLogRepo, session, best.result, best.candles.Last().Close, best.context);
                        }
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

        string message = $"{emoji} [{result.Decision}] Score: {result.Score}/100 | Regimen: {context.MarketRegime?.Regime.ToString() ?? "N/A"} | RSI: {context.Technicals?.Rsi:F1} | Price: ${price:N2}";
        var logData = new {
            score = result.Score,
            decision = result.Decision.ToString(),
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
