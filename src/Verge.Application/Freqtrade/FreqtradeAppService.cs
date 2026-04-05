using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.SignalR;
using Verge.Freqtrade.Hubs;
using Volo.Abp;

namespace Verge.Freqtrade
{
    [Authorize]
    public class FreqtradeAppService : VergeAppService, IFreqtradeAppService
    {
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IHubContext<BotHub> _botHubContext;
        private string _jwtToken; 

        public FreqtradeAppService(
            IHttpClientFactory httpClientFactory,
            IHubContext<BotHub> botHubContext)
        {
            _httpClientFactory = httpClientFactory;
            _botHubContext = botHubContext;
        }

        private async Task EnsureLoginAsync()
        {
            if (!string.IsNullOrEmpty(_jwtToken)) return;

            var handler = new HttpClientHandler { UseProxy = false, Proxy = null };
            using var loginClient = new HttpClient(handler);
            loginClient.BaseAddress = new Uri("http://127.0.0.1:8080");
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
                    Console.WriteLine("[Freqtrade] ✅ Login exitoso");
                }
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
                Console.WriteLine($"[Freqtrade] ⚠️ Freqtrade no disponible: {ex.Message}");
                _jwtToken = null; // Reset para próximo intento
                return null;
            }
        }

        public async Task StartBotAsync(FreqtradeCreateBotDto input)
        {
            var client = await GetClientAsync();
            if (client == null)
                throw new UserFriendlyException("Freqtrade está offline. Revisa que el contenedor Docker esté corriendo.");
            // 1. Localizar y cargar config.json
            // Nota: En un entorno real esto debería estar en un setting o inyectado
            var configPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "Verge.HttpApi.Host", "freqtrade", "user_data", "config.json");
            
            // Si el path anterior falla (dependiendo de dónde se ejecute el host), intentamos el path absoluto detectado
            if (!File.Exists(configPath))
            {
                configPath = @"C:\Users\Nicolas\Desktop\Verge\Verge\freqtrade\user_data\config.json";
            }

            if (File.Exists(configPath))
            {
                var flagPath = Path.Combine(Path.GetDirectoryName(configPath) ?? string.Empty, "bot_deleted.flag");
                if (File.Exists(flagPath)) File.Delete(flagPath);

                var json = await File.ReadAllTextAsync(configPath);
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement.Clone();
                
                // Usamos un Dictionary para manipular el JSON de forma sencilla para este nivel de integración
                var configDict = JsonSerializer.Deserialize<Dictionary<string, object>>(json);

                if (configDict != null)
                {
                    // Actualizar parámetros principales
                    configDict["stake_amount"] = input.StakeAmount;
                    configDict["timeframe"] = input.Timeframe;
                    configDict["take_profit"] = Math.Round((double)input.TpPercent / 100.0, 4);
                    configDict["stoploss"] = -Math.Round((double)input.SlPercent / 100.0, 4);
                    configDict["strategy"] = input.Strategy;
                    configDict["force_entry_enable"] = true;

                    // Deshabilitar FreqAI si elegimos estrategia simple, o activarlo
                    if (input.Strategy == "VergeFreqAIStrategy")
                    {
                        if (configDict.ContainsKey("freqai"))
                        {
                            var freqaiJson = JsonSerializer.Serialize(configDict["freqai"]);
                            var freqaiDict = JsonSerializer.Deserialize<Dictionary<string, object>>(freqaiJson);
                            if (freqaiDict != null)
                            {
                                freqaiDict["enabled"] = true;
                                if (freqaiDict.TryGetValue("feature_parameters", out var fpObj))
                                {
                                    var fpJson = JsonSerializer.Serialize(fpObj);
                                    var fpDict = JsonSerializer.Deserialize<Dictionary<string, object>>(fpJson);
                                    if (fpDict != null)
                                    {
                                        fpDict["include_timeframes"] = new List<string> { input.Timeframe, "1h", "4h" };
                                        freqaiDict["feature_parameters"] = fpDict;
                                    }
                                }
                                configDict["freqai"] = freqaiDict;
                            }
                        }
                    }
                    else
                    {
                        // Deshabilitar freqAI para la estrategia simple
                        if (configDict.ContainsKey("freqai"))
                        {
                            var freqaiJson = JsonSerializer.Serialize(configDict["freqai"]);
                            var freqaiDict = JsonSerializer.Deserialize<Dictionary<string, object>>(freqaiJson);
                            if (freqaiDict != null)
                            {
                                freqaiDict["enabled"] = false;
                                configDict["freqai"] = freqaiDict;
                            }
                        }
                    }

                    // Actualizar Whitelist (Exchange -> pair_whitelist)
                    if (configDict.ContainsKey("exchange"))
                    {
                        var exchangeJson = JsonSerializer.Serialize(configDict["exchange"]);
                        var exchangeDict = JsonSerializer.Deserialize<Dictionary<string, object>>(exchangeJson);
                        if (exchangeDict != null)
                        {
                            // Normalizar par: BTCUSDT -> BTC/USDT:USDT
                            var pair = input.Pair;
                            if (!pair.Contains("/")) 
                            {
                                // Lógica simple de normalización para Binance
                                if (pair.EndsWith("USDT")) pair = pair.Replace("USDT", "/USDT:USDT");
                            }
                            
                            Console.WriteLine($"[Freqtrade] 🔄 Normalizando par: {input.Pair} -> {pair}");
                            
                            var currentPairs = new List<string>();
                            if (exchangeDict.TryGetValue("pair_whitelist", out var currentObj))
                            {
                                try {
                                    var arr = JsonSerializer.Deserialize<List<string>>(JsonSerializer.Serialize(currentObj));
                                    if (arr != null) currentPairs = arr;
                                } catch { /* Ignore parse error */ }
                            }
                            
                            if (!currentPairs.Contains(pair)) {
                                currentPairs.Add(pair);
                            }
                            
                            exchangeDict["pair_whitelist"] = currentPairs;
                            configDict["exchange"] = exchangeDict;
                        }
                    }

                    var updatedJson = JsonSerializer.Serialize(configDict, new JsonSerializerOptions { WriteIndented = true });
                    await File.WriteAllTextAsync(configPath, updatedJson);
                    Console.WriteLine($"[Freqtrade] ✅ Configuración actualizada en {configPath}");
                }
            }
            else
            {
                Console.WriteLine($"[Freqtrade] ⚠️ ADVERTENCIA: No se encontró config.json en {configPath}. Se intentará comando directo.");
            }

            // 2. Recargar configuración en el motor Freqtrade
            try 
            {
                Console.WriteLine($"[Freqtrade] Recargando configuración para {input.Pair}...");
                var reloadResponse = await client.PostAsync("/api/v1/reload_config", new StringContent("{}", Encoding.UTF8, "application/json"));
                
                if (!reloadResponse.IsSuccessStatusCode)
                {
                    var error = await reloadResponse.Content.ReadAsStringAsync();
                    Console.WriteLine($"[Freqtrade] ERROR al recargar config: {error}");
                }

                // PEQUEÑA PAUSA: Freqtrade necesita tiempo para procesar el nuevo JSON
                await Task.Delay(2500);

                // 3. Iniciar el bot (si estaba detenido)
                Console.WriteLine($"[Freqtrade] Enviando comando START...");
                var startResponse = await client.PostAsync("/api/v1/start", new StringContent("{}", Encoding.UTF8, "application/json"));
                
                if (startResponse.IsSuccessStatusCode)
                {
                    Console.WriteLine("[Freqtrade] Motor INICIADO con éxito.");
                    // 4. Notificar vía SignalR para refresco instantáneo del dashboard
                    await _botHubContext.Clients.All.SendAsync("BotStatusChanged", "running");
                }
                else
                {
                    var error = await startResponse.Content.ReadAsStringAsync();
                    Console.WriteLine($"[Freqtrade] ERROR al iniciar motor: {error}");
                    throw new UserFriendlyException($"El bot se configuró pero Freqtrade rechazó el comando START: {error}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Freqtrade] ⚠️ Excepción de conexión: {ex.Message}");
                // No lanzamos (throw) para evitar crash de UI, solo notificamos
                throw new UserFriendlyException("Se guardó la configuración pero Freqtrade se está reiniciando (Offline). Espera 10 segundos y refresca.");
            }
        }

        public async Task StopBotAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return;
            var response = await client.PostAsync("/api/v1/stop", new StringContent("{}", Encoding.UTF8, "application/json"));
            if (response.IsSuccessStatusCode)
                await _botHubContext.Clients.All.SendAsync("BotStatusChanged", "stopped");
        }

        public async Task<FreqtradeStatusDto> GetStatusAsync()
        {
            var client = await GetClientAsync();
            if (client == null)
                return new FreqtradeStatusDto { IsRunning = false, ActivePairs = new List<string>(), OpenTradesCount = 0, RuntimeSeconds = 0 };
            
            bool isRunning = false;
            var activePairs = new List<string>();
            try
            {
                var configResponse = await client.GetAsync("/api/v1/show_config");
                if (configResponse.IsSuccessStatusCode)
                {
                    var configContent = await configResponse.Content.ReadAsStringAsync();
                    var configResult = JsonSerializer.Deserialize<JsonElement>(configContent);
                    var statusStr = configResult.TryGetProperty("state", out var state) ? state.GetString() : "unknown";
                    isRunning = statusStr == "running";
                }

                // Extraer current pairs desde el archivo config.json directamente
                var configPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "Verge.HttpApi.Host", "freqtrade", "user_data", "config.json");
                if (!File.Exists(configPath)) configPath = @"C:\Users\Nicolas\Desktop\Verge\Verge\freqtrade\user_data\config.json";
                
                var flagPath = Path.Combine(Path.GetDirectoryName(configPath) ?? string.Empty, "bot_deleted.flag");

                if (!File.Exists(flagPath) && File.Exists(configPath))
                {
                    var json = await File.ReadAllTextAsync(configPath);
                    using var doc = JsonDocument.Parse(json);
                    if (doc.RootElement.TryGetProperty("exchange", out var exchangeObj) && 
                        exchangeObj.TryGetProperty("pair_whitelist", out var whitelist) &&
                        whitelist.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var p in whitelist.EnumerateArray())
                        {
                            var s = p.GetString();
                            if (!string.IsNullOrEmpty(s)) activePairs.Add(s);
                        }
                    }
                }
            }
            catch { /* Freqtrade offline */ }

            int openTradesCount = 0;
            try
            {
                var statusResponse = await client.GetAsync("/api/v1/status");
                if (statusResponse.IsSuccessStatusCode)
                {
                    var statusContent = await statusResponse.Content.ReadAsStringAsync();
                    var statusResult = JsonSerializer.Deserialize<JsonElement>(statusContent);
                    if (statusResult.ValueKind == JsonValueKind.Array)
                        openTradesCount = statusResult.GetArrayLength();
                }
            }
            catch { /* Freqtrade offline */ }

            return new FreqtradeStatusDto
            {
                IsRunning = isRunning,
                ActivePairs = activePairs,
                OpenTradesCount = openTradesCount,
                RuntimeSeconds = 0
            };
        }

        public async Task<List<FreqtradeTradeDto>> GetOpenTradesAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return new List<FreqtradeTradeDto>();
            try
            {
                var response = await client.GetAsync("/api/v1/trades");
                if (!response.IsSuccessStatusCode) return new List<FreqtradeTradeDto>();
                var content = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(content);
                var trades = new List<FreqtradeTradeDto>();
                if (doc.RootElement.TryGetProperty("trades", out var tradesArray))
                {
                    foreach (var trade in tradesArray.EnumerateArray())
                    {
                        if (trade.TryGetProperty("is_open", out var isOpen) && isOpen.GetBoolean())
                        {
                            trades.Add(new FreqtradeTradeDto
                            {
                                Id = trade.GetProperty("trade_id").GetInt32(),
                                Pair = trade.GetProperty("pair").GetString(),
                                Amount = trade.TryGetProperty("amount", out var amt) ? amt.GetDecimal() : 0,
                                OpenRate = trade.TryGetProperty("open_rate", out var or) ? or.GetDecimal() : 0,
                                CurrentRate = trade.TryGetProperty("current_rate", out var cr) ? cr.GetDecimal() : 0,
                                Pnl = trade.TryGetProperty("profit_abs", out var pnl) ? pnl.GetDecimal() : 0,
                                OpenDate = trade.TryGetProperty("open_date", out var od) && DateTime.TryParse(od.GetString(), out var date) ? date : DateTime.UtcNow
                            });
                        }
                    }
                }
                return trades;
            }
            catch { return new List<FreqtradeTradeDto>(); }
        }

        public async Task<FreqtradeProfitDto> GetProfitAsync()
        {
            var client = await GetClientAsync();
            if (client == null) return new FreqtradeProfitDto();
            try
            {
                var response = await client.GetAsync("/api/v1/profit");
                if (!response.IsSuccessStatusCode) return new FreqtradeProfitDto();
                var content = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(content);
                return new FreqtradeProfitDto
                {
                    TotalProfit = doc.RootElement.TryGetProperty("profit_all_coin", out var p) ? p.GetDecimal() : 0,
                    WinRate = doc.RootElement.TryGetProperty("win_rate", out var w) ? w.GetDecimal() : 0,
                    TotalTrades = doc.RootElement.TryGetProperty("trade_count", out var t) ? t.GetInt32() : 0
                };
            }
            catch { return new FreqtradeProfitDto(); }
        }

        public async Task CloseTradeAsync(string tradeId)
        {
            var client = await GetClientAsync();
            if (client == null) throw new UserFriendlyException("Freqtrade está offline.");
            var response = await client.DeleteAsync($"/api/v1/trades/{tradeId}");
            if (!response.IsSuccessStatusCode)
                throw new UserFriendlyException($"Error al cerrar el trade {tradeId}");
        }

        public async Task UpdateWhitelistAsync(string pair)
        {
            var client = await GetClientAsync();
            // Implementación futura según la Freqtrade API.
            // Generalmente requiere actualizar config.json y recargar o /api/v1/sysinfo, etc.
            await Task.CompletedTask;
        }

        public async Task ForceEnterAsync(string pair, string side, decimal stakeAmount, int leverage)
        {
            var client = await GetClientAsync();
            if (client == null) throw new UserFriendlyException("Freqtrade está offline.");

            // Enviar comando FORCEENTER para el par solicitado
            // Freqtrade API espera { "pair": "ETH/USDT:USDT", "side": "long/short", "stakeamount": 100, "leverage": 10 }
            
            // Si el par no tiene formato Freqtrade, intentamos normalizarlo
            if (!pair.Contains("/"))
            {
                if (pair.EndsWith("USDT")) pair = pair.Replace("USDT", "/USDT:USDT");
            }
            
            var payload = new Dictionary<string, object> 
            { 
                { "pair", pair }, 
                { "side", side.ToLower() },
                { "leverage", leverage },
                { "stakeamount", stakeAmount }
            };
            
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await client.PostAsync("/api/v1/forceenter", content);
            
            if (!response.IsSuccessStatusCode) 
            {
                var error = await response.Content.ReadAsStringAsync();
                Console.WriteLine($"[Freqtrade ForceEnter] ERROR: {error}");
                throw new UserFriendlyException($"Error de Binance al forzar {side} en {pair}: {error}");
            }
        }

        public async Task ResumeBotAsync()
        {
            var client = await GetClientAsync();
            if (client == null) throw new UserFriendlyException("Freqtrade está offline.");
            
            var response = await client.PostAsync("/api/v1/start", new StringContent("{}", Encoding.UTF8, "application/json"));
            if (response.IsSuccessStatusCode)
                await _botHubContext.Clients.All.SendAsync("BotStatusChanged", "running");
            else 
            {
                var err = await response.Content.ReadAsStringAsync();
                throw new UserFriendlyException($"Error al reanudar el motor de Freqtrade: {err}");
            }
        }

        public async Task DeleteBotAsync(string pair)
        {
            var configPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "Verge.HttpApi.Host", "freqtrade", "user_data", "config.json");
            if (!File.Exists(configPath)) configPath = @"C:\Users\Nicolas\Desktop\Verge\Verge\freqtrade\user_data\config.json";
            
            var dbPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "Verge.HttpApi.Host", "freqtrade", "user_data", "tradesv3.sqlite");
            if (!File.Exists(dbPath)) dbPath = @"C:\Users\Nicolas\Desktop\Verge\Verge\freqtrade\user_data\tradesv3.sqlite";

            var flagPath = Path.Combine(Path.GetDirectoryName(configPath) ?? string.Empty, "bot_deleted.flag");

            var client = await GetClientAsync();
            if (client != null) 
            {
                int remainingPairs = 0;
                
                // 1. Remover el par específico del Config
                if (File.Exists(configPath))
                {
                    var json = await File.ReadAllTextAsync(configPath);
                    var configDict = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                    if (configDict != null && configDict.ContainsKey("exchange"))
                    {
                        var exchangeJson = JsonSerializer.Serialize(configDict["exchange"]);
                        var exchangeDict = JsonSerializer.Deserialize<Dictionary<string, object>>(exchangeJson);
                        if (exchangeDict != null)
                        {
                            var currentPairs = new List<string>();
                            if (exchangeDict.TryGetValue("pair_whitelist", out var currentObj))
                            {
                                try {
                                    var arr = JsonSerializer.Deserialize<List<string>>(JsonSerializer.Serialize(currentObj));
                                    if (arr != null) currentPairs = arr;
                                } catch { /* Ignore parse error */ }
                            }
                            
                            if (currentPairs.Contains(pair)) {
                                currentPairs.Remove(pair);
                            }
                            remainingPairs = currentPairs.Count;
                            
                            exchangeDict["pair_whitelist"] = currentPairs;
                            configDict["exchange"] = exchangeDict;
                            var updatedJson = JsonSerializer.Serialize(configDict, new JsonSerializerOptions { WriteIndented = true });
                            await File.WriteAllTextAsync(configPath, updatedJson);
                        }
                    }
                }

                if (remainingPairs == 0)
                {
                    // No quedan pares: hard stop y limpieza total.
                    Console.WriteLine("[Freqtrade] STOPPING Bot for Hard Deletion (No pairs left)...");
                    await client.PostAsync("/api/v1/stop", new StringContent("{}", Encoding.UTF8, "application/json"));
                    await Task.Delay(1500);

                    await File.WriteAllTextAsync(flagPath, "true");
                    Console.WriteLine("[Freqtrade] bot_deleted.flag creado.");

                    try {
                        if (File.Exists(dbPath)) {
                            File.Delete(dbPath);
                            Console.WriteLine("[Freqtrade] tradesv3.sqlite eliminado (Historial purgado).");
                        }
                    } catch(Exception e) {
                        Console.WriteLine("[Freqtrade] Warning: No se pudo purgar tradesv3.sqlite: " + e.Message);
                    }
                }
                else
                {
                    // Aún hay bots corriendo, solo recargamos
                    Console.WriteLine($"[Freqtrade] Bot removido. Recargando Freqtrade con los restantes {remainingPairs} pares...");
                    await client.PostAsync("/api/v1/reload_config", new StringContent("{}", Encoding.UTF8, "application/json"));
                    await Task.Delay(1000);
                }

                await _botHubContext.Clients.All.SendAsync("BotStatusChanged", "deleted");
            }
        }
    }
}
