using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System.Net.Http;
using System.Net.Http.Json;
using System.Collections.Generic;
using System;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Text.Json;
using System.Linq;
using Verge.Trading;

namespace Verge.Agent;

[Authorize]
public class AgentAppService : VergeAppService, IAgentAppService
{
    private readonly AgentProcessManager _processManager;
    private readonly MarketHealthService _healthService;
    private readonly IHubContext<AgentHub> _agentHubContext;
    private readonly IHubContext<TradingHub> _tradingHubContext;
    private readonly HttpClient _marketWsClient;

    public AgentAppService(
        AgentProcessManager processManager,
        MarketHealthService healthService,
        IHubContext<AgentHub> agentHubContext,
        IHubContext<TradingHub> tradingHubContext,
        IConfiguration configuration)
    {
        _processManager = processManager;
        _healthService = healthService;
        _agentHubContext = agentHubContext;
        _tradingHubContext = tradingHubContext;
        _marketWsClient = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
    }

    [AllowAnonymous]
    public async Task<object> GetSystemStateAsync()
    {
        try 
        {
            // If cache is empty (first call after startup), probe immediately before reading
            await _healthService.EnsureProbeAsync();

            var (health, isServerRunning, externalStartTime) = _healthService.GetCurrentHealth();
            if (!isServerRunning) isServerRunning = _processManager.IsProcessRunning("MarketWS");

            bool isAgentRunning  = _processManager.IsProcessRunning("Agent");

            string state = "STOPPED";
            if (isAgentRunning)  state = "AGENT_RUNNING";
            else if (isServerRunning) state = "SERVER_READY";

            var startTimeStr = _processManager.GetStartTime(isAgentRunning ? "Agent" : "MarketWS")?.ToString("yyyy-MM-ddTHH:mm:ssZ");
            if (startTimeStr == null && isServerRunning && !isAgentRunning)
            {
                startTimeStr = externalStartTime;
            }

            var marketWsLocalProcess = _processManager.IsProcessRunning("MarketWS");
            var marketWsExternal = isServerRunning && !marketWsLocalProcess && !isAgentRunning;

            return new {
                state,
                startTime = startTimeStr,
                isServerHealthy = isServerRunning,
                health,
                marketWsExternal,
                logs = (marketWsExternal && state == "SERVER_READY") ? await TryGetMarketWsLogsAsync() : null
            };
        }
        catch (Exception ex)
        {
            Logger.LogWarning("⚠️ Error getting system state: {Message}", ex.Message);
            return new { state = "STOPPED" };
        }
    }

    private async Task<List<string>?> TryGetMarketWsLogsAsync()
    {
        try
        {
            var baseUrl = _healthService.GetActiveUrl();
            using var cts = new System.Threading.CancellationTokenSource(TimeSpan.FromMilliseconds(800));
            var response = await _marketWsClient.GetAsync($"{baseUrl}/logs", cts.Token);
            if (response.IsSuccessStatusCode)
            {
                var content = await response.Content.ReadAsStringAsync(cts.Token);
                var parsed = JsonSerializer.Deserialize<JsonElement>(content);
                if (parsed.TryGetProperty("logs", out var logsArray))
                {
                    return logsArray.EnumerateArray().Select(x => x.GetString() ?? "").ToList();
                }
            }
        }
        catch { }
        return null;
    }

    public async Task StartServerAsync()
    {
        var (_, isHealthy, _) = _healthService.GetCurrentHealth();
        if (isHealthy)
        {
            await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
            return;
        }

        await _processManager.StartProcessAsync("MarketWS", "market_ws_server.py");
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
    }

