using System;
using System.Collections.Generic;
using System.Linq;
using Volo.Abp.Domain.Services;

namespace Verge.Trading;

public class CryptoAnalysisService : DomainService
{
    public decimal CalculateRSI(List<decimal> prices, int period = 14)
    {
        if (prices.Count < period + 1) return 50; // Not enough data

        decimal avgGain = 0;
        decimal avgLoss = 0;

        for (int i = 1; i <= period; i++)
        {
            decimal diff = prices[i] - prices[i - 1];
            if (diff >= 0) avgGain += diff;
            else avgLoss -= diff;
        }

        avgGain /= period;
        avgLoss /= period;

        for (int i = period + 1; i < prices.Count; i++)
        {
            decimal diff = prices[i] - prices[i - 1];
            decimal gain = diff >= 0 ? diff : 0;
            decimal loss = diff < 0 ? -diff : 0;

            avgGain = (avgGain * (period - 1) + gain) / period;
            avgLoss = (avgLoss * (period - 1) + loss) / period;
        }

        if (avgLoss == 0) return 100;
        
        decimal rs = avgGain / avgLoss;
        return 100 - (100 / (1 + rs));
    }

    public bool ShouldAdvanceStage(TradingSession session, TradingStrategy strategy, List<MarketCandleModel> marketData, out string reason)
    {
        reason = string.Empty;
        if (!marketData.Any()) return false;

        var currentPrice = marketData.Last().Close;
        var prices = marketData.Select(x => x.Close).ToList();

        switch (session.CurrentStage)
        {
            case TradingStage.Evaluating:
                return CheckEvaluatingToPrepared(session, strategy, prices, out reason);

            case TradingStage.Prepared:
                return CheckPreparedToBuyActive(session, strategy, out reason);

            case TradingStage.BuyActive:
                return CheckBuyActiveToSellActive(session, strategy, currentPrice, out reason);

            default:
                return false;
        }
    }

    private bool CheckEvaluatingToPrepared(TradingSession session, TradingStrategy strategy, List<decimal> prices, out string reason)
    {
        decimal rsi = CalculateRSI(prices);
        bool isLong = strategy.DirectionPreference == SignalDirection.Long;

        if (isLong && rsi < 30)
        {
            reason = $"RSI en sobreventa ({rsi:F2}) para LONG. ¡Oportunidad detectada!";
            return true;
        }
        
        if (!isLong && rsi > 70)
        {
            reason = $"RSI en sobrecompra ({rsi:F2}) para SHORT. ¡Oportunidad detectada!";
            return true;
        }

        reason = $"Analizando {session.Symbol} - RSI actual: {rsi:F2}";
        return false;
    }

    private bool CheckPreparedToBuyActive(TradingSession session, TradingStrategy strategy, out string reason)
    {
        if (session.LastModificationTime.HasValue && (DateTime.UtcNow - session.LastModificationTime.Value).TotalMinutes >= 2)
        {
            reason = $"Condición cumplida. Avanzando a COMPRA. Precio: {session.Symbol}";
            return true;
        }

        reason = "Esperando confirmación de volumen para entrada...";
        return false;
    }

    private bool CheckBuyActiveToSellActive(TradingSession session, TradingStrategy strategy, decimal currentPrice, out string reason)
    {
        if (!session.EntryPrice.HasValue || !session.TakeProfitPrice.HasValue || !session.StopLossPrice.HasValue)
        {
            reason = "Precios objetivo no configurados";
            return false;
        }

        bool isLong = strategy.DirectionPreference == SignalDirection.Long;

        if (isLong)
        {
            if (currentPrice >= session.TakeProfitPrice)
            {
                reason = $"🎯 Take Profit alcanzado: {currentPrice:F2}. Cerrando posición.";
                return true;
            }
            if (currentPrice <= session.StopLossPrice)
            {
                reason = $"🛑 Stop Loss alcanzado: {currentPrice:F2}. Cerrando posición.";
                return true;
            }
        }
        else
        {
            if (currentPrice <= session.TakeProfitPrice)
            {
                reason = $"🎯 Take Profit alcanzado: {currentPrice:F2}. Cerrando posición.";
                return true;
            }
            if (currentPrice >= session.StopLossPrice)
            {
                reason = $"🛑 Stop Loss alcanzado: {currentPrice:F2}. Cerrando posición.";
                return true;
            }
        }

        decimal pnl = isLong 
            ? (currentPrice - session.EntryPrice.Value) / session.EntryPrice.Value * 100
            : (session.EntryPrice.Value - currentPrice) / session.EntryPrice.Value * 100;

        reason = $"💰 Monitoreando posición - Ganancia actual: {pnl:F2}% (Precio: {currentPrice:F2})";
        return false;
    }
}
