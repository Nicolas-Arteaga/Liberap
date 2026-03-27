using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Verge.Trading.Integrations;

public class BinanceWebSocketService : BackgroundService
{
    private readonly ILogger<BinanceWebSocketService> _logger;
    private readonly ConcurrentDictionary<string, decimal> _symbolLiquidations = new();
    private readonly ConcurrentDictionary<string, double> _symbolBidAskImbalance = new();
    private readonly ConcurrentDictionary<string, bool> _symbolSqueezeDetected = new();

    private readonly ConcurrentDictionary<string, decimal> _symbolLastPrice = new();
    private readonly ConcurrentDictionary<string, DateTime> _symbolLastPriceTime = new();
    
    // 🚀 Depth cache for Order Book (Bids/Asks)
    private readonly ConcurrentDictionary<string, MarketOrderBookModel> _symbolDepth = new();
    private readonly ConcurrentHashSet<string> _activeDepthSymbols = new();

    private const string FuturesStream = "wss://fstream.binance.com/ws/!forceOrder@arr";
    private const string SpotDepthStreamPrefix = "wss://stream.binance.com:9443/ws/";
    private const string MiniTickerAllStream = "wss://fstream.binance.com/ws/!miniTicker@arr";

    public BinanceWebSocketService(ILogger<BinanceWebSocketService> logger)
    {
        _logger = logger;
        // Default base symbols
        _activeDepthSymbols.Add("BTCUSDT");
        _activeDepthSymbols.Add("ETHUSDT");
        _activeDepthSymbols.Add("SOLUSDT");
    }

    public MarketOrderBookModel? GetOrderBook(string symbol)
    {
        var key = symbol.ToUpper();
        if (_activeDepthSymbols.Add(key))
        {
            _logger.LogInformation("➕ New symbol detected: {Symbol}. Adding to WebSocket depth subscription...", key);
        }
        return _symbolDepth.TryGetValue(key, out var depth) ? depth : null;
    }

    public decimal GetRecentLiquidations(string symbol) => _symbolLiquidations.TryGetValue(symbol.ToUpper(), out var value) ? value : 0;
    public double GetBidAskImbalance(string symbol) => _symbolBidAskImbalance.TryGetValue(symbol.ToUpper(), out var value) ? value : 1.0;
    public bool IsSqueezeDetected(string symbol) => _symbolSqueezeDetected.TryGetValue(symbol.ToUpper(), out var value) ? value : false;

    public decimal? GetLastPrice(string symbol)
    {
        var key = symbol.ToUpper();
        if (!_symbolLastPrice.TryGetValue(key, out var price)) return null;
        if (!_symbolLastPriceTime.TryGetValue(key, out var ts)) return null;
        if ((DateTime.UtcNow - ts).TotalSeconds > 30) return null;
        return price;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🚀 Binance WebSocket Service Starting...");
        var futuresTask = RunFuturesStreamAsync(stoppingToken);
        var spotTask = RunSpotDepthStreamAsync(stoppingToken);
        var miniTickerTask = RunMiniTickerStreamAsync(stoppingToken);
        await Task.WhenAll(futuresTask, spotTask, miniTickerTask);
    }

    private async Task RunMiniTickerStreamAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var client = new ClientWebSocket();
                await client.ConnectAsync(new Uri(MiniTickerAllStream), stoppingToken);
                _logger.LogInformation("✅ Connected to Binance Futures Mini-Ticker stream");

