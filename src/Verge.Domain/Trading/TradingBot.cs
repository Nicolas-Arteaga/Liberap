using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

/// <summary>
/// Represetna la configuración persistente de un bot/par en Freqtrade.
/// Permite re-inyectar el bot si Freqtrade se reinicia.
/// </summary>
public class TradingBot : FullAuditedAggregateRoot<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public string Strategy { get; set; } = string.Empty;
    public string Timeframe { get; set; } = string.Empty;
    public decimal StakeAmount { get; set; }
    public int Leverage { get; set; }
    public decimal TakeProfitPercentage { get; set; }
    public decimal StopLossPercentage { get; set; }
    public bool IsActive { get; set; }
    public Guid? UserId { get; set; }

    protected TradingBot() { }

    public TradingBot(
        Guid id, 
        string symbol, 
        string strategy, 
        string timeframe, 
        decimal stakeAmount, 
        int leverage,
        decimal tp = 2.0m,
        decimal sl = 1.0m,
        Guid? userId = null) : base(id)
    {
        Symbol = symbol.ToUpper();
        Strategy = strategy;
        Timeframe = timeframe;
        StakeAmount = stakeAmount;
        Leverage = leverage;
        TakeProfitPercentage = tp;
        StopLossPercentage = sl;
        IsActive = true;
        UserId = userId;
    }
}
