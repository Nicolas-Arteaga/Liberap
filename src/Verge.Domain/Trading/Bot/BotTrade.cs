using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading.Bot;

/// <summary>
/// Entidad de dominio que representa un trade abierto por el bot de scalping.
/// 
/// Relación: BotTrade → SimulatedTrade (1:1)
/// El bot usa SimulatedTrade para la lógica de balance y PnL (ya implementada).
/// BotTrade agrega la metadata de scalping: SL, TP1, TP2, trailing, condiciones de entrada.
/// </summary>
public class BotTrade : FullAuditedAggregateRoot<Guid>
{
    // ─── Datos del trade ───
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }
    public string Timeframe { get; set; } = "5";

    // ─── Precios calculados por el ScalpingSignalEngine ───
    public decimal EntryPrice { get; set; }
    public decimal StopLoss { get; set; }
    public decimal TakeProfit1 { get; set; }   // Cierre parcial 50%
    public decimal TakeProfit2 { get; set; }   // Cierre total + trailing

    // ─── Parámetros de la posición ───
    public int Leverage { get; set; }
    public decimal Margin { get; set; }        // USDT como collateral
    public decimal PositionSize { get; set; }  // Coins totales
    public decimal PositionSizeRemaining { get; set; } // Coins restantes después del cierre parcial

    // ─── Estado del trade ───
    public BotTradeStatus Status { get; set; } = BotTradeStatus.Open;
    public bool PartialCloseDone { get; set; } = false;
    public bool TrailingActive { get; set; } = false;
    public decimal? TrailingStopPrice { get; set; }  // Precio actual del trailing SL

    // ─── PnL ───
    public decimal? PartialPnl { get; set; }   // PnL del 50% cerrado en TP1
    public decimal? FinalPnl { get; set; }     // PnL del 50% restante
    public decimal? TotalPnl { get; set; }     // Total realizado
    public string? CloseReason { get; set; }   // "StopLoss" | "TakeProfit1+Trailing" | "TakeProfit2"

    // ─── Timestamps ───
    public DateTime OpenedAt { get; set; } = DateTime.UtcNow;
    public DateTime? PartialClosedAt { get; set; }
    public DateTime? ClosedAt { get; set; }

    // ─── Metadata de la señal (para auditoría y backtesting) ───
    public decimal ATR { get; set; }
    public decimal ATRPercent { get; set; }
    public decimal SLPercent { get; set; }
    public int ScannerScore { get; set; }
    public string EntryConditionsJson { get; set; } = "{}";  // JSON completo del ScalpingSignal

    // ─── FK a SimulatedTrade ───
    public Guid SimulatedTradeId { get; set; }

    // ─── ID del usuario (para filtrar en el panel) ───
    public Guid UserId { get; set; }

    protected BotTrade() { }

    public BotTrade(Guid id, Guid userId, ScalpingSignal signal, Guid simulatedTradeId) : base(id)
    {
        UserId             = userId;
        Symbol             = signal.Symbol;
        Direction          = signal.Direction;
        EntryPrice         = signal.EntryPrice;
        StopLoss           = signal.StopLoss;
        TakeProfit1        = signal.TakeProfit1;
        TakeProfit2        = signal.TakeProfit2;
        Leverage           = signal.Leverage;
        Margin             = signal.Margin;
        PositionSize       = signal.PositionSize;
        PositionSizeRemaining = signal.PositionSize;
        ATR                = signal.ATR;
        ATRPercent         = signal.ATRPercent;
        SLPercent          = signal.SLPercent;
        ScannerScore       = signal.ScannerScore;
        SimulatedTradeId   = simulatedTradeId;
        Status             = BotTradeStatus.Open;
        OpenedAt           = DateTime.UtcNow;
    }

    /// <summary>Registra el cierre parcial del 50% en TakeProfit1.</summary>
    public void RegisterPartialClose(decimal partialPnl, decimal trailingStopPrice)
    {
        PartialCloseDone     = true;
        TrailingActive       = true;
        PartialPnl           = partialPnl;
        PartialClosedAt      = DateTime.UtcNow;
        PositionSizeRemaining = PositionSize * 0.5m; // 50% restante
        TrailingStopPrice    = trailingStopPrice;
        Status               = BotTradeStatus.PartialClose;
    }

    /// <summary>Registra el cierre final de la posición (trailing o TP2).</summary>
    public void RegisterClose(decimal finalPnl, string reason)
    {
        FinalPnl    = finalPnl;
        TotalPnl    = (PartialPnl ?? 0) + finalPnl;
        CloseReason = reason;
        ClosedAt    = DateTime.UtcNow;
        Status      = finalPnl >= 0 ? BotTradeStatus.Win : BotTradeStatus.Loss;
    }

    /// <summary>Actualiza el precio del trailing stop siguiendo el HMA50.</summary>
    public void UpdateTrailingStop(decimal newTrailingPrice)
    {
        TrailingStopPrice = newTrailingPrice;
    }
}

/// <summary>Estado posible de un BotTrade.</summary>
public enum BotTradeStatus
{
    Open         = 0,  // Posición abierta entera
    PartialClose = 1,  // 50% cerrado en TP1, trailing activo
    Win          = 2,  // Cerrado con ganancia
    Loss         = 3,  // Cerrado con pérdida (stop loss o trailing debajo de entry)
    Cancelled    = 4   // Cancelado manualmente desde el panel
}
