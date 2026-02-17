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

namespace Verge.Trading;

public class MarketScannerService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<MarketScannerService> _logger;

    public MarketScannerService(IServiceProvider serviceProvider, ILogger<MarketScannerService> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
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

            _logger.LogInformation("😴 Scanner sleeping for 1 minute...");
            await Task.Delay(TimeSpan.FromMinutes(1), stoppingToken);
        }
    }

    private async Task ScanMarketAsync()
    {
        _logger.LogInformation("🔍 Starting market scan at {time}", DateTime.UtcNow);

        using var scope = _serviceProvider.CreateScope();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var analysisService = scope.ServiceProvider.GetRequiredService<CryptoAnalysisService>();
        var pythonService = scope.ServiceProvider.GetRequiredService<IPythonIntegrationService>();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
        var analysisLogRepo = scope.ServiceProvider.GetRequiredService<IRepository<AnalysisLog, Guid>>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

        using var uow = unitOfWorkManager.Begin();

        // 1. Obtener Top 30
        var topSymbols = await marketDataManager.GetTopSymbolsAsync(30);
        _logger.LogInformation("📊 Top 30 symbols obtained ({count}). Analyzing...", topSymbols.Count);

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

                var prices = candles.Select(x => x.Close).ToList();
                var rsi = analysisService.CalculateRSI(prices);
                
                // Cálculo de tendencia básica
                var firstHalf = prices.Take(15).Average();
                var lastHalf = prices.Skip(15).Average();
                var trend = lastHalf > firstHalf ? "bullish" : "bearish";
                
                // 3. Sentimiento (IA)
                int sentimentBonus = 0;
                string sentimentText = "Neutral/Unknown";
                try {
                    var sentiment = await pythonService.AnalyzeSentimentAsync(symbol);
                    if (sentiment != null) {
                        sentimentText = sentiment.Sentiment;
                        if (sentiment.Sentiment == "positive") sentimentBonus = 20;
                        else if (sentiment.Sentiment == "negative") sentimentBonus = -20;
                    }
                } catch { /* Ignorar error de IA */ }

                // 4. Calcular Confianza
                int confidence = 0;
                SignalDirection signal = SignalDirection.Auto;

                if (rsi < 35) {
                    confidence = (int)(35 - rsi) * 2 + 50 + sentimentBonus;
                    signal = SignalDirection.Long;
                } else if (rsi > 65) {
                    confidence = (int)(rsi - 65) * 2 + 50 - sentimentBonus; 
                    if (sentimentBonus < 0) confidence += Math.Abs(sentimentBonus);
                    signal = SignalDirection.Short;
                } else {
                    confidence = 30 + (trend == "bullish" ? 10 : 0);
                    signal = SignalDirection.Auto;
                }

                confidence = Math.Clamp(confidence, 0, 100);

                // 5. Crear Log para Dashboard
                var analysisResult = new {
                    symbol = symbol,
                    rsi = Math.Round(rsi, 2),
                    trend = trend,
                    confidence = confidence,
                    signal = signal.ToString(),
                    sentiment = sentimentText,
                    timestamp = DateTime.UtcNow
                };

                var log = new AnalysisLog(
                    Guid.NewGuid(),
                    Guid.Empty, 
                    null,
                    symbol,
                    $"Scanner: {symbol} | RSI: {rsi:F2} | Conf: {confidence}% | IA: {sentimentText}",
                    confidence > 70 ? "success" : "info",
                    DateTime.UtcNow,
                    JsonSerializer.Serialize(analysisResult)
                );

                await analysisLogRepo.InsertAsync(log);
                analyzedCount++;

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