    public async Task StopServerAsync()
    {
        await _processManager.StopAllAsync();
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "STOPPED");
    }

    public async Task StartAgentAsync()
    {
        await _processManager.StartProcessAsync("Agent", "verge_agent.py");
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "AGENT_RUNNING");
    }

    public async Task StopAgentAsync()
    {
        await _processManager.StopProcessAsync("Agent");
        await _agentHubContext.Clients.All.SendAsync("ServerStateChanged", "SERVER_READY");
    }

    public async Task<object> GetAuditSummaryAsync()
    {
        try {
            var url = _healthService.GetActiveUrl();
            return await _marketWsClient.GetFromJsonAsync<object>($"{url}/audit/summary");
        } catch { return new { balance = 0, winRate = 0, trades = 0, pnlTotal = 0 }; }
    }

    public async Task<object> GetStrategyStatsAsync()
    {
        try {
            var url = _healthService.GetActiveUrl();
            return await _marketWsClient.GetFromJsonAsync<object>($"{url}/audit/stats");
        } catch { return new { }; }
    }

    public async Task<object> GetRecentTradesAsync(int limit = 10)
    {
        try {
            var url = _healthService.GetActiveUrl();
            return await _marketWsClient.GetFromJsonAsync<object>($"{url}/audit/trades?limit={limit}");
        } catch { return new List<object>(); }
    }

    public async Task<object> GetTopSymbolsAsync(int limit = 5)
    {
        try {
            var url = _healthService.GetActiveUrl();
            return await _marketWsClient.GetFromJsonAsync<object>($"{url}/audit/top-symbols?limit={limit}");
        } catch { return new List<object>(); }
    }

    public async Task<object> GetOpenPositionsAsync()
    {
        try {
            var url = _healthService.GetActiveUrl();
            return await _marketWsClient.GetFromJsonAsync<object>($"{url}/audit/open");
        } catch { return new List<object>(); }
    }

    public async Task BroadcastSignalAsync(object signal)
    {
        await _tradingHubContext.Clients.All.SendAsync("ReceiveSuperScore", signal);
    }

    public async Task BroadcastSignalsAsync(List<object> signals)
    {
        if (signals == null || signals.Count == 0) return;
        await _tradingHubContext.Clients.All.SendAsync("ReceiveSuperScores", signals);
    }

    public async Task<object> GetGhostAgentsAsync()
    {
        var ghosts = new List<object>();
        try
        {
            var backendPid = _processManager.GetProcessId("Agent");
            
            var startInfo = new System.Diagnostics.ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -Command \"Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python') -and ($_.CommandLine -match 'verge_agent.py') } | Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress\"",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            
            using var proc = System.Diagnostics.Process.Start(startInfo);
            if (proc != null)
            {
                string json = (await proc.StandardOutput.ReadToEndAsync()).Trim();
                await proc.WaitForExitAsync();
                
                if (!string.IsNullOrEmpty(json))
                {
                    using var doc = JsonDocument.Parse(json);
                    if (doc.RootElement.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var el in doc.RootElement.EnumerateArray())
                        {
                            var pid = el.GetProperty("ProcessId").GetInt32();
                            var cmd = el.GetProperty("CommandLine").GetString() ?? "";
                            if (pid != backendPid)
                            {
                                ghosts.Add(new { pid, cmdLine = cmd });
                            }
                        }
                    }
                    else if (doc.RootElement.ValueKind == JsonValueKind.Object)
                    {
                        var pid = doc.RootElement.GetProperty("ProcessId").GetInt32();
                        var cmd = doc.RootElement.GetProperty("CommandLine").GetString() ?? "";
                        if (pid != backendPid)
                        {
                            ghosts.Add(new { pid, cmdLine = cmd });
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Logger.LogWarning("⚠️ Error scanning ghost agents: {Message}", ex.Message);
        }
        return ghosts;
    }

    public async Task PurgeGhostAgentsAsync()
    {
        try
        {
            var backendPid = _processManager.GetProcessId("Agent");
            var ghosts = new List<int>();
            
            var startInfo = new System.Diagnostics.ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -Command \"Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python') -and ($_.CommandLine -match 'verge_agent.py') } | Select-Object ProcessId | ConvertTo-Json -Compress\"",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            
            using var proc = System.Diagnostics.Process.Start(startInfo);
            if (proc != null)
            {
                string json = (await proc.StandardOutput.ReadToEndAsync()).Trim();
                await proc.WaitForExitAsync();
                
                if (!string.IsNullOrEmpty(json))
                {
                    using var doc = JsonDocument.Parse(json);
                    if (doc.RootElement.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var el in doc.RootElement.EnumerateArray())
                        {
                            var pid = el.GetProperty("ProcessId").GetInt32();
                            if (pid != backendPid) ghosts.Add(pid);
                        }
                    }
                    else if (doc.RootElement.ValueKind == JsonValueKind.Object)
                    {
                        var pid = doc.RootElement.GetProperty("ProcessId").GetInt32();
                        if (pid != backendPid) ghosts.Add(pid);
                    }
                }
            }
            
            foreach (var pid in ghosts)
            {
                try
                {
                    using var killProc = System.Diagnostics.Process.GetProcessById(pid);
                    if (!killProc.HasExited)
                    {
                        killProc.Kill(entireProcessTree: true);
                        await killProc.WaitForExitAsync();
                        Logger.LogInformation("Successfully purged ghost agent PID {Pid}", pid);
                    }
                }
                catch (Exception ex)
                {
                    Logger.LogWarning("Failed to kill ghost agent PID {Pid}: {Msg}", pid, ex.Message);
                }
            }
        }
        catch (Exception ex)
        {
            Logger.LogWarning("⚠️ Error purging ghost agents: {Message}", ex.Message);
        }
    }
}
