using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Verge.Trading.Integrations;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class CryptoAnalysisAppService : ApplicationService, ICryptoAnalysisAppService
{
    private readonly IFreeCryptoNewsService _freeNewsService;
    private readonly CryptoAnalysisService _cryptoAnalysisService;
    private readonly MarketDataManager _marketDataManager;
    private readonly IRepository<TradingSession, Guid> _sessionRepository;

    public CryptoAnalysisAppService(
        IFreeCryptoNewsService freeNewsService,
        CryptoAnalysisService cryptoAnalysisService,
        MarketDataManager marketDataManager,
        IRepository<TradingSession, Guid> sessionRepository)
    {
        _freeNewsService = freeNewsService;
        _cryptoAnalysisService = cryptoAnalysisService;
        _marketDataManager = marketDataManager;
        _sessionRepository = sessionRepository;
    }

    public async Task<SentimentAnalysisDto> GetSentimentForSymbolAsync(string symbol)
    {
        var result = await _freeNewsService.GetSentimentAsync(symbol);

        if (result == null) return null;

        return new SentimentAnalysisDto
        {
            Sentiment = result.Label,
            Confidence = (float)result.Score,
            Scores = new Dictionary<string, float> { { result.Label, (float)result.Score } }
        };
    }

    public async Task<EnhancedAnalysisDto> GetEnhancedAnalysisAsync(Guid sessionId)
    {
        var session = await _sessionRepository.GetAsync(sessionId);
        var marketData = await _marketDataManager.GetCandlesAsync(session.Symbol, session.Timeframe, 30);
        
        var prices = marketData.Select(x => x.Close).ToList();
        var rsi = (decimal)_cryptoAnalysisService.CalculateRSI(prices);

        var sentiment = await GetSentimentForSymbolAsync(session.Symbol);

        var recommendation = GenerateRecommendation(rsi, sentiment);

        return new EnhancedAnalysisDto
        {
            Rsi = rsi,
            Sentiment = sentiment,
            Summary = $"Análisis para {session.Symbol}: RSI {rsi:F2}, Sentimiento {sentiment?.Sentiment ?? "N/A"}",
            Recommendation = recommendation
        };
    }

    private string GenerateRecommendation(decimal rsi, SentimentAnalysisDto sentiment)
    {
        if (sentiment == null) return "No hay datos de sentimiento suficientes.";

        if (rsi < 35 && sentiment.Sentiment == "positive")
            return "🔥 OPORTUNIDAD FUERTE: Sobreventa + Sentimiento Positivo";
        
        if (rsi > 65 && sentiment.Sentiment == "negative")
            return "⚠️ RIESGO ALTO: Sobrecompra + Sentimiento Negativo";

        if (rsi < 30) return "📉 Sobreventa detectada, monitoreando rebote";
        if (rsi > 70) return "📈 Sobrecompra detectada, posible corrección";

        return "⚖️ Mercado neutral, sin señales claras";
    }

    private List<string> GetSimulatedNews(string symbol)
    {
        var baseNews = new List<string>
        {
            $"{symbol} is showing strong accumulation patterns",
            $"Institutional interest in {symbol} continues to grow",
            $"New regulatory updates could impact {symbol} performance",
            $"Technical analysts predict a breakout for {symbol}",
            $"Community sentiment remains bullish on {symbol} ecosystem"
        };

        // Devolver una muestra aleatoria o fija
        return baseNews.OrderBy(x => Guid.NewGuid()).Take(3).ToList();
    }
}
