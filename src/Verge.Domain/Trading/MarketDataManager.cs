using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Http;
using StackExchange.Redis;
using Volo.Abp.Domain.Services;
using Verge.Trading.Integrations;
using System.Threading;

namespace Verge.Trading;

public class MarketDataManager : DomainService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly BinanceWebSocketService _webSocketService;
    private const string BinanceBaseUrl = "https://api.binance.com";
    private const string FuturesBaseUrl = "https://fapi.binance.com";

    private readonly IDatabase _redis;
    private static readonly SemaphoreSlim _binanceGate = new(10, 10);    // Max 10 parallel REST calls
    private static readonly SemaphoreSlim _tickerGate  = new(3, 3);      // Dedicated slots for ticker calls (Nexus-15 top scan)

    public MarketDataManager(IHttpClientFactory httpClientFactory, BinanceWebSocketService webSocketService, IConnectionMultiplexer redis)
    {
        _httpClientFactory = httpClientFactory;
        _webSocketService = webSocketService;
        _redis = redis.GetDatabase();
    }

    /// <summary>
    /// Returns the live price from the WebSocket in-memory cache (zero REST calls).
    /// Returns null if data is not yet available (e.g., on startup before WebSocket connects).
    /// </summary>
    public decimal? GetWebSocketPrice(string symbol) => _webSocketService.GetLastPrice(symbol);

    public async Task<MarketOpenInterestModel?> GetOpenInterestAsync(string symbol)
    {
        try
        {
            var client = _httpClientFactory.CreateClient();
            symbol = symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
            
            var url = $"{FuturesBaseUrl}/fapi/v1/openInterest?symbol={symbol}";
            var response = await client.GetAsync(url);
            
            if (!response.IsSuccessStatusCode) return null;

            var content = await response.Content.ReadAsStringAsync();
            var doc = JsonDocument.Parse(content);
            var root = doc.RootElement;

            return new MarketOpenInterestModel
            {
                Symbol = root.GetProperty("symbol").GetString() ?? symbol,
                OpenInterest = decimal.Parse(root.GetProperty("openInterest").GetString()!, System.Globalization.CultureInfo.InvariantCulture),
                Timestamp = root.GetProperty("time").GetInt64()
            };
        }
        catch (Exception ex)
        {
            Logger.LogError($"💥 Error al obtener Open Interest para {symbol}: {ex.Message}");
            return null;
        }
    }

    // Símbolos deprecados/migrados que Binance sigue listando con volumen residual
    private static readonly HashSet<string> _deprecatedSymbols = new(StringComparer.OrdinalIgnoreCase)
    {
        "MATICUSDT",  // Migrated to POLUSDT
        "LUNAUSDT",   // Collapsed, use LUNCUSDT
        "SRMUSDT",    // Delisted (FTX related)
        "RAYUSDT",    // Low liquidity
        "HNTUSDT",    // Migrated away
        "TOMOUSDT",   // Rebranded
        "BTTUSDT",    // Split/rebrand
    };

    public async Task<List<string>> GetTopSymbolsAsync(int limit = 30)
    {
        try
        {
            var client = _httpClientFactory.CreateClient();
            // Para obtener el TOP por volumen, usamos fapi/v1/ticker/24hr
            var url = $"{FuturesBaseUrl}/fapi/v1/ticker/24hr";
            var response = await client.GetAsync(url);
            
            if (!response.IsSuccessStatusCode) return new List<string> { "BTCUSDT", "ETHUSDT", "SOLUSDT" };

            var content = await response.Content.ReadAsStringAsync();
            var tickers = JsonSerializer.Deserialize<List<JsonElement>>(content);

            if (tickers == null) return new List<string> { "BTCUSDT", "ETHUSDT", "SOLUSDT" };

            // Filtrar solo USDT, excluir deprecados, y exigir volumen mínimo ($1M/24h)
            var topSymbols = tickers
                .Where(x => x.GetProperty("symbol").GetString()!.EndsWith("USDT"))
                .Select(x => new {
                    Symbol = x.GetProperty("symbol").GetString()!,
                    Volume = decimal.Parse(x.GetProperty("quoteVolume").GetString()!, System.Globalization.CultureInfo.InvariantCulture)
                })
                .Where(x => !_deprecatedSymbols.Contains(x.Symbol))
                .Where(x => x.Volume > 1_000_000m) // Mínimo $1M volumen 24h
                .OrderByDescending(x => x.Volume)
                .Take(limit)
                .Select(x => x.Symbol)
                .ToList();

            return topSymbols;
        }
        catch (Exception ex)
        {
            Logger.LogError($"💥 Error al obtener top symbols: {ex.Message}");
            return new List<string> { "BTCUSDT", "ETHUSDT", "SOLUSDT" };
        }
    }

    public async Task<List<MarketCandleModel>> GetCandlesAsync(string symbol, string interval, int limit = 100, long? endTime = null)
    {
        try
        {
            // Normalize symbol
            var cleanSymbol = symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();

            var binanceInterval = interval.ToLower() switch
            {
                "1" => "1m",
                "5" => "5m",
                "15" => "15m",
                "30" => "30m",
                "60" => "1h",
                "240" => "4h",
                _ => interval
            };

            var cacheKey = endTime.HasValue
                ? $"price:{cleanSymbol}:{binanceInterval}:{limit}:{endTime.Value}"
                : $"price:{cleanSymbol}:{binanceInterval}:{limit}";

            var cached = await _redis.StringGetAsync(cacheKey);
            if (cached.HasValue)
            {
                return JsonSerializer.Deserialize<List<MarketCandleModel>>((string)cached!)!;
            }

            var result = await FetchKlinesAsync(cleanSymbol, binanceInterval, limit, endTime, futures: true);

            // ── Fallback to Spot API for small-caps not listed on Futures ────────
            if (result.Count < 5)
            {
                Logger.LogWarning($"⚠️ Futures sin datos para {cleanSymbol}, probando Spot API...");
                result = await FetchKlinesAsync(cleanSymbol, binanceInterval, limit, endTime, futures: false);
            }

            if (result.Count > 0)
            {
                var ttlSeconds = binanceInterval switch {
                    "1m" => 30,
                    "5m" => 120,
                    _ => 300
                };
                await _redis.StringSetAsync(cacheKey, JsonSerializer.Serialize(result), TimeSpan.FromSeconds(ttlSeconds));
            }

            return result;
        }
        catch (Exception ex)
        {
            Logger.LogError($"💥 EXCEPCIÓN en MarketDataManager: {ex.Message}");
            return new List<MarketCandleModel>();
        }
    }

    private async Task<List<MarketCandleModel>> FetchKlinesAsync(string cleanSymbol, string binanceInterval, int limit, long? endTime, bool futures)
    {
        await _binanceGate.WaitAsync();
        try
        {
            var client = _httpClientFactory.CreateClient();
            var baseEndpoint = futures
                ? $"{FuturesBaseUrl}/fapi/v1/klines"
                : $"{BinanceBaseUrl}/api/v3/klines";

            var url = $"{baseEndpoint}?symbol={cleanSymbol}&interval={binanceInterval}&limit={limit}";
            if (endTime.HasValue) url += $"&endTime={endTime.Value}";

            Logger.LogInformation($"📡 Fetching Klines ({(futures ? "Futures" : "Spot")}): {url}");
            var response = await client.GetAsync(url);

            if (!response.IsSuccessStatusCode)
            {
                var err = await response.Content.ReadAsStringAsync();
                Logger.LogWarning($"⚠️ Klines {(futures ? "Futures" : "Spot")} {response.StatusCode} for {cleanSymbol}: {err}");
                return new List<MarketCandleModel>();
            }

            var content = await response.Content.ReadAsStringAsync();
            var rawCandles = JsonSerializer.Deserialize<List<List<JsonElement>>>(content);
            var result = new List<MarketCandleModel>();

            if (rawCandles != null)
            {
                foreach (var raw in rawCandles)
                {
                    result.Add(new MarketCandleModel
                    {
                        Timestamp = raw[0].GetInt64(),
                        Open = ParseDecimal(raw[1]),
                        High = ParseDecimal(raw[2]),
                        Low = ParseDecimal(raw[3]),
                        Close = ParseDecimal(raw[4]),
                        Volume = ParseDecimal(raw[5])
                    });
                }
            }

            return result;
        }
        finally
        {
            _binanceGate.Release();
        }
    }

    public async Task<MarketOrderBookModel> GetOrderBookAsync(string symbol, int limit = 20)
    {
        try
        {
            symbol = symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();

            // 1. Try to get from WebSocket Cache first (Zero latency)
            var wsDepth = _webSocketService.GetOrderBook(symbol);
            if (wsDepth != null && wsDepth.Bids.Any())
            {
                return wsDepth;
            }

            // 2. Fallback to REST API if not in cache or symbol just added
            Logger.LogInformation($"ℹ️ Depth cache miss for {symbol}. Falling back to REST API...");
            
            var client = _httpClientFactory.CreateClient();
            var url = $"{FuturesBaseUrl}/fapi/v1/depth?symbol={symbol}&limit={limit}";
            var response = await client.GetAsync(url);
            
            if (!response.IsSuccessStatusCode) return new MarketOrderBookModel();

            var content = await response.Content.ReadAsStringAsync();
            var doc = JsonDocument.Parse(content);
            var root = doc.RootElement;

            var result = new MarketOrderBookModel();

            foreach (var bid in root.GetProperty("bids").EnumerateArray())
            {
                result.Bids.Add(new OrderBookEntryModel { 
                    Price = ParseDecimal(bid[0]),
                    Amount = ParseDecimal(bid[1])
                });
            }

            foreach (var ask in root.GetProperty("asks").EnumerateArray())
            {
                result.Asks.Add(new OrderBookEntryModel { 
                    Price = ParseDecimal(ask[0]),
                    Amount = ParseDecimal(ask[1])
                });
            }

            return result;
        }
        catch (Exception ex)
        {
            Logger.LogError($"💥 Error al obtener Depth para {symbol}: {ex.Message}");
            return new MarketOrderBookModel();
        }
    }

    public async Task<List<RecentTradeModel>> GetRecentTradesAsync(string symbol, int limit = 20)
    {
        try
        {
            var client = _httpClientFactory.CreateClient();
            symbol = symbol.ToUpper().Replace("/", "").Replace("-", "").Trim();
            
            var url = $"{FuturesBaseUrl}/fapi/v1/trades?symbol={symbol}&limit={limit}";
            var response = await client.GetAsync(url);
            
            if (!response.IsSuccessStatusCode) return new List<RecentTradeModel>();

            var content = await response.Content.ReadAsStringAsync();
            var trades = JsonSerializer.Deserialize<List<JsonElement>>(content);

            var result = new List<RecentTradeModel>();

            if (trades != null)
            {
                foreach (var trade in trades)
                {
                    result.Add(new RecentTradeModel
                    {
                        Id = trade.GetProperty("id").GetInt64(),
                        Price = ParseDecimal(trade.GetProperty("price")),
                        Amount = ParseDecimal(trade.GetProperty("qty")),
                        Time = trade.GetProperty("time").GetInt64(),
                        IsBuyerMaker = trade.GetProperty("isBuyerMaker").GetBoolean()
                    });
                }
            }

            return result;
        }
        catch (Exception ex)
        {
            Logger.LogError($"💥 Error al obtener Trades para {symbol}: {ex.Message}");
            return new List<RecentTradeModel>();
        }
    }

    public async Task<List<SymbolTickerModel>> GetTickersAsync()
    {
        await _tickerGate.WaitAsync();  // dedicated gate - doesn't compete with klines calls
        try
        {
            var client = _httpClientFactory.CreateClient();
            var url = $"{FuturesBaseUrl}/fapi/v1/ticker/24hr";
            var response = await client.GetAsync(url);
            
            if (!response.IsSuccessStatusCode) return new List<SymbolTickerModel>();

            var content = await response.Content.ReadAsStringAsync();
            var tickers = JsonSerializer.Deserialize<List<JsonElement>>(content);

            if (tickers == null) return new List<SymbolTickerModel>();

            return tickers
                .Where(x => x.GetProperty("symbol").GetString()!.EndsWith("USDT"))
                .Select(x => new SymbolTickerModel
                {
                    Symbol = x.GetProperty("symbol").GetString()!,
                    LastPrice = ParseDecimal(x.GetProperty("lastPrice")),
                    PriceChange = ParseDecimal(x.GetProperty("priceChange")),
                    PriceChangePercent = ParseDecimal(x.GetProperty("priceChangePercent")),
                    Volume = ParseDecimal(x.GetProperty("quoteVolume")),
                    HighPrice = ParseDecimal(x.GetProperty("highPrice")),
                    LowPrice = ParseDecimal(x.GetProperty("lowPrice"))
                })
                .ToList();
        }
        catch (Exception ex)
        {
            Logger.LogError($"💥 Error al obtener tickers: {ex.Message}");
            return new List<SymbolTickerModel>();
        }
        finally
        {
            _tickerGate.Release();
        }
    }
    
    private decimal ParseDecimal(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.String)
        {
            return decimal.Parse(element.GetString()!, System.Globalization.CultureInfo.InvariantCulture);
        }
        return element.GetDecimal();
    }
}

