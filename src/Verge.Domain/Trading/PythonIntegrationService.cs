using System;
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

    public async Task<SentimentResponseModel> AnalyzeSentimentAsync(string text)
    {
        try
        {
            var response = await _httpClient.PostAsJsonAsync($"{_baseUrl}/analyze-sentiment", new { text });
            
            if (response.IsSuccessStatusCode)
            {
                return await response.Content.ReadFromJsonAsync<SentimentResponseModel>();
            }

            _logger.LogWarning($"⚠️ Python service returned error: {response.StatusCode}");
            return null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ Error connecting to Python AI service");
            return null;
        }
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
