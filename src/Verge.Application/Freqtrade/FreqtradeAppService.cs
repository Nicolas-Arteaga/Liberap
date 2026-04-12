using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Verge.Freqtrade.Hubs;
using Volo.Abp;
using Volo.Abp.Domain.Repositories;
using Verge.Trading;

namespace Verge.Freqtrade
{
    [Authorize]
    public class FreqtradeAppService : VergeAppService, IFreqtradeAppService
    {
        // - [x] `FreqtradeAppService`: Use `JsonNode` for surgical `config.json` updates.
        // - [x] `MarketScannerService`: Restore full AI pipeline in parallel tasks.
        // - [x] `SignalR`: Sync SessionId/UserId for instant UI updates.
        // - [x] `Verification`: Confirm SOL/SIREN co-existence and high-quality scores.
        private static string _jwtToken; // 👈 Persistencia Singleton
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IHubContext<BotHub> _botHubContext;
        private readonly IConfiguration _configuration;
        private readonly ILogger<FreqtradeAppService> _logger;
        private readonly IRepository<TradingBot, Guid> _botRepository;

        public FreqtradeAppService(
            IHttpClientFactory httpClientFactory,
            IHubContext<BotHub> botHubContext,
            IConfiguration configuration,
            ILogger<FreqtradeAppService> logger,
            IRepository<TradingBot, Guid> botRepository)
        {
            _httpClientFactory = httpClientFactory;
            _botHubContext = botHubContext;
            _configuration = configuration;
            _logger = logger;
            _botRepository = botRepository;
        }

        private async Task EnsureLoginAsync()
        {
            if (!string.IsNullOrEmpty(_jwtToken)) return;

            try 
            {
                var baseUrl = _configuration["RemoteServices:Freqtrade:BaseUrl"] ?? "http://127.0.0.1:8080";
                var handler = new HttpClientHandler { UseProxy = false, Proxy = null };
                using var loginClient = new HttpClient(handler);
                loginClient.BaseAddress = new Uri(baseUrl);
                loginClient.Timeout = TimeSpan.FromSeconds(5);

                var authBytes = Encoding.UTF8.GetBytes("verge_admin:verge_secure_password");
                var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/token/login")
                {
                    Version = new Version(1, 1),
                    Content = new StringContent("{}", Encoding.UTF8, "application/json")
                };
                request.Headers.Authorization = new AuthenticationHeaderValue("Basic", Convert.ToBase64String(authBytes));

                var response = await loginClient.SendAsync(request);
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync();
                    var result = JsonSerializer.Deserialize<JsonElement>(content);
                    if (result.TryGetProperty("access_token", out var token))
                    {
                        _jwtToken = token.GetString();
                        _logger.LogInformation("[Freqtrade] ✅ Login exitoso. JWT obtenido.");
                    }
                }
                else 
                {
                    _logger.LogWarning("[Freqtrade] ❌ Fallo de login: {StatusCode}", response.StatusCode);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[Freqtrade] ❌ Excepción durante EnsureLoginAsync");
            }
        }

        private async Task<HttpClient?> GetClientAsync()
        {
            try
            {
                await EnsureLoginAsync();
                if (string.IsNullOrEmpty(_jwtToken)) return null;

                var client = _httpClientFactory.CreateClient("Freqtrade");
                client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _jwtToken);
                client.Timeout = TimeSpan.FromSeconds(5);
                return client;
            }
            catch (Exception ex)
            {
                _logger.LogWarning("[Freqtrade] ⚠️ GetClientAsync failed: {Msg}", ex.Message);
                _jwtToken = null; 
                return null;
            }
        }

        public async Task<List<FreqtradeTradeDto>> GetOpenTradesAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return new List<FreqtradeTradeDto>();

