using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Volo.Abp.DependencyInjection;

namespace Verge.Agent;

public class AgentProcessManager : ISingletonDependency
{
    private const int MarketWsPort = 8001;
    private readonly IHubContext<AgentHub> _hubContext;
    private readonly ILogger<AgentProcessManager> _logger;
    private readonly ConcurrentDictionary<string, Process> _processes = new();
    private readonly ConcurrentDictionary<string, DateTime> _startTimes = new();

    public AgentProcessManager(
        IHubContext<AgentHub> hubContext,
        ILogger<AgentProcessManager> logger)
    {
        _hubContext = hubContext;
        _logger = logger;
    }

    public async Task StartProcessAsync(string name, string scriptName,
        System.Collections.Generic.Dictionary<string, string>? extraEnv = null)
    {
        try
        {
            if (IsProcessRunning(name))
            {
                _logger.LogWarning("{Name} is already running.", name);
                return;
            }

            // Cleanup if it was in the dictionary but exited
            _processes.TryRemove(name, out _);

            if (name == "MarketWS")
            {
                await EnsureMarketWsPortIsFreeAsync();
            }

            string pythonPath = "python";
            string scriptPath = System.IO.Path.Combine(@"C:\Users\Nicolas\Desktop\Verge\Verge\agent", scriptName);

            if (!System.IO.File.Exists(scriptPath))
            {
                await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", $"❌ ERROR: No se encontró el script en {scriptPath}", "#ef4444");
                return;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = pythonPath,
                Arguments = scriptName,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = @"C:\Users\Nicolas\Desktop\Verge\Verge\agent"
            };

            // Inject any extra environment variables (e.g. VERGE_SKIP_SEED=1 during ban)
            if (extraEnv != null)
            {
                foreach (var kv in extraEnv)
                    startInfo.EnvironmentVariables[kv.Key] = kv.Value;
            }

            // EVITAR BUFFERING: Forzar a Python a enviar logs en tiempo real
            startInfo.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
            // EVITAR UnicodeEncodeError en Windows con emojis
            startInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            var process = new Process { StartInfo = startInfo };
            process.EnableRaisingEvents = true;
            process.Exited += (_, _) =>
            {
                _processes.TryRemove(name, out _);
                _startTimes.TryRemove(name, out _);
                _logger.LogInformation("{Name} process exited.", name);
            };

            process.OutputDataReceived += async (sender, args) =>
            {
                if (!string.IsNullOrEmpty(args.Data))
                {
                    _logger.LogInformation("[{Name}] {Data}", name, args.Data);
                    await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", args.Data, null);
                }
            };

            process.ErrorDataReceived += async (sender, args) =>
            {
                if (!string.IsNullOrEmpty(args.Data))
                {
                    _logger.LogError("[{Name} Error] {Data}", name, args.Data);
                    await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", args.Data, "#ef4444");
                }
            };

            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            _processes[name] = process;
            _startTimes[name] = DateTime.Now;

            await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", $"▶️ Proceso {scriptName} iniciado.", "#3b82f6");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start {Name}", name);
            await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", $"❌ ERROR FATAL al iniciar {name}: {ex.Message}", "#ef4444");
        }
    }

    public async Task StopProcessAsync(string name)
    {
        if (_processes.TryRemove(name, out var process))
        {
            _logger.LogInformation("Stopping {Name} process...", name);
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                    if (!process.WaitForExit(5000))
                    {
                        _logger.LogWarning("{Name} did not exit after kill timeout.", name);
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Error stopping {Name} process cleanly.", name);
            }
            finally
            {
                process.Dispose();
            }
            _startTimes.TryRemove(name, out _);
            await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", $"⏹️ Proceso {name} detenido.", "#ef4444");
        }
    }

    public bool IsProcessRunning(string name)
    {
        if (_processes.TryGetValue(name, out var process))
        {
            try {
                return !process.HasExited;
            } catch {
                _processes.TryRemove(name, out _);
                return false;
            }
        }
        return false;
    }

    public DateTime? GetStartTime(string name)
    {
        if (_startTimes.TryGetValue(name, out var startTime))
            return startTime;
        return null;
    }

    public async Task StopAllAsync()
    {
        foreach (var key in _processes.Keys)
        {
            await StopProcessAsync(key);
        }
    }

    private async Task EnsureMarketWsPortIsFreeAsync()
    {
        var listeners = IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners();
        var occupied = false;
        foreach (var endpoint in listeners)
        {
            if (endpoint.Port == MarketWsPort)
            {
                occupied = true;
                break;
            }
        }

        if (!occupied)
        {
            return;
        }

        _logger.LogWarning("Port {Port} is already in use. Attempting stale process cleanup.", MarketWsPort);

        var netstat = new ProcessStartInfo
        {
            FileName = "netstat",
            Arguments = "-ano -p tcp",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var netstatProcess = Process.Start(netstat);
        if (netstatProcess == null)
        {
            return;
        }

        var output = await netstatProcess.StandardOutput.ReadToEndAsync();
        netstatProcess.WaitForExit(2000);

        var pids = new System.Collections.Generic.HashSet<int>();
        var lines = output.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
        foreach (var line in lines)
        {
            try
            {
                if (!line.Contains($":{MarketWsPort} "))
                {
                    continue;
                }

                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length < 5)
                {
                    continue;
                }

                if (int.TryParse(parts[4], out var pid))
                {
                    pids.Add(pid);
                }
            }
            catch
            {
                // Best-effort parsing.
            }
        }

        foreach (var pid in pids)
        {
            try
            {
                using var proc = Process.GetProcessById(pid);
                if (!proc.HasExited)
                {
                    proc.Kill(entireProcessTree: true);
                    proc.WaitForExit(2000);
                }
            }
            catch
            {
                // Best-effort cleanup.
            }
        }

        await Task.Delay(300);
    }
}


