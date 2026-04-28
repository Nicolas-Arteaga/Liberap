using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Volo.Abp.DependencyInjection;

namespace Verge.Agent;

public class AgentProcessManager : ISingletonDependency
{
    private readonly IHubContext<AgentHub> _hubContext;
    private readonly ILogger<AgentProcessManager> _logger;
    private readonly ConcurrentDictionary<string, Process> _processes = new();

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
            if (_processes.TryGetValue(name, out var existingProcess) && !existingProcess.HasExited)
            {
                _logger.LogWarning("{Name} is already running.", name);
                return;
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
        if (_processes.TryRemove(name, out var process) && !process.HasExited)
        {
            _logger.LogInformation("Stopping {Name} process...", name);
            process.Kill();
            process.Dispose();
            await _hubContext.Clients.All.SendAsync("ReceiveAgentLog", $"⏹️ Proceso {name} detenido.", "#ef4444");
        }
    }

    public async Task StopAllAsync()
    {
        foreach (var key in _processes.Keys)
        {
            await StopProcessAsync(key);
        }
    }
}
