using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Volo.Abp.DependencyInjection;

namespace Verge.Agent;

public class MarketHealthService : ISingletonDependency
{
    private readonly HttpClient _client;
    private readonly ILogger<MarketHealthService> _logger;
    private readonly string[] _baseUrls;
    
    private string _activeUrl = "http://localhost:8001";
    private object? _lastSnapshot;
    private DateTime _lastUpdateUtc = DateTime.MinValue;
    private DateTime? _firstDetectedUtc = null;
    private bool _isInitialized = false;

    public MarketHealthService(IConfiguration configuration, ILogger<MarketHealthService> logger)
    {
        _logger = logger;
        _client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        
        var urls = configuration.GetSection("MarketWs:BaseUrls").Get<string[]>();
        _baseUrls = urls ?? new[] { "http://localhost:8001", "http://127.0.0.1:8001", "http://host.docker.internal:8001" };
        
        // Start background monitoring (first probe runs immediately inside the loop)
        _ = MonitorAsync();
    }

    private int _failureCount = 0;
    private const int MaxFailures = 5;

    public (object? health, bool isHealthy, string? startTime) GetCurrentHealth()
    {
        // Use ISO 8601 with Z suffix to ensure JS parses it as UTC
        return (_lastSnapshot, _lastSnapshot != null, _firstDetectedUtc?.ToString("yyyy-MM-ddTHH:mm:ssZ"));
    }

    /// <summary>
    /// Forces an immediate probe if the cache is empty.
    /// Used by GetSystemStateAsync on the first call after startup.
    /// </summary>
    public async Task EnsureProbeAsync()
    {
        if (_lastSnapshot == null)
        {
            await ProbeAsync();
        }
    }

    public string GetActiveUrl() => _activeUrl;

    private async Task MonitorAsync()
    {
        // Run first probe immediately so state is ready ASAP
        try { await ProbeAsync(); } catch { }

        while (true)
        {
            await Task.Delay(TimeSpan.FromSeconds(5));
            try
            {
                await ProbeAsync();
                _isInitialized = true;
            }
            catch (Exception ex)
            {
                _logger.LogWarning("Health probe loop error: {Message}", ex.Message);
            }
        }
    }

    private async Task ProbeAsync()
    {
        bool currentProbeSuccess = false;
        
        // Try active one first
        if (await CheckUrlAsync(_activeUrl)) 
        {
            currentProbeSuccess = true;
        }
        else 
        {
            // Try others
            foreach (var url in _baseUrls)
            {
                if (url == _activeUrl) continue;
                if (await CheckUrlAsync(url))
                {
                    _activeUrl = url;
                    currentProbeSuccess = true;
                    break;
                }
            }
        }

        if (currentProbeSuccess)
        {
            _failureCount = 0;
            _firstDetectedUtc ??= DateTime.UtcNow;
        }
        else
        {
            _failureCount++;
            if (_failureCount >= MaxFailures)
            {
                _firstDetectedUtc = null;
                _lastSnapshot = null;
            }
        }
    }

    private async Task<bool> CheckUrlAsync(string url)
    {
        try
        {
            // Increased timeout to 5s for Windows Docker stability
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var response = await _client.GetAsync($"{url.TrimEnd('/')}/health", cts.Token);
            if (response.IsSuccessStatusCode)
            {
                var content = await response.Content.ReadAsStringAsync(cts.Token);
                _lastSnapshot = JsonSerializer.Deserialize<JsonElement>(content);
                _lastUpdateUtc = DateTime.UtcNow;
                return true;
            }
        }
        catch { }
        return false;
    }
}
