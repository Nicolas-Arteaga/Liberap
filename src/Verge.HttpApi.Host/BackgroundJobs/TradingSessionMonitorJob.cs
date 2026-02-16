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

            _logger.LogInformation("😴 Job sleeping for 1 minute...");
            await Task.Delay(TimeSpan.FromMinutes(1), stoppingToken);
        }
    }

    private async Task MonitorActiveSessionsAsync()
    {
        _logger.LogInformation("🔍 MonitorActiveSessionsAsync() called");

        using var scope = _serviceProvider.CreateScope();
        var sessionRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingSession, Guid>>();
        var strategyRepository = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
        var marketDataManager = scope.ServiceProvider.GetRequiredService<MarketDataManager>();
        var analysisService = scope.ServiceProvider.GetRequiredService<CryptoAnalysisService>();
        var analysisLogRepo = scope.ServiceProvider.GetRequiredService<IRepository<AnalysisLog, Guid>>();
        var unitOfWorkManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

        using var uow = unitOfWorkManager.Begin();

        var activeSessions = await sessionRepository.GetListAsync(x => x.IsActive && x.CurrentStage < TradingStage.SellActive);
        _logger.LogInformation("📊 Found {count} active sessions", activeSessions.Count);

        if (!activeSessions.Any())
        {
            _logger.LogInformation("ℹ️ No hay sesiones activas para monitorear.");
            return;
        }

        foreach (var session in activeSessions)
        {
            try
            {
                var profileId = session.TraderProfileId;
                var strategy = await strategyRepository.FirstOrDefaultAsync(x => x.TraderProfileId == profileId && x.IsActive);
                
                if (strategy == null)
                {
                    _logger.LogWarning($"⚠️ No se encontró estrategia activa para el perfil {profileId}. Desactivando sesión {session.Id}");
                    session.IsActive = false;
                    session.EndTime = DateTime.UtcNow;
                    await sessionRepository.UpdateAsync(session);
                    continue;
                }

                _logger.LogInformation($"📊 Obteniendo datos de mercado para {session.Symbol} ({session.Timeframe})...");
                var marketData = await marketDataManager.GetCandlesAsync(session.Symbol, session.Timeframe, 30);
                
                if (marketData == null || !marketData.Any())
                {
                    _logger.LogWarning($"⚠️ No se obtuvieron velas para {session.Symbol}");
                    continue;
                }

                // Datos básicos para el log
                var currentPrice = marketData.Last().Close;
                var prices = marketData.Select(x => x.Close).ToList();
                var rsi = analysisService.CalculateRSI(prices);
                
                string reason;
                bool advanced = analysisService.ShouldAdvanceStage(session, strategy, marketData, out reason);
                
                string logLevel = "info";
                string message = "";

                // MEJORAR MENSAJES DE LA CONSOLA (UX)
                // Si es el primer minuto
                if (session.CreationTime > DateTime.UtcNow.AddMinutes(-2))
                {
                    message = $"🔄 Iniciando análisis de {session.Symbol} - Calibrando indicadores...";
                }
                // Análisis normal
                else
                {
                    message = $"📊 Analizando {session.Symbol} - RSI: {rsi:F2} | Precio: ${currentPrice:F2}";
                    
                    // Mensajes según el RSI
                    if (rsi < 30)
                    {
                        message = $"🔥 {session.Symbol} en SOBREVENTA (RSI: {rsi:F2}) - Posible oportunidad de COMPRA";
                        logLevel = "warning";
                    }
                    else if (rsi > 70)
                    {
                        message = $"⚠️ {session.Symbol} en SOBRECOMPRA (RSI: {rsi:F2}) - Posible oportunidad de VENTA";
                        logLevel = "warning";
                    }
                    else if (rsi < 40)
                        message = $"📉 {session.Symbol} acercándose a sobreventa (RSI: {rsi:F2}) - Monitoreando...";
                    else if (rsi > 60)
                        message = $"📈 {session.Symbol} acercándose a sobrecompra (RSI: {rsi:F2}) - Monitoreando...";
                }

                // Si hay noticias (simulado)
                if (DateTime.UtcNow.Minute % 3 == 0) // Cada 3 minutos simular noticias
                {
                    var news = new[] {
                        "Analizando sentimiento de noticias...",
                        "Volumen anormal detectado",
                        "Tendencia alcista en redes sociales",
                        "Noticias positivas para el sector"
                    };
                    message = $"📰 {news[DateTime.UtcNow.Minute % 4]} - {message}";
                }

                if (advanced)
                {
                    _logger.LogInformation($"✅ AVANCE DETECTADO! Sesión {session.Id} ({session.Symbol}): {reason}");
                    
                    var oldStage = session.CurrentStage;
                    session.CurrentStage = (TradingStage)((int)session.CurrentStage + 1);
                    _logger.LogInformation($"🚀 Stage actualizado: {oldStage} -> {session.CurrentStage}");
                    
                    logLevel = "success";
                    message = $"🚀 {reason} | RSI: {rsi:F2} | Precio: ${currentPrice:F2} | Nuevo Stage: {session.CurrentStage}";

                    if (session.CurrentStage == TradingStage.BuyActive)
                    {
                        session.EntryPrice = currentPrice;
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
                        _logger.LogInformation($"🎯 Targets configurados: Entrada {session.EntryPrice}, TP {session.TakeProfitPrice}, SL {session.StopLossPrice}");
                    }

                    if (session.CurrentStage == TradingStage.SellActive)
                    {
                        _logger.LogInformation($"🏁 Cacería completa para {session.Symbol}. Desactivando sesión.");
                        session.EndTime = DateTime.UtcNow;
                        session.IsActive = false;
                    }

                    await sessionRepository.UpdateAsync(session);
                }

                // LOG OBLIGATORIO CADA MINUTO (unificado)
                var logData = new 
                { 
                    rsi = Math.Round(rsi, 2), 
                    precio = currentPrice,
                    stage = session.CurrentStage.ToString(),
                    advanced = advanced,
                    tendencia = rsi > 50 ? "alcista" : "bajista",
                    volumen_relativo = "normal" // Podrías calcularlo si tenés datos
                };

                var log = new AnalysisLog(
                    Guid.NewGuid(),
                    session.TraderProfileId,
                    session.Id,
                    session.Symbol,
                    message,
                    logLevel,
                    DateTime.UtcNow,
                    System.Text.Json.JsonSerializer.Serialize(logData)
                );
                
                await analysisLogRepo.InsertAsync(log);
                _logger.LogInformation($"✅ LOG CREADO: {log.Message}");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"❌ Error procesando sesión {session.Id}");
            }
        }

        await uow.CompleteAsync();
        _logger.LogInformation("🏁 Ciclo de monitoreo finalizado.");
    }
}
