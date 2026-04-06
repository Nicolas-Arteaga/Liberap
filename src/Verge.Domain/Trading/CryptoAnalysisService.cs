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

        if (avgLoss == 0) return avgGain == 0 ? 50 : 100;
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

        decimal rsiOversold = 30;
        decimal rsiOverbought = 70;

        if (strategy.Style == TradingStyle.Scalping)
        {
            rsiOversold = 35; // Más sensible
            rsiOverbought = 65;
        }
        else if (strategy.Style == TradingStyle.SwingTrading || strategy.Style == TradingStyle.PositionTrading)
        {
            rsiOversold = 25; // Más exigente
            rsiOverbought = 75;
        }

        if (isLong && rsi <= rsiOversold)
        {
            reason = $"RSI en sobreventa ({rsi:F2}) para LONG ({strategy.Style}). ¡Oportunidad detectada!";
            return true;
        }
        
        if (!isLong && rsi >= rsiOverbought)
        {
            reason = $"RSI en sobrecompra ({rsi:F2}) para SHORT ({strategy.Style}). ¡Oportunidad detectada!";
            return true;
        }

        reason = $"Analizando {session.Symbol} ({strategy.Style}) - RSI actual: {rsi:F2}";
        return false;
    }

    private bool CheckPreparedToBuyActive(TradingSession session, TradingStrategy strategy, out string reason)
    {
        int waitMinutes = 2; // Default for DayTrading

        if (strategy.Style == TradingStyle.Scalping) waitMinutes = 0; // Inmediato
        else if (strategy.Style == TradingStyle.SwingTrading) waitMinutes = 15;
        else if (strategy.Style == TradingStyle.PositionTrading) waitMinutes = 60;

        if (session.LastModificationTime.HasValue && (DateTime.UtcNow - session.LastModificationTime.Value).TotalMinutes >= waitMinutes)
        {
            reason = $"Condición de confirmación ({waitMinutes}m) cumplida. Avanzando a COMPRA. Precio: {session.Symbol}";
            return true;
        }

        reason = $"Esperando confirmación de {waitMinutes} minutos para entrada ({strategy.Style})...";
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

    public (TradingStyle Style, string Reason) RecommendTradingStyle(List<MarketCandleModel> marketData)
    {
        if (marketData == null || marketData.Count < 14) 
        {
            return (TradingStyle.DayTrading, "Datos insuficientes (menos de 14 periodos). Day Trading por defecto.");
        }

        var prices = marketData.Select(x => x.Close).ToList();
        var rsi = CalculateRSI(prices);

        var recentCandles = marketData.Skip(Math.Max(0, marketData.Count - 5)).ToList();
        decimal avgVolatility = 0;
        if (recentCandles.Any())
        {
            avgVolatility = recentCandles.Average(x => x.Low > 0 ? (x.High - x.Low) / x.Low * 100 : 0);
        }

        if (avgVolatility > 1.5m)
        {
            return (TradingStyle.Scalping, $"Alta volatilidad detectada ({avgVolatility:F2}% promedio reciente). Recomendamos SCALPING para entradas y salidas rápidas.");
        }

        if (rsi > 65 || rsi < 35)
        {
            return (TradingStyle.SwingTrading, $"Tendencia marcada detectada (RSI: {rsi:F2}). Recomendamos SWING TRADING para aprovechar la inercia del mercado.");
        }

        if (rsi > 40 && rsi < 60 && avgVolatility < 0.5m)
        {
            return (TradingStyle.GridTrading, $"Mercado en rango lateral de baja volatilidad. GRID TRADING es ideal para este escenario.");
        }

        return (TradingStyle.DayTrading, $"Condiciones de mercado estándar (Volatilidad: {avgVolatility:F2}%, RSI: {rsi:F2}). DAY TRADING balanceado.");
    }

    public bool IsZombieData(List<MarketCandleModel> candles)
    {
        if (candles == null || (candles.Count < 10)) return false;
        var recent = candles.Skip(Math.Max(0, candles.Count - 10)).ToList();
        var first = recent.First().Close;
        // If all 10 recent candles have the exact same price, it's a zombie/stagnant symbol
        // Relaxed for now: Return false to ensure all symbols are analyzed as requested
        return false; 
    }
}