            try
            {
                // /api/v1/status returns the currently active trades
                var response = await client.GetAsync("/api/v1/status");
                if (!response.IsSuccessStatusCode) return new List<FreqtradeTradeDto>();

                var content = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(content);
                var list = new List<FreqtradeTradeDto>();

                // Freqtrade /status returns a JSON array directly or in a "trades" property
                var root = doc.RootElement;
                JsonElement tradesArray;
                
                if (root.ValueKind == JsonValueKind.Array) {
                    tradesArray = root;
                } else if (root.TryGetProperty("trades", out var tArr)) {
                    tradesArray = tArr;
                } else {
                    return list;
                }

                foreach (var element in tradesArray.EnumerateArray())
                {
                    var rawPair = element.TryGetProperty("pair", out var pProp) ? pProp.GetString() ?? "" : "";
                    var normalizedPair = rawPair.Replace("/", "").Split(':')[0];

                    list.Add(new FreqtradeTradeDto
                    {
                        Id = element.TryGetProperty("trade_id", out var idProp) ? idProp.GetInt32() : 0,
                        Pair = normalizedPair,
                        Amount = element.TryGetProperty("amount", out var amtProp) ? amtProp.GetDecimal() : 0,
                        OpenRate = element.TryGetProperty("open_rate", out var orProp) ? orProp.GetDecimal() : 0,
                        CurrentRate = element.TryGetProperty("current_rate", out var crProp) ? crProp.GetDecimal() : 
                                      (element.TryGetProperty("close_rate", out var clrProp) ? clrProp.GetDecimal() : 0),
                        ProfitPercentage = element.TryGetProperty("profit_pct", out var ppProp) ? ppProp.GetDecimal() : 
                                          (element.TryGetProperty("profit_ratio", out var prProp) ? prProp.GetDecimal() * 100 : 0),
                        ProfitAbs = element.TryGetProperty("profit_abs", out var paProp) ? paProp.GetDecimal() : 0,
                        Pnl = element.TryGetProperty("profit_abs", out var pnlProp) ? pnlProp.GetDecimal() : 0,
                        OpenDate = element.TryGetProperty("open_date", out var odProp) && odProp.GetString() != null 
                                  ? (DateTime.TryParse(odProp.GetString(), out var date) ? date : DateTime.UtcNow) 
                                  : DateTime.UtcNow,
                        IsShort = element.TryGetProperty("is_short", out var shortProp) && shortProp.GetBoolean()
                    });
                }
                
                _logger.LogDebug("[Freqtrade] Status Sync: {Count} trades abiertos encontrados.", list.Count);
                return list;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[Freqtrade] Error en GetOpenTradesAsync");
                return new List<FreqtradeTradeDto>();
            }
        }

        public async Task<List<FreqtradeTradeDto>> GetTradeHistoryAsync(string? pair = null)
        {
            var client = await GetClientAsync();
            if (client == null) return new List<FreqtradeTradeDto>();

            try
            {
                // /api/v1/trades?limit=500
                var url = "/api/v1/trades?limit=500";
                var response = await client.GetAsync(url);
                if (!response.IsSuccessStatusCode) return new List<FreqtradeTradeDto>();

                var content = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(content);
                var list = new List<FreqtradeTradeDto>();

                if (doc.RootElement.TryGetProperty("trades", out var tradesArray))
                {
                    foreach (var element in tradesArray.EnumerateArray())
                    {
                        var rawPair = element.TryGetProperty("pair", out var pProp) ? pProp.GetString() ?? "" : "";
                        var normalizedPair = rawPair.Replace("/", "").Split(':')[0];

                        // Filter by pair if requested
                        if (!string.IsNullOrEmpty(pair)) {
                            var cleanInputPair = pair.Replace("/", "").Split(':')[0];
                            if (!normalizedPair.Equals(cleanInputPair, StringComparison.OrdinalIgnoreCase)) continue;
                        }

                        list.Add(new FreqtradeTradeDto
                        {
                            Id = element.TryGetProperty("trade_id", out var idProp) ? idProp.GetInt32() : 0,
                            Pair = normalizedPair,
                            Amount = element.TryGetProperty("amount", out var amtProp) ? amtProp.GetDecimal() : 0,
                            OpenRate = element.TryGetProperty("open_rate", out var orProp) ? orProp.GetDecimal() : 0,
                            CurrentRate = element.TryGetProperty("close_rate", out var crProp) ? crProp.GetDecimal() : 0,
                            ProfitPercentage = element.TryGetProperty("profit_pct", out var ppProp) ? ppProp.GetDecimal() : 0,
                            ProfitAbs = element.TryGetProperty("profit_abs", out var paProp) ? paProp.GetDecimal() : 0,
                            OpenDate = element.TryGetProperty("open_date", out var odProp) && odProp.GetString() != null 
                                      ? (DateTime.TryParse(odProp.GetString(), out var date) ? date : DateTime.UtcNow) 
                                      : DateTime.UtcNow,
                            CloseDate = element.TryGetProperty("close_date", out var cdProp) && cdProp.GetString() != null 
                                       ? (DateTime.TryParse(cdProp.GetString(), out var cDate) ? cDate : (DateTime?)null) 
                                       : null,
                            IsShort = element.TryGetProperty("is_short", out var shortProp) && shortProp.GetBoolean()
                        });
                    }
                }
                return list;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[Freqtrade] Error en GetTradeHistoryAsync");
                return new List<FreqtradeTradeDto>();
            }
        }

        public async Task<FreqtradeStatusDto> GetStatusAsync()
        {
            var client = await GetClientAsync();
            if (client == null)
                return new FreqtradeStatusDto { IsRunning = false, ActivePairs = new List<string>() };
            
            try
            {
                // Aumentamos el timeout para esta llamada específica ya que el bot puede estar ocupado (entrenando)
                var response = await client.GetAsync("/api/v1/show_config");
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync();
                    using var doc = JsonDocument.Parse(content);
                    var root = doc.RootElement;

                    var result = root.TryGetProperty("config", out var configObj) ? configObj : root;
                    var stateValue = result.TryGetProperty("state", out var stateProp) ? stateProp.GetString()?.ToLower() : "stopped";
                    
                    if (stateValue == "stopped")
                    {
                        var pingResp = await client.GetAsync("/api/v1/ping");
                        if (pingResp.IsSuccessStatusCode) {
                             stateValue = "running";
                        }
                    }

                    var pairs = new List<string>();
                    void ExtractFromElement(JsonElement el)
                    {
                        if (el.TryGetProperty("pair_whitelist", out var wl) && wl.ValueKind == JsonValueKind.Array)
                        {
                            foreach (var p in wl.EnumerateArray()) {
                                var s = p.GetString();
                                if (!string.IsNullOrEmpty(s)) pairs.Add(s);
                            }
                        }
                    }

                    ExtractFromElement(result);
                    if (result.TryGetProperty("exchange", out var exch) && exch.ValueKind == JsonValueKind.Object)
                        ExtractFromElement(exch);
                    
                    if (pairs.Count == 0)
                    {
                        try 
                        {
                            var wlResp = await client.GetAsync("/api/v1/whitelist");
                            if (wlResp.IsSuccessStatusCode)
                            {
                                var wlContent = await wlResp.Content.ReadAsStringAsync();
                                using var wlDoc = JsonDocument.Parse(wlContent);
                                if (wlDoc.RootElement.TryGetProperty("whitelist", out var wlArray))
                                {
                                    foreach (var p in wlArray.EnumerateArray()) pairs.Add(p.GetString() ?? "");
                                }
                            }
                        }
                        catch (Exception ex) { _logger.LogWarning("[Freqtrade] Whitelist fallback failed: {msg}", ex.Message); }
                    }

                    var distinctPairs = pairs.Distinct().Where(p => !string.IsNullOrEmpty(p)).ToList();
                    
                    return new FreqtradeStatusDto
                    {
                        IsRunning = stateValue == "running" || stateValue == "starting" || stateValue == "healthy",
                        ActivePairs = distinctPairs,
                        OpenTradesCount = 0 
                    };
                }
            }
            catch (Exception ex)
            { 
                _logger.LogError(ex, "[Freqtrade] Exception in GetStatusAsync");
            }
            return new FreqtradeStatusDto { IsRunning = false, ActivePairs = new List<string>() };
        }

        public async Task<FreqtradeProfitDto> GetProfitAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return new FreqtradeProfitDto();
            try
            {
                // Intentamos con /api/v1/profit que suele devolver el acumulado
                var response = await client.GetAsync("/api/v1/profit");
                if (!response.IsSuccessStatusCode) return new FreqtradeProfitDto();
                
                var content = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(content);
                var root = doc.RootElement;

                return new FreqtradeProfitDto
                {
                    TotalProfit = root.TryGetProperty("profit_all_coin", out var p) ? p.GetDecimal() : 
                                 (root.TryGetProperty("profit_closed_coin", out var pc) ? pc.GetDecimal() : 0),
                    WinRate = root.TryGetProperty("win_rate", out var w) ? w.GetDecimal() : 
                             (root.TryGetProperty("winrate", out var wr) ? wr.GetDecimal() : 0),
                    TotalTrades = root.TryGetProperty("trade_count", out var t) ? t.GetInt32() : 
                                 (root.TryGetProperty("closed_trades", out var ct) ? ct.GetInt32() : 0)
                };
            }
            catch { return new FreqtradeProfitDto(); }
        }

        public async Task StartBotAsync(FreqtradeCreateBotDto input)
        {
            var configPath = _configuration["Freqtrade:ConfigPath"] ?? @"C:\Users\Nicolas\Desktop\Verge\Verge\freqtrade\user_data\config.json";
            if (!File.Exists(configPath)) throw new UserFriendlyException("Config file not found: " + configPath);

            var json = await File.ReadAllTextAsync(configPath);
            var rootNode = JsonNode.Parse(json);
            if (rootNode == null) throw new UserFriendlyException("Invalid Config JSON");

            // Format pair
            var pair = input.Pair;
            if (string.IsNullOrEmpty(pair)) return;
            if (!pair.Contains("/")) pair = $"{pair.Replace("USDT", "")}/USDT:USDT";

            // 1. Persistencia en Base de Datos (Source of Truth)
            var existing = await _botRepository.FirstOrDefaultAsync(x => x.Symbol == input.Pair.ToUpper());
            if (existing == null)
            {
                await _botRepository.InsertAsync(new TradingBot(
                    GuidGenerator.Create(),
                    input.Pair,
                    input.Strategy ?? "VergeFreqAIStrategy",
                    input.Timeframe ?? "15m",
                    input.StakeAmount,
                    input.Leverage,
                    input.TpPercent,
                    input.SlPercent,
                    CurrentUser.Id
                ));
            }
            else 
            {
                existing.IsActive = true;
                existing.Strategy = input.Strategy ?? existing.Strategy;
                existing.Timeframe = input.Timeframe ?? existing.Timeframe;
                existing.StakeAmount = input.StakeAmount;
                existing.Leverage = input.Leverage;
                await _botRepository.UpdateAsync(existing);
            }

            // Update basic config in file
            rootNode["stake_amount"] = input.StakeAmount > 0 ? input.StakeAmount : 100;
            rootNode["timeframe"] = !string.IsNullOrEmpty(input.Timeframe) ? input.Timeframe : "15m";
            rootNode["strategy"] = !string.IsNullOrEmpty(input.Strategy) ? input.Strategy : "VergeFreqAIStrategy";

            // Update Whitelist inside Exchange surgically
            var exchange = rootNode["exchange"]?.AsObject();
            if (exchange != null)
            {
                var whitelist = exchange["pair_whitelist"]?.AsArray();
                if (whitelist == null)
                {
                    whitelist = new JsonArray();
                    exchange["pair_whitelist"] = whitelist;
                }

                // Append if not exists
                bool exists = false;
                foreach (var item in whitelist)
                {
                    if (item?.ToString().Equals(pair, StringComparison.OrdinalIgnoreCase) == true)
                    {
                        exists = true;
                        break;
                    }
                }

                if (!exists)
                {
                    whitelist.Add(pair);
                    _logger.LogInformation("✅ Pair {pair} ADDED to whitelist surgically.", pair);
                }
            }

            await File.WriteAllTextAsync(configPath, rootNode.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            _logger.LogInformation("✅ Config file updated SUCCESSFULLY with {pair}", pair);

            var client = await GetClientAsync();
            if (client != null)
            {
                var reloadResp = await client.PostAsync("/api/v1/reload_config", new StringContent("{}", Encoding.UTF8, "application/json"));
                _logger.LogInformation("🔄 Freqtrade Reload Config Sent: {Status}", reloadResp.StatusCode);
                
                await Task.Delay(2500); 
                
                var startResp = await client.PostAsync("/api/v1/start", new StringContent("{}", Encoding.UTF8, "application/json"));
                _logger.LogInformation("▶️ Freqtrade Start Sent: {Status}", startResp.StatusCode);
            }
            
            await _botHubContext.Clients.All.SendAsync("BotStatusChanged", "running");
        }

        public async Task StopBotAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return;
            await client.PostAsync("/api/v1/stop", new StringContent("{}", Encoding.UTF8, "application/json"));
            await _botHubContext.Clients.All.SendAsync("BotStatusChanged", "stopped");
        }

        public async Task ResumeBotAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return;
            await client.PostAsync("/api/v1/start", new StringContent("{}", Encoding.UTF8, "application/json"));
            await client.PostAsync("/api/v1/reload_config", new StringContent("{}", Encoding.UTF8, "application/json"));
        }

        public async Task CloseTradeAsync(string tradeId)
        {
            var client = await GetClientAsync();
            if (client == null) return;
            await client.DeleteAsync($"/api/v1/trades/{tradeId}");
        }

        public async Task ForceEnterAsync(string pair, string side, decimal stakeAmount, int leverage)
        {
            var client = await GetClientAsync();
            if (client == null) return;
            if (!pair.Contains("/")) pair = $"{pair.Replace("USDT", "")}/USDT:USDT";
            
            var payload = new { pair, side = side.ToLower(), stakeamount = stakeAmount, leverage };
            await client.PostAsync("/api/v1/forceenter", new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json"));
        }

        public async Task ForceExitAsync(string tradeId)
        {
            var client = await GetClientAsync();
            if (client == null) return;
            var payload = new { tradeid = tradeId };
            await client.PostAsync("/api/v1/forceexit", new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json"));
        }

        public async Task PauseBotAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return;
            await client.PostAsync("/api/v1/stopbuy", new StringContent("{}", Encoding.UTF8, "application/json"));
        }

        public async Task ReloadConfigAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return;
            await client.PostAsync("/api/v1/reload_config", new StringContent("{}", Encoding.UTF8, "application/json"));
        }
        public async Task DeleteBotAsync(string pair)
        {
            // 1. Actualizar DB
            var existing = await _botRepository.FirstOrDefaultAsync(x => x.Symbol == pair.ToUpper());
            if (existing != null)
            {
                await _botRepository.DeleteAsync(existing);
                _logger.LogInformation("🗑️ Bot {pair} REMOVED from Database.", pair);
            }

            var configPath = _configuration["Freqtrade:ConfigPath"] ?? @"C:\Users\Nicolas\Desktop\Verge\Verge\freqtrade\user_data\config.json";
            if (!File.Exists(configPath)) return;
            var json = await File.ReadAllTextAsync(configPath);
            var rootNode = JsonNode.Parse(json);
            if (rootNode == null) return;

            var pairToMatch = pair;
            if (!pairToMatch.Contains("/")) pairToMatch = $"{pairToMatch.Replace("USDT", "")}/USDT:USDT";

            var exchange = rootNode["exchange"]?.AsObject();
            if (exchange != null)
            {
                var whitelist = exchange["pair_whitelist"]?.AsArray();
                var blacklist = exchange["pair_blacklist"]?.AsArray();
                
                if (whitelist != null)
                {
                    for (int i = 0; i < whitelist.Count; i++)
                    {
                        if (whitelist[i]?.ToString().Equals(pairToMatch, StringComparison.OrdinalIgnoreCase) == true){ whitelist.RemoveAt(i); break; }
                    }
                }
                if (blacklist != null)
                {
                    for (int i = 0; i < blacklist.Count; i++)
                    {
                        if (blacklist[i]?.ToString().Equals(pairToMatch, StringComparison.OrdinalIgnoreCase) == true){ blacklist.RemoveAt(i); break; }
                    }
                }
                
                await File.WriteAllTextAsync(configPath, rootNode.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            }

            var client = await GetClientAsync();
            if (client != null)
            {
                await client.PostAsync("/api/v1/reload_config", new StringContent("{}", Encoding.UTF8, "application/json"));
            }
        }

        public async Task UpdateWhitelistAsync(string pair) => await Task.CompletedTask;
    }
}
