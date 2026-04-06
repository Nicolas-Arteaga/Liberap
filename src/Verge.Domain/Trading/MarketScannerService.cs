using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;

using Verge.Trading.Integrations;
using Verge.Trading.DecisionEngine;
using Volo.Abp.EventBus.Distributed;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class MarketScannerService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<MarketScannerService> _logger;
    private readonly IDistributedEventBus _eventBus;

    public MarketScannerService(
        IServiceProvider serviceProvider, 
        ILogger<MarketScannerService> logger,
        IDistributedEventBus eventBus)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _eventBus = eventBus;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 Market Scanner Service started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ScanMarketAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error in market scanner cycle");
            }

            _logger.LogInformation("😴 Scanner sleeping for 30 seconds...");
            await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
    }

    private async Task ScanMarketAsync()
    {
        _logger.LogInformation("🔍 Starting market scan at {time}", DateTime.UtcNow);

        using var scope = _serviceProvider.CreateScope();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var analysisService = scope.ServiceProvider.GetRequiredService<CryptoAnalysisService>();
        var freeNewsService = scope.ServiceProvider.GetRequiredService<IFreeCryptoNewsService>();
        var pythonService = scope.ServiceProvider.GetRequiredService<IPythonIntegrationService>();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
        var profileRepository = scope.ServiceProvider.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var analysisLogRepo = scope.ServiceProvider.GetRequiredService<IRepository<AnalysisLog, Guid>>();
        var alertHistoryRepo = scope.ServiceProvider.GetRequiredService<IRepository<AlertHistory, Guid>>();
        var whaleTracker = scope.ServiceProvider.GetRequiredService<IWhaleTrackerService>();
        var institutionalService = scope.ServiceProvider.GetRequiredService<IInstitutionalDataService>();
        var multiAgentConsensus = scope.ServiceProvider.GetRequiredService<IMultiAgentConsensusService>();
        var macroService = scope.ServiceProvider.GetRequiredService<IMacroSentimentService>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();
        var aniquilador = scope.ServiceProvider.GetRequiredService<IAniquiladorPatternManager>();

        using var uow = unitOfWorkManager.Begin();

        // 0. Macro Check (Sprint 5) - Affects entire scan cycle
        var macroData = await macroService.GetMacroSentimentAsync();
        if (macroData.IsInQuietPeriod) {
            _logger.LogWarning("🌍 QUIET PERIOD ACTIVE: {reason}. Skipping scanners or dampening entries...", macroData.QuietPeriodReason);
        }

        // Top 30 symbols by volume (Phase 4 Scaling)
        var topSymbols = await marketDataManager.GetTopSymbolsAsync(30);
        _logger.LogInformation("📊 Top 30 symbols to analyze ({count}). Analyzing...", topSymbols.Count);

        int analyzedCount = 0;
        foreach (var symbol in topSymbols)
        {
            try
            {
                _logger.LogInformation("🧪 Analizando {symbol}...", symbol);
                
                // 2. Obtener velas (15m por defecto para el scanner)
                var candles = await marketDataManager.GetCandlesAsync(symbol, "15", 30);
                if (candles == null || candles.Count < 20) {
                    _logger.LogWarning("⚠️ No hay suficientes velas para {symbol}", symbol);
                    continue;
                }

                // 🎯 [NICOLAS ANIQUILADOR] Obtener velas 1H y analizar el patrón extremo
                try {
                    var hourlyCandles = await marketDataManager.GetCandlesAsync(symbol, "1h", 120);
                    if (hourlyCandles != null && hourlyCandles.Count >= 100)
                    {
                        await aniquilador.AnalyzeCandlesAsync(symbol, hourlyCandles);
                    }
                } catch { /* Ignorar fallos aislados en este branch analitico */ }

                // 🚀 Phase 4 Pre-Filter: Zombie Data Check
                if (analysisService.IsZombieData(candles))
                {
                    _logger.LogWarning("🧟 ZOMBIE DATA DETECTED for {symbol}. Skipping to save resources.", symbol);
                    continue;
                }

                var prices = candles.Select(x => x.Close).ToList();
                
                // 🚀 ZOMBIE DATA DETECTION: If price hasn't moved at all, RSI will be fake.
                bool isStagnant = prices.Distinct().Count() == 1;
                if (isStagnant) {
                    _logger.LogWarning("🧟 [ZOMBIE DATA] {symbol} price is stuck at {price}. RSI will be neutral 50.", symbol, prices.First());
                }

                var rsi = analysisService.CalculateRSI(prices);
                
                // 🧠 IA Local (Python) - Detectar Régimen de Mercado
                // Esto genera los 200 OK en el terminal del servicio de Python
                try
                {
                    var regimeResult = await pythonService.DetectMarketRegimeAsync(symbol, "15m", candles);
                    if (regimeResult != null)
                        _logger.LogInformation("🧠 [Python] {symbol} Regime: {regime} (Strength: {str:F2})", symbol, regimeResult.Regime, regimeResult.TrendStrength);
                }
                catch (Exception ex) { _logger.LogWarning("⚠️ [Python Regime] {symbol}: {msg}", symbol, ex.Message); }

                // 🧠 IA Local (Python) - Analizar Técnicos
                try
                {
                    var techResult = await pythonService.AnalyzeTechnicalsAsync(symbol, "15m", candles);
                    if (techResult != null)
                        _logger.LogInformation("🧠 [Python] {symbol} RSI={rsi:F1} MACD={macd:F4} ATR={atr:F4}", symbol, techResult.Rsi, techResult.MacdHistogram, techResult.Atr);
                }
                catch (Exception ex) { _logger.LogWarning("⚠️ [Python Technicals] {symbol}: {msg}", symbol, ex.Message); }

                // Cálculo de tendencia básica
                var firstHalf = prices.Take(15).Average();
                var lastHalf = prices.Skip(15).Average();
                var trend = lastHalf > firstHalf ? "bullish" : "bearish";
                
                // 3. Sentimiento (IA)
                int sentimentBonus = 0;
                string sentimentText = "Neutral/Unknown";
                try {
                    var sentiment = await freeNewsService.GetSentimentAsync(symbol);
                    if (sentiment != null) {
                        sentimentText = sentiment.Label;
                        if (sentiment.Label == "positive") sentimentBonus = 20;
                        else if (sentiment.Label == "negative") sentimentBonus = -20;
                    }
                } catch { /* Ignorar error de Noticias */ }

                // 3.1. Ballenas (Sprint 5)
                var whaleData = await whaleTracker.GetWhaleActivityAsync(symbol);
                int whaleBonus = (int)(whaleData.NetFlowScore * 15); // Max +15 bonus

                // 3.2. Liquidaciones y Order Flow (Sprint 5)
                var instData = await institutionalService.GetInstitutionalDataAsync(symbol);
                int instBonus = instData.IsSqueezeDetected ? (instData.SqueezeType == "Short Squeeze" ? 15 : -15) : 0;
                instBonus += (int)((instData.BidAskImbalance - 1.0) * 5); // Max +10 bonus

                // 4. Calcular Confianza
                int confidence = 0;
                SignalDirection signal = SignalDirection.Auto;

                if (rsi < 35) {
                    // 🛡️ Falling Knife Protection: Don't call LONG if trend is strongly bearish
                    if (trend == "bearish") {
                        confidence = (int)(35 - rsi) * 1 + 40; // Reduced confidence
                        signal = SignalDirection.Auto; // WAIT
                    } else {
                        confidence = (int)(35 - rsi) * 2 + 50;
                        signal = SignalDirection.Long;
                    }
                } else if (rsi > 65) {
                    // 🛡️ Rocket Protection: Don't call SHORT if trend is strongly bullish
                    if (trend == "bullish") {
                        confidence = (int)(rsi - 65) * 1 + 40;
                        signal = SignalDirection.Auto; // WAIT
                    } else {
                        confidence = (int)(rsi - 65) * 2 + 50; 
                        signal = SignalDirection.Short;
                    }
                } else {
                    confidence = 30 + (trend == "bullish" ? 10 : 0);
                    signal = SignalDirection.Auto;
                }

                confidence += sentimentBonus + whaleBonus + instBonus;
                
                // 4.2. Quiet Period Dampening
                if (macroData.IsInQuietPeriod) {
                    confidence = 0; // Absolute protection during news
                }

                confidence = Math.Clamp(confidence, 0, 100);

                // 5. Crear Log para Dashboard
                var analysisResult = new {
                    symbol = symbol,
                    rsi = Math.Round(rsi, 2),
                    trend = trend,
                    confidence = confidence,
                    signal = signal.ToString(),
                    style = "DayTrading (15m)", // Fixed for now, can be dynamic later
                    sentiment = sentimentText,
                    whaleSentiment = whaleData.Summary,
                    institutionalSummary = instData.Summary,
                    isSqueeze = instData.IsSqueezeDetected,
                    macroQuietPeriod = macroData.IsInQuietPeriod,
                    macroReason = macroData.QuietPeriodReason,
                    timestamp = DateTime.UtcNow
                };

                var log = new AnalysisLog(
                    Guid.NewGuid(),
                    Guid.Empty, 
                    null,
                    symbol,
                    $"Scanner: {symbol} | RSI: {rsi:F2} | Conf: {confidence}% | 🐋: {whaleData.Summary} | 🔥: {instData.SqueezeType} | 🌍: {(macroData.IsInQuietPeriod ? "QUIET" : "OK")}",
                    confidence > 70 ? "success" : "info",
                    DateTime.UtcNow,
                    AnalysisLogType.Standard,
                    JsonSerializer.Serialize(analysisResult)
                );

                await analysisLogRepo.InsertAsync(log);
                analyzedCount++;

                // 5.5 Publish Real-time Telemetry (SignalR) for Dashboard UI Grids
                var profiles = await profileRepository.GetListAsync();
                // 2. Fetch AI Insights for high-confidence findings (>60% to save quota)
                Dictionary<string, string> agentOpinions = new();
                if (confidence >= 60)
                {
                    try {
                        var marketContext = new MarketContext { 
                            Symbol = symbol,
                            Technicals = new TechnicalsResponseModel { Rsi = (float)rsi },
                            MarketRegime = new RegimeResponseModel { 
                                Regime = trend == "bullish" ? MarketRegimeType.BullTrend : MarketRegimeType.BearTrend,
                                TrendStrength = 1.0f
                            },
                            WhaleData = whaleData,
                            InstitutionalData = instData,
                            MacroData = macroData
                        }; 
                        _logger.LogInformation("🧠 [Scanner AI] Fetching insights for {symbol} with full context...", symbol);
                        var aiResult = await multiAgentConsensus.GetConsensusAsync(marketContext, TradingStyle.DayTrading);
                        agentOpinions = aiResult.AgentOpinions;
                        _logger.LogInformation("🧠 [Scanner AI] Fetched {count} opinions for {symbol}", agentOpinions.Count, symbol);
                    } catch (Exception ex) { 
                        _logger.LogWarning("⚠️ [Scanner AI] Failed to fetch insights for {symbol}: {msg}", symbol, ex.Message);
                    }
                }

                // Fase 5 & 6: Save strictly every alert generated with all metrics
                var (estMinutes, expectedDd) = AlertHistory.GetStyleEstimates("DayTrading"); // For Scanner is mostly day trading
                var tier = AlertHistory.ComputeTier(confidence);
                var alertReasoningJson = JsonSerializer.Serialize(agentOpinions);
                
                var alertHistory = new AlertHistory(
                    Guid.NewGuid(),
                    symbol,
                    "DayTrading", // Default style for scanner
                    signal == SignalDirection.Long ? 0 : (signal == SignalDirection.Short ? 1 : 2),
                    prices.LastOrDefault(), // entry
                    prices.LastOrDefault() + ( (prices.LastOrDefault() * 0.03m) * (signal == SignalDirection.Long ? 1.0m : -1.0m) ), // target
                    prices.LastOrDefault() - ( (prices.LastOrDefault() * 0.015m) * (signal == SignalDirection.Long ? 1.0m : -1.0m) ), // sl
                    confidence,
                    estMinutes,
                    expectedDd,
                    alertReasoningJson,
                    "{}", // raw representation can be added later if needed
                    DateTime.UtcNow,
                    DateTime.UtcNow.AddMinutes(estMinutes),
                    tier,
                    "Scanner",
                    false
                );
                
                await alertHistoryRepo.InsertAsync(alertHistory);

                foreach (var profile in profiles)
                {
                    await _eventBus.PublishAsync(new AlertStateChangedEto
                    {
                        UserId = profile.UserId,
                        SessionId = Guid.Empty,
                        Alert = new VergeAlertDto
                        {
                            Id = Guid.NewGuid().ToString(),
                            Type = confidence >= 50 ? "Stage1" : "ScannerUpdate",
                            Title = confidence >= 50 ? $"🔍 Oportunidad: {symbol}" : $"Scanner: {symbol}",
                            Message = $"Confianza: {(int)confidence}% | Tendencia: {trend.ToUpper()} | RSI: {rsi:F2} | 🐋: {whaleData.Summary} | 🔥: {instData.SqueezeType}",
                            Timestamp = DateTime.UtcNow,
                            Read = false,
                            Crypto = symbol,
                            Price = prices.LastOrDefault(),
                            Confidence = (SignalConfidence)(int)confidence,
                            Direction = signal,
                            Severity = confidence >= 70 ? "success" : (confidence >= 50 ? "warning" : "info"),
                            Icon = confidence >= 50 ? "search-outline" : "pulse-outline",
                            WhaleInfluenceScore = whaleBonus * 100 / 15,
                            IsSqueeze = instData.IsSqueezeDetected,
                            Score = (int)confidence,
                            AgentOpinions = agentOpinions,
                            // 🚀 NUCLEAR SYNC: Mathematical multiplier ensures Label and Prices are LOCKED
                            RiskRewardRatio = 2.0,
                            StopLoss = prices.LastOrDefault() - ( (prices.LastOrDefault() * 0.015m) * (signal == SignalDirection.Long ? 1.0m : -1.0m) ),
                            TakeProfit = prices.LastOrDefault() + ( (prices.LastOrDefault() * 0.03m) * (signal == SignalDirection.Long ? 1.0m : -1.0m) )
                        }
                    });
                }

                // 6. Si Confianza > 2 (Threshold bajo para test), buscar estrategias en AutoMode y activar sesión
                if (confidence >= 2) {
                    _logger.LogInformation("🔥 OPORTUNIDAD DETECTADA: {symbol} con {confidence}% de confianza!", symbol, confidence);
                    
                    // Guardar log de OPORTUNIDAD para el modal
                    var opportunityLog = new AnalysisLog(
                        Guid.NewGuid(),
                        Guid.Empty,
                        null,
                        symbol,
                        $"🚀 OPORTUNIDAD DETECTADA: {symbol} con {confidence}% de confianza!",
                        "success",
                        DateTime.UtcNow,
                        AnalysisLogType.AlertContext,
                        JsonSerializer.Serialize(new { 
                            symbol = symbol, 
                            confidence = confidence, 
                            signal = signal.ToString(),
                            isOpportunity = true 
                        })
                    );
                    await analysisLogRepo.InsertAsync(opportunityLog);
                    
                    var autoStrategies = await strategyRepository.GetListAsync(x => x.IsActive && x.IsAutoMode);

                    foreach (var strategy in autoStrategies) {
                        var existingSession = await sessionRepository.FirstOrDefaultAsync(x => x.TraderProfileId == strategy.TraderProfileId && x.IsActive);
                        if (existingSession == null) {
                            _logger.LogInformation("🚀 Auto-activando sesión para {symbol} en perfil {profile}", symbol, strategy.TraderProfileId);
                            var session = new TradingSession(Guid.NewGuid(), strategy.TraderProfileId, symbol, "15");
                            session.CurrentStage = TradingStage.Evaluating;
                            await sessionRepository.InsertAsync(session);
                        }
                    }
                }
            } catch (Exception ex) {
                _logger.LogWarning($"⚠️ Error analizando {symbol}: {ex.Message}");
            }
        }

        await uow.CompleteAsync();
        _logger.LogInformation("🏁 Ciclo completado. Se analizaron {count} símbolos", analyzedCount);
    }
}
