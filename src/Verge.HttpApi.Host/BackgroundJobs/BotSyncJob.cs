using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Verge.Trading;
using Verge.Freqtrade;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;

namespace Verge.BackgroundJobs;

/// <summary>
/// Trabajo que asegura que el motor de Freqtrade tenga siempre los bots 
/// que figuran como activos en la base de datos.
/// </summary>
public class BotSyncJob : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<BotSyncJob> _logger;
    private readonly Volo.Abp.Guids.IGuidGenerator _guidGenerator;

    public BotSyncJob(
        IServiceScopeFactory scopeFactory, 
        ILogger<BotSyncJob> logger,
        Volo.Abp.Guids.IGuidGenerator guidGenerator)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _guidGenerator = guidGenerator;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 BotSyncJob iniciado. Asegurando persistencia de bots...");

        // Espera inicial para que Freqtrade arranque
        await Task.Delay(15000, stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await SynchronizeBotsAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Error durante la sincronización de bots");
            }

            // Repetir cada 2 minutos
            await Task.Delay(TimeSpan.FromMinutes(2), stoppingToken);
        }
    }

    private async Task SynchronizeBotsAsync()
    {
        using var scope = _scopeFactory.CreateScope();
        var botRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingBot, Guid>>();
        var freqtradeService = scope.ServiceProvider.GetRequiredService<IFreqtradeAppService>();
        var uowManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();
        var principalAccessor = scope.ServiceProvider.GetRequiredService<Volo.Abp.Security.Claims.ICurrentPrincipalAccessor>();

        // Simular un usuario autenticado para el background job (evita AbpAuthorizationException)
        var claims = new[] { new System.Security.Claims.Claim(Volo.Abp.Security.Claims.AbpClaimTypes.UserId, Guid.Empty.ToString()) };
        var identity = new System.Security.Claims.ClaimsIdentity(claims, "BackgroundJob");
        var principal = new System.Security.Claims.ClaimsPrincipal(identity);

        using var principalScope = principalAccessor.Change(principal);
        using var uow = uowManager.Begin();
        
        // 1. Obtener bots activos de la DB
        var activeBots = await botRepo.GetListAsync();
        
        _logger.LogDebug("🔄 Sincronizando bots (DB: {DbCount})...", activeBots.Count);

        // 2. Obtener estado actual de Freqtrade
        var status = await freqtradeService.GetStatusAsync();
        var currentWhitelist = status.ActivePairs ?? new System.Collections.Generic.List<string>();

        // A. DISCOVERY: De Freqtrade -> Base de Datos
        // Si hay algo en Freqtrade que no está en la DB, lo importamos
        foreach (var pair in currentWhitelist)
        {
            // Limpiar símbolo (e.g., "BTC/USDT:USDT" -> "BTCUSDT")
            var cleanSymbol = pair.Replace("/", "").Split(':')[0].ToUpper();
            
            var inDb = activeBots.Any(x => x.Symbol.Equals(cleanSymbol, StringComparison.OrdinalIgnoreCase));
            if (!inDb)
            {
                _logger.LogInformation("✨ Descubierto nuevo bot en Freqtrade: {Pair}. Importando a DB...", pair);
                await botRepo.InsertAsync(new TradingBot(
                    _guidGenerator.Create(),
                    cleanSymbol,
                    "VergeFreqAIStrategy", // Default
                    "15m",                 // Default
                    100,                   // Default stake
                    10,                    // Default leverage
                    200,                   // Default TP
                    1,                     // Default SL
                    null                   // System Created
                ));
            }
        }

        // B. CONSISTENCY: De Base de Datos -> Freqtrade
        // Si hay algo en la DB marcado como activo que NO está en Freqtrade, lo re-inyectamos
        foreach (var bot in activeBots.Where(x => x.IsActive))
        {
            // Normalizar símbolo para comparar (Freqtrade usa BASE/QUOTE:QUOTE)
            var expectedPair = bot.Symbol;
            if (!expectedPair.Contains("/")) expectedPair = $"{expectedPair.Replace("USDT", "")}/USDT:USDT";

            var isMissing = !currentWhitelist.Any(p => p.Equals(expectedPair, StringComparison.OrdinalIgnoreCase));

            if (isMissing)
            {
                _logger.LogWarning("⚠️ Bot {Symbol} falta en Freqtrade. Re-inyectando...", bot.Symbol);
                
                try 
                {
                    await freqtradeService.StartBotAsync(new Freqtrade.FreqtradeCreateBotDto
                    {
                        Pair = bot.Symbol,
                        Strategy = bot.Strategy,
                        Timeframe = bot.Timeframe,
                        StakeAmount = bot.StakeAmount,
                        Leverage = bot.Leverage,
                        TpPercent = bot.TakeProfitPercentage,
                        SlPercent = bot.StopLossPercentage
                    });
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "❌ Fallo al re-inyectar bot {Symbol}", bot.Symbol);
                }
            }
        }
        
        await uow.CompleteAsync();
    }
}