                var buffer = new byte[1024 * 64];
                while (client.State == WebSocketState.Open && !stoppingToken.IsCancellationRequested)
                {
                    var result = await client.ReceiveAsync(new ArraySegment<byte>(buffer), stoppingToken);
                    if (result.MessageType == WebSocketMessageType.Close) break;

                    var message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                    ProcessMiniTickers(message);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Mini-Ticker Stream Error. Reconnecting in 5s...");
                await Task.Delay(5000, stoppingToken);
            }
        }
    }

    private void ProcessMiniTickers(string message)
    {
        try
        {
            using var doc = JsonDocument.Parse(message);
            if (doc.RootElement.ValueKind != JsonValueKind.Array) return;
            foreach (var ticker in doc.RootElement.EnumerateArray())
            {
                if (!ticker.TryGetProperty("s", out var symbolProp) || !ticker.TryGetProperty("c", out var closeProp)) continue;
                var symbol = symbolProp.GetString();
                if (string.IsNullOrEmpty(symbol)) continue;
                if (!decimal.TryParse(closeProp.GetString(), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out var price)) continue;
                _symbolLastPrice[symbol] = price;
                _symbolLastPriceTime[symbol] = DateTime.UtcNow;
            }
        } catch { }
    }

    private async Task RunFuturesStreamAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var client = new ClientWebSocket();
                await client.ConnectAsync(new Uri(FuturesStream), stoppingToken);
                _logger.LogInformation("✅ Connected to Binance Futures Force Order Stream");
                var buffer = new byte[1024 * 4];
                while (client.State == WebSocketState.Open && !stoppingToken.IsCancellationRequested)
                {
                    var result = await client.ReceiveAsync(new ArraySegment<byte>(buffer), stoppingToken);
                    if (result.MessageType == WebSocketMessageType.Close) break;
                    ProcessLiquidation(Encoding.UTF8.GetString(buffer, 0, result.Count));
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Futures Stream Error. Reconnecting in 5s...");
                await Task.Delay(5000, stoppingToken);
            }
        }
    }

    private async Task RunSpotDepthStreamAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var symbols = _activeDepthSymbols.Select(s => s.ToLower()).ToList();
                string streamUrl = SpotDepthStreamPrefix + string.Join("/", symbols.Select(s => $"{s}@depth20"));
                using var client = new ClientWebSocket();
                await client.ConnectAsync(new Uri(streamUrl), stoppingToken);
                _logger.LogInformation("✅ Connected to Binance Spot Depth Stream for {Count} symbols", symbols.Count);
                var buffer = new byte[1024 * 16];
                while (client.State == WebSocketState.Open && !stoppingToken.IsCancellationRequested)
                {
                    var result = await client.ReceiveAsync(new ArraySegment<byte>(buffer), stoppingToken);
                    if (result.MessageType == WebSocketMessageType.Close) break;
                    ProcessDepth(Encoding.UTF8.GetString(buffer, 0, result.Count));
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Spot Depth Stream Error. Reconnecting in 5s...");
                await Task.Delay(5000, stoppingToken);
            }
        }
    }

    private void ProcessLiquidation(string message)
    {
        try
        {
            using var doc = JsonDocument.Parse(message);
            var data = doc.RootElement.GetProperty("o");
            string symbol = data.GetProperty("s").GetString();
            decimal quant = decimal.Parse(data.GetProperty("q").GetString());
            decimal price = decimal.Parse(data.GetProperty("p").GetString());
            decimal amount = quant * price;
            _symbolLiquidations.AddOrUpdate(symbol, amount, (k, old) => old + amount);
            if (amount > 500000)
            {
                _symbolSqueezeDetected[symbol] = true;
                _logger.LogWarning("🔥 SQUEEZE DETECTED on {Symbol}: ${Amount:F0} liquidated!", symbol, amount);
                Task.Delay(10000).ContinueWith(_ => _symbolSqueezeDetected[symbol] = false);
            }
        } catch { }
    }

    private void ProcessDepth(string message)
    {
        try
        {
            using var doc = JsonDocument.Parse(message);
            var root = doc.RootElement;
            JsonElement data;
            string symbol;
            if (root.TryGetProperty("stream", out var streamNameProp))
            {
                symbol = streamNameProp.GetString().Split('@')[0].ToUpper();
                data = root.GetProperty("data");
            } else return;

            var bidsArr = data.GetProperty("b").EnumerateArray();
            var asksArr = data.GetProperty("a").EnumerateArray();
            var depth = new MarketOrderBookModel();
            decimal totalBidVol = 0, totalAskVol = 0;

            foreach (var b in bidsArr)
            {
                var p = decimal.Parse(b[0].GetString(), System.Globalization.CultureInfo.InvariantCulture);
                var a = decimal.Parse(b[1].GetString(), System.Globalization.CultureInfo.InvariantCulture);
                depth.Bids.Add(new OrderBookEntryModel { Price = p, Amount = a });
                totalBidVol += a;
            }
            foreach (var a in asksArr)
            {
                var p = decimal.Parse(a[0].GetString(), System.Globalization.CultureInfo.InvariantCulture);
                var am = decimal.Parse(a[1].GetString(), System.Globalization.CultureInfo.InvariantCulture);
                depth.Asks.Add(new OrderBookEntryModel { Price = p, Amount = am });
                totalAskVol += am;
            }
            _symbolDepth[symbol] = depth;
            if (totalAskVol > 0) _symbolBidAskImbalance[symbol] = Math.Round((double)(totalBidVol / totalAskVol), 2);
        } catch { }
    }

    private class ConcurrentHashSet<T>
    {
        private readonly ConcurrentDictionary<T, byte> _dict = new();
        public bool Add(T item) => _dict.TryAdd(item, 0);
        public List<T> ToList() => _dict.Keys.ToList();
        public IEnumerable<T> Select(Func<T, T> func) => _dict.Keys.Select(func);
        public int Count => _dict.Count;
    }
}