public class MarketCandleModel
{
    public long Timestamp { get; set; }
    public decimal Open { get; set; }
    public decimal High { get; set; }
    public decimal Low { get; set; }
    public decimal Close { get; set; }
    public decimal Volume { get; set; }
}

public class MarketOpenInterestModel
{
    public string Symbol { get; set; } = string.Empty;
    public decimal OpenInterest { get; set; }
    public long Timestamp { get; set; }
}

public class MarketOrderBookModel
{
    public List<OrderBookEntryModel> Bids { get; set; } = new();
    public List<OrderBookEntryModel> Asks { get; set; } = new();
}

public class OrderBookEntryModel
{
    public decimal Price { get; set; }
    public decimal Amount { get; set; }
}

public class RecentTradeModel
{
    public long Id { get; set; }
    public decimal Price { get; set; }
    public decimal Amount { get; set; }
    public long Time { get; set; }
    public bool IsBuyerMaker { get; set; }
}

public class SymbolTickerModel
{
    public string Symbol { get; set; } = string.Empty;
    public decimal LastPrice { get; set; }
    public decimal PriceChange { get; set; }
    public decimal PriceChangePercent { get; set; }
    public decimal Volume { get; set; }
    public decimal HighPrice { get; set; }
    public decimal LowPrice { get; set; }
}
