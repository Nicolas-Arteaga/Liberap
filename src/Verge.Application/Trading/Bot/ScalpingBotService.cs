using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;
using Verge.Trading.Bot;
using Verge.Trading.DecisionEngine;
using Verge.Trading.DTOs;
using Verge.Trading.Integrations;

namespace Verge.Trading;

/// <summary>
/// Hosted Service principal del bot de scalping.
/// 
/// Loop principal: cada 5 minutos (configurable).
/// Por cada símbolo activo:
///   1. Descarga velas 5m desde Binance (cache Redis en MarketDataManager)
///   2. Calcula indicadores: HMA50, MA7, MA25, MA99, ATR14
///   3. Lee score del scanner desde AlertHistory (DB)
///   4. Evalúa señal con ScalpingSignalEngine
///   5. Si hay señal y hay cupo de posiciones → abre SimulatedTrade + BotTrade
///   6. Push SignalR al dashboard de VERGE
/// </summary>
public class ScalpingBotService : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly IBotStateService _botState;
    private readonly ILogger<ScalpingBotService> _logger;

    public ScalpingBotService(
        IServiceProvider serviceProvider,
        IBotStateService botState,
        ILogger<ScalpingBotService> logger)
    {
        _serviceProvider = serviceProvider;
        _botState = botState;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🤖 [ScalpingBot] Service started.");

        // Reset estadísticas del día al arrancar
        _botState.ResetDailyStats();

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (_botState.IsRunning)
                {
                    var config = _botState.GetConfig();
                    int intervalMinutes = int.TryParse(config.Timeframe, out int tf) ? tf : 5;
                    
                    // Solo ejecutar si nunca se ejecutó o si ya pasó el intervalo
                    if (_botState.LastCycleAt == null || 
                        DateTime.UtcNow >= _botState.LastCycleAt.Value.AddMinutes(intervalMinutes))
                    {
                        await RunOneCycleAsync(stoppingToken);
                        _botState.UpdateLastCycle();
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ [ScalpingBot] Unhandled error in main cycle");
            }

            // Check cada segundo para reaccionar rápido al "Start" del usuario
            try 
            {
                await Task.Delay(1000, stoppingToken);
            }
            catch (TaskCanceledException)
            {
                break;
            }
        }
    }

    private async Task RunOneCycleAsync(CancellationToken ct)
    {
        var config = _botState.GetConfig();
        
        // Scope inicial para servicios globales
        using (var initialScope = _serviceProvider.CreateScope())
        {
            var hubContext = initialScope.ServiceProvider.GetRequiredService<IHubContext<TradingHub>>();
            var macroService = initialScope.ServiceProvider.GetRequiredService<IMacroSentimentService>();
            var marketDataManager = initialScope.ServiceProvider.GetRequiredService<MarketDataManager>();

            // ─── 1. MACRO SHIELD ───
            var macro = await macroService.GetMacroSentimentAsync();
            if (macro.IsInQuietPeriod && !config.AllowQuietPeriodTrading)
            {
                await SendBotActivityAsync(hubContext, "System", "📅 Quiet Period detectado. Bot en pausa estratégica.", "warn");
                _logger.LogInformation("📅 [ScalpingBot] Quiet Period. Bot esperando...");
                return;
            }

            await SendBotActivityAsync(hubContext, "System", $"🔍 Ciclo de escaneo iniciado ({config.Timeframe}). Buscando oportunidades...", "info");

            // ─── 2. OBTENER SÍMBOLOS ───
            var topSymbols = await marketDataManager.GetTopSymbolsAsync(config.TopSymbolsCount + 5);
            await _botState.RefreshActiveSymbolsAsync(topSymbols);
        }

        var symbols = _botState.GetActiveSymbols();
        _logger.LogInformation("🔍 [ScalpingBot] Ciclo iniciado. {Count} simbolos activos. Posiciones: {Open}/{Max}",
            symbols.Count, _botState.GetOpenPositionCount(), config.MaxOpenPositions);

        // ─── 3. POR CADA SÍMBOLO (Scope Individual para evitar DisposedContext) ───
        foreach (var symbol in symbols)
        {
            if (ct.IsCancellationRequested) break;
            
            if (!_botState.CanOpenNewPosition()) 
            {
                _logger.LogInformation("⚠️ [ScalpingBot] Límite de posiciones alcanzado ({Max}).", config.MaxOpenPositions);
                break;
            }
            if (_botState.IsSymbolAlreadyOpen(symbol)) continue;

            using (var scope = _serviceProvider.CreateScope())
            {
                var sp = scope.ServiceProvider;
                var uowManager = sp.GetRequiredService<IUnitOfWorkManager>();
                
                using (var uow = uowManager.Begin(requiresNew: true))
                {
                    try
                    {
                        var macro = await sp.GetRequiredService<IMacroSentimentService>().GetMacroSentimentAsync();
                        await EvaluateSymbolWithScopeAsync(symbol, config, macro, sp, ct);
                        await uow.CompleteAsync();
                    }
                    catch (Exception ex)
                    {
                        await uow.RollbackAsync();
                        _logger.LogWarning("⚠️ [ScalpingBot] Error evaluando {Symbol}: {Msg}", symbol, ex.Message);
                    }
                }
            }

            await Task.Delay(200, ct);
        }

        using (var finalScope = _serviceProvider.CreateScope())
        {
            var hubContext = finalScope.ServiceProvider.GetRequiredService<IHubContext<TradingHub>>();
            await SendBotActivityAsync(hubContext, "System", "✅ Ciclo completado. Esperando próxima vela...", "success");
        }
    }

    private async Task EvaluateSymbolWithScopeAsync(
        string symbol,
        ScalpingConfig config,
        MacroAnalysisResult macro,
        IServiceProvider sp,
        CancellationToken ct)
    {
        var marketDataManager = sp.GetRequiredService<MarketDataManager>();
        var signalEngine      = sp.GetRequiredService<ScalpingSignalEngine>();
        var simulationService = sp.GetRequiredService<TradingSimulationService>();
        var whaleTracker      = sp.GetRequiredService<IWhaleTrackerService>();
        var webSocket         = sp.GetRequiredService<BinanceWebSocketService>();
        var uowManager        = sp.GetRequiredService<IUnitOfWorkManager>();
        var hubContext        = sp.GetRequiredService<IHubContext<TradingHub>>();
        var profileRepo       = sp.GetRequiredService<IRepository<TraderProfile, Guid>>();
        var simTradeRepo      = sp.GetRequiredService<IRepository<SimulatedTrade, Guid>>();
        var botTradeRepo      = sp.GetRequiredService<IRepository<BotTrade, Guid>>();
        var alertHistoryRepo  = sp.GetRequiredService<IRepository<AlertHistory, Guid>>();

        // ─── A. Precio Live ───
        var livePrice = webSocket.GetLastPrice(symbol);
        if (livePrice == null || livePrice <= 0) return;

        // ─── B. Velas (Redis) ───
        var candles = await marketDataManager.GetCandlesAsync(symbol, config.Timeframe, 150);
        if (candles == null || candles.Count < 110) return;

        var closes = candles.Select(c => c.Close).ToList();

        // ─── C. Indicadores ───
        decimal hma50  = IndicatorCalculator.HMA(closes, 50);
        decimal ma7    = IndicatorCalculator.SMA(closes, 7);
        decimal ma25   = IndicatorCalculator.SMA(closes, 25);
        decimal ma99   = IndicatorCalculator.SMA(closes, 99);
        decimal atr    = IndicatorCalculator.ATR(candles, 14);

        var prevCloses = closes.Take(closes.Count - 1).ToList();
        decimal prevMa7  = IndicatorCalculator.SMA(prevCloses, 7);
        decimal prevMa25 = IndicatorCalculator.SMA(prevCloses, 25);

        // D. Score del Scanner
        var scannerResult = await GetLatestScannerScoreAsync(alertHistoryRepo, symbol.ToUpper(), hubContext);
        int scannerScore = scannerResult.Score;
        int scannerDir   = scannerResult.Direction;
        
        // LOG DE SALTO si score es bajo
        if (scannerScore < config.MinScore)
        {
            if (scannerScore > 0)
            {
                _logger.LogDebug("📊 [ScalpingBot] {Symbol} Score {Score} < {Min}. Ignorado.", symbol, scannerScore, config.MinScore);
                // No enviamos esto a SignalR para no inundar, pero lo dejamos en logs
            }
            return;
        }

        string dirText = scannerDir == 0 ? "LONG" : (scannerDir == 1 ? "SHORT" : "AUTO");
        await SendBotActivityAsync(hubContext, symbol, $"Señal {dirText} detectada (Score: {scannerScore}). Analizando filtros...", "info");

        // ─── E. Otros Datos ───
        var whaleData = await whaleTracker.GetWhaleActivityAsync(symbol);
        var botUserId = _botState.CreatorUserId;
        var profile = await profileRepo.FirstOrDefaultAsync(p => p.UserId == (botUserId ?? Guid.Empty)) 
                      ?? await profileRepo.FirstOrDefaultAsync(_ => true);
        
        if (profile == null) return;

        // ─── F. Evaluación de Señal ───
        var context = new ScalpingContext
        {
            Symbol          = symbol,
            Price           = livePrice.Value,
            HMA50           = hma50,
            MA7             = ma7,
            MA25            = ma25,
            MA99            = ma99,
            ATR             = atr,
            PrevMA7         = prevMa7,
            PrevMA25        = prevMa25,
            ScannerScore    = scannerScore,
            ScannerDirection = scannerDir,
            IsHighVolatility = macro.FearAndGreedIndex < 20,
            IsQuietPeriod   = macro.IsInQuietPeriod,
            WhaleNetFlowScore = whaleData.NetFlowScore,
            VirtualBalance  = profile.VirtualBalance,
            Config          = config,
            Candles         = candles
        };

        var signal = signalEngine.Evaluate(context);
        if (signal == null)
        {
            // LOG EXPLICATIVO para el usuario si el score era bueno pero falló lo demás
            if (scannerScore >= config.MinScore)
            {
                string reason = "Momentum insuficiente (MA7-MA25)";
                
                // Razón específica por dirección
                if (scannerDir == 0 && hma50 > 0 && livePrice < hma50) 
                    reason = "Tendencia Bajista (Precio < HMA50)";
                else if (scannerDir == 1 && hma50 > 0 && livePrice > hma50) 
                    reason = "Tendencia Alcista (Precio > HMA50)";
                
                _logger.LogInformation("⏭️ [ScalpingBot] Oportunidad {Dir} en {Symbol} saltada: {Reason} (Score: {Score})", dirText, symbol, reason, scannerScore);
                await SendBotActivityAsync(hubContext, symbol, $"Oportunidad {dirText} rechazada: {reason}", "warn");
            }
            return;
        }

        // ─── G. ABRIR TRADE ───
        // Nota: Ya estamos dentro de un UOW general por símbolo
        try
        {
            var totalCost = signal.Margin + simulationService.CalculateEntryFee(signal.Notional);
            if (profile.VirtualBalance < totalCost)
            {
                _logger.LogWarning("💸 [ScalpingBot] {Symbol} sin balance. Req: {Req}", symbol, totalCost);
                await SendBotActivityAsync(hubContext, symbol, "Balance insuficiente para abrir posición", "error");
                return;
            }

            var entryFee = simulationService.CalculateEntryFee(signal.Notional);
            var liquidationPrice = simulationService.CalculateLiquidationPrice(signal.EntryPrice, signal.Leverage, signal.Direction);

            var simTrade = new SimulatedTrade(Guid.NewGuid(), profile.UserId, symbol, signal.Direction, signal.Leverage, signal.EntryPrice, signal.PositionSize, signal.Notional, signal.Margin, liquidationPrice, entryFee);
            await simTradeRepo.InsertAsync(simTrade);
            profile.VirtualBalance -= (signal.Margin + entryFee);

            var botTrade = new BotTrade(Guid.NewGuid(), profile.UserId, signal, simTrade.Id)
            {
                Timeframe = config.Timeframe,
                EntryConditionsJson = JsonSerializer.Serialize(signal)
            };
            await botTradeRepo.InsertAsync(botTrade);

            _botState.RegisterOpen(symbol);

            // Notificaciones
            await hubContext.Clients.All.SendAsync("BotTradeOpened", new {
                symbol, direction = signal.Direction.ToString(), entryPrice = signal.EntryPrice, score = signal.ScannerScore, botTradeId = botTrade.Id
            });

            await SendBotActivityAsync(hubContext, symbol, $"🚀 ¡ORDEN ABIERTA! {signal.Direction} x{signal.Leverage}", "success");
            _logger.LogInformation("🚀 [ScalpingBot] TRADE ABIERTO: {Symbol} {Dir} (Score: {Score})", symbol, signal.Direction, scannerScore);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error abriendo trade en DB para {Symbol}", symbol);
        }
    }

    /// <summary>
    /// Lee el score y dirección más reciente del scanner para un símbolo.
    /// </summary>
    private async Task<(int Score, int Direction)> GetLatestScannerScoreAsync(
        IRepository<AlertHistory, Guid> alertHistoryRepo,
        string symbol,
        IHubContext<TradingHub> hubContext)
    {
        try
        {
            // 🚀 Primero intentamos leer de REDIS (Sync ultra-rápido)
            var redisResult = await _botState.GetSymbolScoreAsync(symbol);
            if (redisResult != null) return (redisResult.Value.Score, redisResult.Value.Direction);

            // Fallback: Si no está en Redis, buscamos en DB (ventana de 24h)
            var cutoff = DateTime.UtcNow.AddHours(-24);
            var query = await alertHistoryRepo.GetQueryableAsync();
            var searchSymbol = symbol.ToUpper().Trim();
            
            var latest = query
                .Where(a => a.Symbol.ToUpper() == searchSymbol && a.EmittedAt >= cutoff)
                .OrderByDescending(a => a.EmittedAt)
                .FirstOrDefault();

            if (latest == null) return (0, 2); // 2 = Auto/None
            return (latest.Confidence, latest.Direction);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error consultando AlertHistory para {Symbol}", symbol);
            return (0, 2);
        }
    }

    private async Task SendBotActivityAsync(IHubContext<TradingHub> hubContext, string symbol, string message, string type)
    {
        try 
        {
            await _botState.AddLogAsync(symbol, message, type);
            await hubContext.Clients.All.SendAsync("BotActivityLog", new 
            {
                symbol,
                message,
                type,
                timestamp = DateTime.UtcNow
            });
        }
        catch { /* Fire and forget */ }
    }

    private string formatCurrency(decimal value)
    {
        return value.ToString("F2") + " USDT";
    }
}
