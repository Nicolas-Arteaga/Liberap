using System;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Volo.Abp.Domain.Services;

namespace Verge.Trading;

public class PythonIntegrationService : DomainService, IPythonIntegrationService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PythonIntegrationService> _logger;
    private readonly string _baseUrl;

    public PythonIntegrationService(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<PythonIntegrationService> logger)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger;
        _baseUrl = _configuration["PythonService:Url"] ?? "http://localhost:8000";
    }


    public async Task<RegimeResponseModel?> DetectMarketRegimeAsync(string symbol, string timeframe, System.Collections.Generic.List<MarketCandleModel> data)
    {
        int maxRetries = 3;
        for (int i = 0; i < maxRetries; i++)
        {
            try
            {
                var payload = new 
                { 
                    symbol, 
                    timeframe, 
                    data = data.Select(c => new {
                        timestamp = c.Timestamp.ToString(),
                        open = c.Open,
                        high = c.High,
                        low = c.Low,
                        close = c.Close,
                        volume = c.Volume
                    })
                };
                var response = await _httpClient.PostAsJsonAsync($"{_baseUrl}/detect-regime", payload);
                
                if (response.IsSuccessStatusCode)
                {
                    return await response.Content.ReadFromJsonAsync<RegimeResponseModel>();
                }

                _logger.LogWarning($"⚠️ Python service ({i+1}/{maxRetries}) returned error: {response.StatusCode}");
                if (i < maxRetries - 1) await Task.Delay(1000); 
            }
            catch (Exception ex)
            {
                _logger.LogError($"❌ Attempt {i+1}/{maxRetries} failed connecting to Python AI service: {ex.Message}");
                if (i < maxRetries - 1) await Task.Delay(1000);
            }
        }
        return null;
    }

    public async Task<TechnicalsResponseModel?> AnalyzeTechnicalsAsync(string symbol, string timeframe, System.Collections.Generic.List<MarketCandleModel> data)
    {
        int maxRetries = 3;
        for (int i = 0; i < maxRetries; i++)
        {
            try
            {
                var payload = new 
                { 
                    symbol, 
                    timeframe, 
                    data = data.Select(c => new {
                        timestamp = c.Timestamp.ToString(),
                        open = c.Open,
                        high = c.High,
                        low = c.Low,
                        close = c.Close,
                        volume = c.Volume
                    })
                };
                var response = await _httpClient.PostAsJsonAsync($"{_baseUrl}/analyze-technicals", payload);
                
                if (response.IsSuccessStatusCode)
                {
                    return await response.Content.ReadFromJsonAsync<TechnicalsResponseModel>();
                }

                _logger.LogWarning($"⚠️ Python service tech ({i+1}/{maxRetries}) returned error: {response.StatusCode}");
                if (i < maxRetries - 1) await Task.Delay(1000);
            }
            catch (Exception ex)
            {
                _logger.LogError($"❌ Attempt {i+1}/{maxRetries} technicals failed: {ex.Message}");
                if (i < maxRetries - 1) await Task.Delay(1000);
            }
        }
        return null;
    }

    public async Task<bool> IsHealthyAsync()
    {
        try
        {
            var response = await _httpClient.GetAsync($"{_baseUrl}/health");
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }
}
