using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading.Bot;

/// <summary>
/// Interfaz del servicio de estado del bot.
/// Implementado como Singleton para ser accedido desde los dos BackgroundServices.
/// El estado se mantiene en memoria y se persiste en Redis para sobrevivir reinicios.
/// </summary>
public interface IBotStateService
{
    // ─── Control del bot ───
    bool IsRunning { get; }
    Guid? CreatorUserId { get; }
    Task StartAsync(Guid? userId);
    Task StopAsync();
    Task UpdateCreatorUserIdAsync(Guid? userId);

    // ─── Configuración en caliente ───
    ScalpingConfig GetConfig();
    Task UpdateConfigAsync(ScalpingConfig newConfig);

    // ─── Control de posiciones ───
    int GetOpenPositionCount();
    void RegisterOpen(string symbol);
    void RegisterClose(string symbol);
    bool IsSymbolAlreadyOpen(string symbol);
    bool CanOpenNewPosition();

    // ─── Top symbols dinámicos del scanner ───
    List<string> GetActiveSymbols();
    Task RefreshActiveSymbolsAsync(List<string> topScannerSymbols);

    // ─── Estadísticas del día ───
    decimal DailyPnl { get; }
    int DailyTradeCount { get; }
    int DailyWins { get; }
    int DailyLosses { get; }
    void AddDailyPnl(decimal pnl);
    void ResetDailyStats();

    // ─── Timestamp del último ciclo (para debugging) ───
    DateTime? LastCycleAt { get; }
    void UpdateLastCycle();
    
    // ─── Score del Scanner (Persistencia en Redis para tiempo real) ───
    Task SetSymbolScoreAsync(string symbol, int score, int direction);
    Task<(int Score, int Direction)?> GetSymbolScoreAsync(string symbol);

    // ─── Historial de Actividad (Buffer para UI) ───
    Task AddLogAsync(string symbol, string message, string type);
    Task<List<BotActivityLogDto>> GetRecentLogsAsync();
}
