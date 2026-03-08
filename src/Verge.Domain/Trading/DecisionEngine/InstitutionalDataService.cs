using System;
using System.Threading.Tasks;
using Verge.Trading.Integrations;

namespace Verge.Trading.DecisionEngine;

public class InstitutionalDataService : IInstitutionalDataService
{
    private readonly BinanceWebSocketService _binanceWs;

    public InstitutionalDataService(BinanceWebSocketService binanceWs)
    {
        _binanceWs = binanceWs;
    }

    public Task<InstitutionalAnalysisResult> GetInstitutionalDataAsync(string symbol)
    {
        // REAL DATA: Fetching from Binance WebSocket Service
        decimal liquidations = _binanceWs.GetRecentLiquidations(symbol);
        double bidAskRatio = _binanceWs.GetBidAskImbalance(symbol);
        bool isSqueeze = _binanceWs.IsSqueezeDetected(symbol);

        var result = new InstitutionalAnalysisResult
        {
            Symbol = symbol,
            TotalLiquidations24h = liquidations * 12, // Approximation based on rolling window
            BuyLiquidations1h = 0, // Need finer breakdown if required
            SellLiquidations1h = liquidations,
            IsSqueezeDetected = isSqueeze,
            SqueezeType = isSqueeze ? "Live Squeeze" : "None",
            BidAskImbalance = Math.Round(bidAskRatio, 2),
            HasSignificantWall = bidAskRatio > 2.2 || bidAskRatio < 0.45,
            WallDirection = bidAskRatio > 2.2 ? "Support" : (bidAskRatio < 0.45 ? "Resistance" : "None"),
            Summary = isSqueeze 
                ? $"🔥 institutional EDGE: {symbol} in Live Squeeze (${liquidations/1000:F1}K detected)!" 
                : $"📊 Order flow: {bidAskRatio:F2} bid/ask ratio.",
            Timestamp = DateTime.UtcNow
        };

        return Task.FromResult(result);
    }
}
