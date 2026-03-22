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

    // 🚀 Live price cache — updated every ~1s via WebSocket, zero REST calls
    private readonly ConcurrentDictionary<string, decimal> _symbolLastPrice = new();
    private readonly ConcurrentDictionary<string, DateTime> _symbolLastPriceTime = new();

    private const string FuturesStream = "wss://fstream.binance.com/ws/!forceOrder@arr";
    private const string SpotDepthStreamPrefix = "wss://stream.binance.com:9443/ws/";
    // Mini-ticker stream gives last price + 24h stats for ALL symbols, updated every second
    private const string MiniTickerAllStream = "wss://fstream.binance.com/ws/!miniTicker@arr";

    public BinanceWebSocketService(ILogger<BinanceWebSocketService> logger)
    {
        _logger = logger;
    }

    public decimal GetRecentLiquidations(string symbol)
    {
        return _symbolLiquidations.TryGetValue(symbol.ToUpper(), out var value) ? value : 0;
    }

    public double GetBidAskImbalance(string symbol)
    {
        return _symbolBidAskImbalance.TryGetValue(symbol.ToUpper(), out var value) ? value : 1.0;
    }

    public bool IsSqueezeDetected(string symbol)
    {
        return _symbolSqueezeDetected.TryGetValue(symbol.ToUpper(), out var value) ? value : false;
    }

    /// <summary>
    /// Returns the last known price for a symbol from the WebSocket stream.
    /// Returns null if the symbol hasn't been received yet or data is stale (>30s).
    /// Use this instead of REST polling for fast tick detection.
    /// </summary>
    public decimal? GetLastPrice(string symbol)
    {
        var key = symbol.ToUpper();
        if (!_symbolLastPrice.TryGetValue(key, out var price)) return null;
        if (!_symbolLastPriceTime.TryGetValue(key, out var ts)) return null;
        // Treat data as stale if older than 30 seconds (WebSocket likely disconnected)
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
                _logger.LogInformation("✅ Connected to Binance Futures Mini-Ticker stream (live prices, zero polling)");

                var buffer = new byte[1024 * 64]; // 64k — mini-ticker payload is large
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
                if (!ticker.TryGetProperty("s", out var symbolProp)) continue;
                if (!ticker.TryGetProperty("c", out var closeProp)) continue;

                var symbol = symbolProp.GetString();
                if (string.IsNullOrEmpty(symbol)) continue;
                if (!decimal.TryParse(closeProp.GetString(), System.Globalization.NumberStyles.Any,
                    System.Globalization.CultureInfo.InvariantCulture, out var price)) continue;

                _symbolLastPrice[symbol] = price;
                _symbolLastPriceTime[symbol] = DateTime.UtcNow;
            }
        }
        catch
        {
            // Parse failures are non-critical for price cache
        }
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

                    var message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                    ProcessLiquidation(message);
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
        // For simplicity, we track top symbols. In a real scenario, this could be dynamic.
        string streamUrl = $"{SpotDepthStreamPrefix}btcusdt@depth20/ethusdt@depth20/solusdt@depth20";

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var client = new ClientWebSocket();
                await client.ConnectAsync(new Uri(streamUrl), stoppingToken);
                _logger.LogInformation("✅ Connected to Binance Spot Depth Stream");

                var buffer = new byte[1024 * 8];
                while (client.State == WebSocketState.Open && !stoppingToken.IsCancellationRequested)
                {
                    var result = await client.ReceiveAsync(new ArraySegment<byte>(buffer), stoppingToken);
                    if (result.MessageType == WebSocketMessageType.Close) break;

                    var message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                    ProcessDepth(message);
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
            decimal quantity = decimal.Parse(data.GetProperty("q").GetString());
            decimal price = decimal.Parse(data.GetProperty("p").GetString());
            decimal amount = quantity * price;

            _symbolLiquidations.AddOrUpdate(symbol, amount, (k, old) => old + amount);
            
            // Logic for squeeze detection: if amount > $500k in a single burst (simplified)
            if (amount > 500000)
            {
                _symbolSqueezeDetected[symbol] = true;
                _logger.LogWarning("🔥 SQUEEZE DETECTED on {Symbol}: ${Amount:F0} liquidated!", symbol, amount);
                
                // Reset squeeze after 10 seconds
                Task.Delay(10000).ContinueWith(_ => _symbolSqueezeDetected[symbol] = false);
            }
        }
        catch (Exception ex)
        {
            _logger.LogTrace("Error parsing liquidation: {Msg}", ex.Message);
        }
    }

    private void ProcessDepth(string message)
    {
        try
        {
            using var doc = JsonDocument.Parse(message);
            var root = doc.RootElement;
            if (!root.TryGetProperty("stream", out var streamNameProp)) return;
            
            string streamName = streamNameProp.GetString();
            string symbol = streamName.Split('@')[0].ToUpper();
            
            var data = root.GetProperty("data");
            var bidsArr = data.GetProperty("b").EnumerateArray();
            var asksArr = data.GetProperty("a").EnumerateArray();

            decimal totalBidVol = 0;
            foreach (var b in bidsArr) totalBidVol += decimal.Parse(b[1].GetString());

            decimal totalAskVol = 0;
            foreach (var a in asksArr) totalAskVol += decimal.Parse(a[1].GetString());

            if (totalAskVol > 0)
            {
                double ratio = (double)(totalBidVol / totalAskVol);
                _symbolBidAskImbalance[symbol] = Math.Round(ratio, 2);
            }
        }
        catch (Exception ex)
        {
             // _logger.LogTrace("Error parsing depth: {Msg}", ex.Message);
        }
    }
}
