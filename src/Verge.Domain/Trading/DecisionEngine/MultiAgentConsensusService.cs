using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Services;

namespace Verge.Trading.DecisionEngine;

public class MultiAgentConsensusService : DomainService, IMultiAgentConsensusService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<MultiAgentConsensusService> _logger;

    // 🚀 AI Response Cache (Sprint 5 Optimization)
    // Key: {Symbol}_{Style}
    private static readonly ConcurrentDictionary<string, (AgentConsensusResult Result, DateTime Expiry)> _consensusCache = new();
    private const int CacheDurationMinutes = 10;

    public MultiAgentConsensusService(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<MultiAgentConsensusService> logger)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<AgentConsensusResult> GetConsensusAsync(MarketContext context, TradingStyle style)
    {
        var cacheKey = $"{context.Symbol}_{style}";
        
        // 1. Check Cache first to save AI tokens (429 Protection)
        if (_consensusCache.TryGetValue(cacheKey, out var cacheItem) && DateTime.UtcNow < cacheItem.Expiry)
        {
            _logger.LogInformation("🧠 [AI CACHE] Using cached consensus for {Symbol} ({Style})", context.Symbol, style);
            return cacheItem.Result;
        }

        var result = new AgentConsensusResult();
        bool anyRateLimitHit = false;
        
        try
        {
            // 2. Dispatch Specialized Agents
            var techTask = GetTechnicalOpinionAsync(context, style);
            var sentimentTask = GetSentimentOpinionAsync(context, style);

            await Task.WhenAll(techTask, sentimentTask);

            var techOpinion = await techTask;
            var sentimentOpinion = await sentimentTask;

            // Detect 429/Rate limit from reasoning strings (set in CallGroq/CallGemini)
            if (techOpinion.Reasoning.Contains("429") || sentimentOpinion.Reasoning.Contains("429"))
            {
                anyRateLimitHit = true;
            }

            if (anyRateLimitHit)
            {
                _logger.LogWarning("⚠️ [AI LIMIT] Rate limit detected. Activating Technical Fallback Mode for {Symbol}...", context.Symbol);
                result = CalculateTechnicalFallback(context, style);
            }
            else
            {
                result.AgentOpinions.Add("TechnicalAgent", techOpinion.Reasoning);
                result.AgentOpinions.Add("SentimentAgent", sentimentOpinion.Reasoning);

                // 2. Devil's Advocate (Challenges the leading bias)
                float leadingScore = (techOpinion.Score + sentimentOpinion.Score) / 2;
                var devilOpinion = await GetDevilAdvocateOpinionAsync(context, style, leadingScore, result.AgentOpinions);
                result.AgentOpinions.Add("DevilAdvocate", devilOpinion.Reasoning);

                // 3. Final Aggregation
                result.Score = (techOpinion.Score * 0.4f) + (sentimentOpinion.Score * 0.4f) + (devilOpinion.Score * 0.2f);
                
                result.Reasoning = $"[AI Consensus] Final Score: {result.Score:F1}. " +
                                   $"Tech: {techOpinion.Score:F0}, Sent: {sentimentOpinion.Score:F0}. " +
                                   $"Devil: {devilOpinion.Reasoning.Take(50)}...";
            }

            // 4. Update Cache
            _consensusCache[cacheKey] = (result, DateTime.UtcNow.AddMinutes(CacheDurationMinutes));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in MultiAgentConsensusService");
            result = CalculateTechnicalFallback(context, style); // Fallback on exception too
        }

        return result;
    }

    private AgentConsensusResult CalculateTechnicalFallback(MarketContext context, TradingStyle style)
    {
        var result = new AgentConsensusResult();
        float score = 50;

        if (context.Technicals != null)
        {
            float rsiScore = 50;
            if (context.Technicals.Rsi < 35) rsiScore = 80; // Oversold -> High Long bias
            else if (context.Technicals.Rsi > 65) rsiScore = 20; // Overbought -> High Short bias

            float trendScore = 50;
            if (context.MarketRegime?.Regime == MarketRegimeType.BullTrend) trendScore = 80;
            else if (context.MarketRegime?.Regime == MarketRegimeType.BearTrend) trendScore = 20;

            // Simple weighted average for technical fallback
            score = (rsiScore * 0.5f) + (trendScore * 0.5f);
        }

        result.Score = score;
        result.Reasoning = $"⚠️ [TECH-FALLBACK] AI Limited by Quota. Score calculated via RSI/Regime. (Score: {score:F1})";
        result.AgentOpinions.Add("EmergencySystem", "AI Rate limited. Using deterministic technical rules.");
        
        return result;
    }

    private async Task<(float Score, string Reasoning)> GetTechnicalOpinionAsync(MarketContext context, TradingStyle style)
    {
        var prompt = $"Analyze technicals for {style} trading. RSI: {context.Technicals?.Rsi}, MACD: {context.Technicals?.MacdHistogram}, ATR: {context.Technicals?.Atr}. " +
                     $"Structure: {context.MarketRegime?.Structure}. Trend Strength: {context.MarketRegime?.TrendStrength}. " +
                     "Return a JSON with 'score' (0-100) and 'reasoning'.";

        return await CallGroqAsync(prompt, "Technical Specialist");
    }

    private async Task<(float Score, string Reasoning)> GetSentimentOpinionAsync(MarketContext context, TradingStyle style)
    {
        var newsCount = context.News?.Count ?? 0;
        var prompt = $"Analyze sentiment for {style} trading. Fear&Greed: {context.FearAndGreed?.Value}. News count: {newsCount}. " +
                     $"Global Sentiment: {context.GlobalSentiment?.Label} ({context.GlobalSentiment?.Score}). " +
                     "Return a JSON with 'score' (0-100) and 'reasoning'.";

        return await CallGeminiAsync(prompt, "Sentiment Specialist");
    }

    private async Task<(float Score, string Reasoning)> GetDevilAdvocateOpinionAsync(MarketContext context, TradingStyle style, float currentScore, Dictionary<string, string> opinions)
    {
        var bias = currentScore > 50 ? "BULLISH" : "BEARISH";
        var prompt = $"You are a Skeptic Trader. The current consensus is {bias} (Score: {currentScore}). " +
                     $"Opinions: {string.Join(" | ", opinions.Values)}. " + bias +
                     $"Challenge this bias. Find risks. Return a adjusted 'score' (0-100) and 'reasoning'.";

        return await CallGroqAsync(prompt, "Devil's Advocate");
    }

    private async Task<(float Score, string Reasoning)> CallGroqAsync(string prompt, string role)
    {
        var apiKey = _configuration["AI:Groq:ApiKey"];
        var model = _configuration["AI:Groq:Model"] ?? "llama-3.3-70b-versatile";
        
        if (string.IsNullOrEmpty(apiKey)) return (50, "Groq API Key missing.");

        _logger.LogInformation("Calling Groq for {Role}...", role);
        
        try
        {
            var request = new HttpRequestMessage(HttpMethod.Post, "https://api.groq.com/openai/v1/chat/completions");
            request.Headers.Add("Authorization", $"Bearer {apiKey}");
            
            var body = new
            {
                model = model,
                messages = new[]
                {
                    new { role = "system", content = "You are a crypto trading AI. Output ONLY a valid JSON object with 'score' (number 0-100) and 'reasoning' (string). No markdown, no preambles." },
                    new { role = "user", content = prompt }
                },
                response_format = new { type = "json_object" }
            };
            
            request.Content = JsonContent.Create(body);
            
            var response = await _httpClient.SendAsync(request);
            if (response.IsSuccessStatusCode)
            {
                var jsonString = await response.Content.ReadAsStringAsync();
                var result = JsonDocument.Parse(jsonString);
                var contentString = result.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString();
                
                if (!string.IsNullOrEmpty(contentString))
                {
                    var parsed = JsonSerializer.Deserialize<AgentResponseDto>(contentString, new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                    if (parsed != null)
                    {
                         return (parsed.Score, $"[{role}] {parsed.Reasoning}");
                    }
                }
            }
            else if (response.StatusCode == HttpStatusCode.TooManyRequests)
            {
                return (50, $"[{role}] ERROR 429: Rate limit hit.");
            }
            else
            {
                var error = await response.Content.ReadAsStringAsync();
                _logger.LogWarning("Groq API Error: {StatusCode} - {Error}", response.StatusCode, error);
            }
        }
        catch (Exception ex)
        {
             _logger.LogError(ex, "Exception calling Groq for {Role}", role);
        }

        return (50, $"[{role}] Analysis failed due to API error.");
    }

    private async Task<(float Score, string Reasoning)> CallGeminiAsync(string prompt, string role)
    {
        var apiKey = _configuration["AI:Gemini:ApiKey"];
        var model = _configuration["AI:Gemini:Model"] ?? "gemini-2.0-flash";
        
        if (string.IsNullOrEmpty(apiKey)) return (50, "Gemini API Key missing.");

        _logger.LogInformation("Calling Gemini for {Role}...", role);
        
        try
        {
            var url = $"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={apiKey}";
            var request = new HttpRequestMessage(HttpMethod.Post, url);
            
            var body = new
            {
                contents = new[]
                {
                    new
                    {
                        parts = new[] { new { text = prompt } }
                    }
                },
                systemInstruction = new 
                {
                    parts = new[] { new { text = "You are a crypto trading AI. Output ONLY a valid JSON object with 'score' (number 0-100) and 'reasoning' (string). No markdown, no preambles." } }
                },
                generationConfig = new
                {
                    responseMimeType = "application/json"
                }
            };
            
            request.Content = JsonContent.Create(body);
            
            var response = await _httpClient.SendAsync(request);
            if (response.IsSuccessStatusCode)
            {
                var jsonString = await response.Content.ReadAsStringAsync();
                var result = JsonDocument.Parse(jsonString);
                var candidates = result.RootElement.GetProperty("candidates");
                
                if (candidates.GetArrayLength() > 0)
                {
                    var contentString = candidates[0].GetProperty("content").GetProperty("parts")[0].GetProperty("text").GetString();
                    if (!string.IsNullOrEmpty(contentString))
                    {
                        var parsed = JsonSerializer.Deserialize<AgentResponseDto>(contentString, new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                        if (parsed != null)
                        {
                             return (parsed.Score, $"[{role}] {parsed.Reasoning}");
                        }
                    }
                }
            }
            else if (response.StatusCode == HttpStatusCode.TooManyRequests)
            {
                return (50, $"[{role}] ERROR 429: Rate limit hit.");
            }
            else
            {
                var error = await response.Content.ReadAsStringAsync();
                _logger.LogWarning("Gemini API Error: {StatusCode} - {Error}", response.StatusCode, error);
            }
        }
        catch (Exception ex)
        {
             _logger.LogError(ex, "Exception calling Gemini for {Role}", role);
        }
        
        return (50, $"[{role}] Analysis failed due to API error.");
    }
    
    private class AgentResponseDto
    {
        public float Score { get; set; }
        public string Reasoning { get; set; } = string.Empty;
    }
}
