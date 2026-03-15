using System;
using Volo.Abp.Domain.Services;

namespace Verge.Trading;

/// <summary>
/// Domain service for all trading simulation calculations.
/// Based on Binance Isolated Margin formulas.
/// </summary>
public class TradingSimulationService : DomainService
{
    private const decimal TakerFeeRate = 0.0004m;      // 0.04%
    private const decimal MaintenanceMarginRate = 0.005m;  // 0.5% (MMR)
    private const decimal FundingRate = 0.0001m;       // Simulated 0.01% every 8h

    /// <summary>
    /// Calculates initial margin (collateral required to open the position).
    /// InitialMargin = Amount / Leverage
    /// </summary>
    public decimal CalculateInitialMargin(decimal amount, int leverage)
        => amount / leverage;

    /// <summary>
    /// Calculates entry taker fee: Amount * TakerFeeRate 
    /// (on the full notional value, not just margin)
    /// </summary>
    public decimal CalculateEntryFee(decimal amount)
        => amount * TakerFeeRate;

    /// <summary>
    /// Calculates exit taker fee on the notional at closing price.
    /// ExitFee = Size * ClosePrice * TakerFeeRate
    /// </summary>
    public decimal CalculateExitFee(decimal size, decimal closePrice)
        => size * closePrice * TakerFeeRate;

    /// <summary>
    /// Calculates position size (quantity) in base asset.
    /// Size = Amount / EntryPrice
    /// </summary>
    public decimal CalculatePositionSize(decimal amount, decimal entryPrice)
        => amount / entryPrice;

    /// <summary>
    /// Calculates isolated margin liquidation price.
    ///
    /// For LONG:
    ///   LiqPrice = EntryPrice * (1 - 1/Leverage + MMR)
    ///
    /// For SHORT:
    ///   LiqPrice = EntryPrice * (1 + 1/Leverage - MMR)
    /// </summary>
    public decimal CalculateLiquidationPrice(decimal entryPrice, int leverage, SignalDirection side)
    {
        decimal leverageFactor = 1m / leverage;

        if (side == SignalDirection.Long)
            return entryPrice * (1m - leverageFactor + MaintenanceMarginRate);
        else
            return entryPrice * (1m + leverageFactor - MaintenanceMarginRate);
    }

    /// <summary>
    /// Calculates unrealized PnL.
    ///
    /// Long PnL = (MarkPrice - EntryPrice) * Size
    /// Short PnL = (EntryPrice - MarkPrice) * Size
    /// </summary>
    public decimal CalculateUnrealizedPnl(decimal entryPrice, decimal markPrice, decimal size, SignalDirection side)
    {
        if (side == SignalDirection.Long)
            return (markPrice - entryPrice) * size;
        else
            return (entryPrice - markPrice) * size;
    }

    /// <summary>
    /// Calculates ROI percentage based on unrealized PnL vs initial margin.
    /// ROI = UnrealizedPnl / InitialMargin * 100
    /// </summary>
    public decimal CalculateROI(decimal unrealizedPnl, decimal initialMargin)
        => initialMargin == 0 ? 0 : (unrealizedPnl / initialMargin) * 100m;

    /// <summary>
    /// Calculates realized PnL after closing a position (minus fees).
    /// RealizedPnl = GrossPnl - EntryFee - ExitFee - FundingPaid
    /// </summary>
    public decimal CalculateRealizedPnl(
        decimal entryPrice,
        decimal closePrice,
        decimal size,
        SignalDirection side,
        decimal entryFee,
        decimal exitFee,
        decimal totalFundingPaid)
    {
        decimal grossPnl;
        if (side == SignalDirection.Long)
            grossPnl = (closePrice - entryPrice) * size;
        else
            grossPnl = (entryPrice - closePrice) * size;

        return grossPnl - entryFee - exitFee - totalFundingPaid;
    }

    /// <summary>
    /// Calculates funding payment for one funding event.
    /// FundingPayment = Size * MarkPrice * FundingRate
    /// </summary>
    public decimal CalculateFundingPayment(decimal size, decimal markPrice)
        => size * markPrice * FundingRate;

    /// <summary>
    /// Returns true if the trade should be liquidated based on current mark price.
    /// </summary>
    public bool IsLiquidationTriggered(decimal markPrice, decimal liquidationPrice, SignalDirection side)
    {
        if (side == SignalDirection.Long)
            return markPrice <= liquidationPrice;
        else
            return markPrice >= liquidationPrice;
    }
}
