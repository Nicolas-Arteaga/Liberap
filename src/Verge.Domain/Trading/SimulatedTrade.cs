using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class SimulatedTrade : FullAuditedAggregateRoot<Guid>
{
    public Guid UserId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Side { get; set; }
    public int Leverage { get; set; }
    public decimal Size { get; set; } // Quantity in base currency (e.g. BTC)
    public decimal Amount { get; set; } // Quantity in quote currency (e.g. USDT)
    
    public decimal EntryPrice { get; set; }
    public decimal MarkPrice { get; set; }
    public decimal LiquidationPrice { get; set; }
    public decimal Margin { get; set; } // Initial Margin
    public decimal MarginRate { get; set; }
    
    public decimal UnrealizedPnl { get; set; }
    public decimal ROIPercentage { get; set; }
    public TradeStatus Status { get; set; }
    
    public decimal? ClosePrice { get; set; }
    public decimal? RealizedPnl { get; set; }
    
    public decimal? TpPrice { get; set; }
    public decimal? SlPrice { get; set; }
    
    public decimal EntryFee { get; set; }
    public decimal ExitFee { get; set; }
    public decimal TotalFundingPaid { get; set; }
    
    public DateTime OpenedAt { get; set; }
    public DateTime? ClosedAt { get; set; }
    
    public Guid? TradingSignalId { get; set; }

    /// <summary>
    /// Exchange where this trade was opened. Used by the worker to ensure
    /// price evaluation always uses the same exchange, preventing phantom closes
    /// caused by cross-exchange price discrepancies.
    /// Default: "Binance"
    /// </summary>
    public string Exchange { get; set; } = "Binance";

    /// <summary>
    /// JSON snapshot of Nexus-15 / SCAR / LSE / sizing at open time (Python agent).
    /// Null for manually opened simulated trades.
    /// </summary>
    public string? AgentDecisionJson { get; set; }

    protected SimulatedTrade() { }

    public SimulatedTrade(
        Guid id, 
        Guid userId, 
        string symbol, 
        SignalDirection side, 
        int leverage, 
        decimal entryPrice, 
        decimal size, 
        decimal amount,
        decimal margin,
        decimal liquidationPrice,
        decimal entryFee,
        decimal? tpPrice = null,
        decimal? slPrice = null,
        Guid? tradingSignalId = null,
        string exchange = "Binance") : base(id)
    {
        UserId = userId;
        Symbol = symbol;
        Side = side;
        Leverage = leverage;
        EntryPrice = entryPrice;
        MarkPrice = entryPrice;
        Size = size;
        Amount = amount;
        Margin = margin;
        LiquidationPrice = liquidationPrice;
        EntryFee = entryFee;
        TpPrice = tpPrice;
        SlPrice = slPrice;
        TradingSignalId = tradingSignalId;
        Exchange = exchange;
        Status = TradeStatus.Open;
        OpenedAt = DateTime.UtcNow;
        UnrealizedPnl = 0;
        ROIPercentage = 0;
        MarginRate = 0;
    }
}
