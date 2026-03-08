using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Mvc;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Users;
using Volo.Abp.Uow;
using Microsoft.AspNetCore.SignalR;
using Verge.Trading.DecisionEngine;
using Verge.Trading.DecisionEngine.Profiles;
using Verge.Trading.Optimization;
using Verge.Trading.DTOs;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;

namespace Verge.Trading;

[Authorize]
public class TradingAppService : ApplicationService, ITradingAppService
{
    private readonly IRepository<TraderProfile, Guid> _profileRepository;
    private readonly IRepository<TradingSignal, Guid> _signalRepository;
    private readonly IRepository<TradingStrategy, Guid> _strategyRepository;
    private readonly IRepository<TradeOrder, Guid> _orderRepository;
    private readonly IRepository<TradingSession, Guid> _sessionRepository;
    private readonly IRepository<TradingAlert, Guid> _alertRepository;
    private readonly IRepository<BacktestResult, Guid> _backtestRepository;
    private readonly IRepository<ExchangeConnection, Guid> _exchangeRepository;
    private readonly IRepository<AnalysisLog, Guid> _analysisLogRepository;
    private readonly MarketDataManager _marketDataManager;
    private readonly CryptoAnalysisService _analysisService;
    private readonly ILogger<TradingAppService> _logger;
    private readonly IHubContext<TradingHub> _hubContext;
    private readonly ITradingDecisionEngine _decisionEngine;
    private readonly OptimizationService _optimizationService;
    private readonly IRepository<TemporalOptimizationResult, Guid> _optimizationResultRepository;
    private readonly IRepository<StrategyCalibration, Guid> _calibrationRepository;
    private readonly IServiceScopeFactory _serviceScopeFactory;

    public TradingAppService(
        IRepository<TraderProfile, Guid> profileRepository,
        IRepository<TradingSignal, Guid> signalRepository,
        IRepository<TradingStrategy, Guid> strategyRepository,
        IRepository<TradeOrder, Guid> orderRepository,
        IRepository<TradingSession, Guid> sessionRepository,
        IRepository<TradingAlert, Guid> alertRepository,
        IRepository<BacktestResult, Guid> backtestRepository,
        IRepository<ExchangeConnection, Guid> exchangeRepository,
        IRepository<AnalysisLog, Guid> analysisLogRepository,
        MarketDataManager marketDataManager,
        CryptoAnalysisService analysisService,
        ILogger<TradingAppService> logger,
        ITradingDecisionEngine decisionEngine,
        OptimizationService optimizationService,
        IRepository<TemporalOptimizationResult, Guid> optimizationResultRepository,
        IRepository<StrategyCalibration, Guid> calibrationRepository,
        IServiceScopeFactory serviceScopeFactory,
        IHubContext<TradingHub>? hubContext = null)
    {
        _profileRepository = profileRepository;
        _signalRepository = signalRepository;
        _strategyRepository = strategyRepository;
        _orderRepository = orderRepository;
        _sessionRepository = sessionRepository;
        _alertRepository = alertRepository;
        _backtestRepository = backtestRepository;
        _exchangeRepository = exchangeRepository;
        _analysisLogRepository = analysisLogRepository;
        _marketDataManager = marketDataManager;
        _analysisService = analysisService;
        _logger = logger;
        _hubContext = hubContext;
        _decisionEngine = decisionEngine;
        _optimizationService = optimizationService;
        _optimizationResultRepository = optimizationResultRepository;
        _calibrationRepository = calibrationRepository;
        _serviceScopeFactory = serviceScopeFactory;
    }

    public async Task<TraderProfileDto> GetProfileAsync()
    {
        var profile = await GetProfileInternalAsync(CurrentUser.Id);
        return ObjectMapper.Map<TraderProfile, TraderProfileDto>(profile);
    }

    protected virtual async Task<TraderProfile> GetProfileInternalAsync(Guid? userId)
    {
        if (userId == null)
        {
            _logger.LogWarning("⚠️ Intento de obtener perfil sin UserId en contexto.");
            return null;
        }

        var profile = await _profileRepository.FirstOrDefaultAsync(x => x.UserId == userId.Value);
        if (profile == null)
        {
            profile = new TraderProfile(
                GuidGenerator.Create(),
                userId.Value,
                "Usuario", 
                "email@ejemplo.com", 
                TradingLevel.Beginner,
                RiskTolerance.Medium
            );
            await _profileRepository.InsertAsync(profile);
        }
        return profile;
    }

    public async Task<TraderProfileDto> UpdateProfileAsync(UpdateTraderProfileDto input)
    {
        var profile = await _profileRepository.GetAsync(x => x.UserId == CurrentUser.GetId());
        profile.Name = input.Name;
        profile.Level = input.Level;
        profile.RiskTolerance = input.RiskTolerance;
        await _profileRepository.UpdateAsync(profile);
        return ObjectMapper.Map<TraderProfile, TraderProfileDto>(profile);
    }

    public async Task<PagedResultDto<TradingSignalDto>> GetSignalsAsync(GetSignalsInput input)
    {
        var query = await _signalRepository.GetQueryableAsync();
        
        if (input.Status.HasValue)
            query = query.Where(x => x.Status == input.Status.Value);
        
        if (input.Confidence.HasValue)
            query = query.Where(x => x.Confidence == input.Confidence.Value);

        var totalCount = await AsyncExecuter.CountAsync(query);
        var signals = await AsyncExecuter.ToListAsync(query.OrderByDescending(x => x.AnalyzedDate).PageBy(input));

        return new PagedResultDto<TradingSignalDto>(totalCount, ObjectMapper.Map<List<TradingSignal>, List<TradingSignalDto>>(signals));
    }

    public async Task<List<TradingStrategyDto>> GetStrategiesAsync()
    {
        var profile = await GetProfileAsync();
        var strategies = await _strategyRepository.GetListAsync(x => x.TraderProfileId == profile.Id);
        return ObjectMapper.Map<List<TradingStrategy>, List<TradingStrategyDto>>(strategies);
    }

    public async Task<TradingStrategyDto> CreateStrategyAsync(CreateUpdateTradingStrategyDto input)
    {
        try
        {
            var profile = await GetProfileAsync();
            
            // Check for active hunt/session
            var activeSession = await _sessionRepository.FirstOrDefaultAsync(x => x.TraderProfileId == profile.Id && x.IsActive);
            if (activeSession != null)
            {
                throw new Volo.Abp.UserFriendlyException("Ya tenés una cacería activa. Finalizala desde el dashboard antes de crear una nueva");
            }

            _logger.LogInformation("🚀 [VERGE] Creando estrategia: {Name} | User: {User} | Profile: {ProfileId}", 
                input.Name, CurrentUser.UserName, profile.Id);
            
            _logger.LogInformation("📊 Datos: Leverage={Leverage}, Capital={Capital}, Cryptos={Cryptos}", 
                input.Leverage, input.Capital, string.Join(",", input.SelectedCryptos ?? new List<string>()));

            var strategy = ObjectMapper.Map<CreateUpdateTradingStrategyDto, TradingStrategy>(input);
            strategy.TraderProfileId = profile.Id;
            
            // Ensure serialization
            strategy.SelectedCryptosJson = System.Text.Json.JsonSerializer.Serialize(input.SelectedCryptos ?? new List<string>());
            strategy.IsActive = true; 
            strategy.IsAutoMode = input.IsAutoMode;
            
            // Handle CustomSymbolsJson safely
            strategy.CustomSymbolsJson = input.CustomSymbols != null && input.CustomSymbols.Count > 0 
                ? System.Text.Json.JsonSerializer.Serialize(input.CustomSymbols) 
                : "[]";
            
            _logger.LogInformation("💾 Guardando estrategia en DB...");
            await _strategyRepository.InsertAsync(strategy, autoSave: true);
            
            _logger.LogInformation("✅ Estrategia creada con ID: {Id}", strategy.Id);
            return ObjectMapper.Map<TradingStrategy, TradingStrategyDto>(strategy);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ ERROR CRÍTICO al crear estrategia: {Message}", ex.Message);
            throw; // Re-throw to allow ABP handle the 500 but now with logs
        }
    }

    public async Task<TradingStrategyDto> UpdateStrategyAsync(Guid id, CreateUpdateTradingStrategyDto input)
    {
        var strategy = await _strategyRepository.GetAsync(id);
        // Ownership check
        var profile = await GetProfileAsync();
        if (strategy.TraderProfileId != profile.Id) throw new UnauthorizedAccessException();

        // Map fields manually or use a specific update mapper
        strategy.Name = input.Name;
        strategy.DirectionPreference = input.DirectionPreference;
        strategy.SelectedCryptosJson = System.Text.Json.JsonSerializer.Serialize(input.SelectedCryptos);
        strategy.Leverage = input.Leverage;
        strategy.Capital = input.Capital;
        strategy.RiskLevel = input.RiskLevel;
        strategy.AutoStopLoss = input.AutoStopLoss;
        strategy.TakeProfitPercentage = input.TakeProfitPercentage;
        strategy.StopLossPercentage = input.StopLossPercentage;
        strategy.NotificationsEnabled = input.NotificationsEnabled;
        strategy.IsAutoMode = input.IsAutoMode;
        strategy.CustomSymbolsJson = input.CustomSymbols != null ? System.Text.Json.JsonSerializer.Serialize(input.CustomSymbols) : null;

        await _strategyRepository.UpdateAsync(strategy);
        return ObjectMapper.Map<TradingStrategy, TradingStrategyDto>(strategy);
    }

    public async Task DeleteStrategyAsync(Guid id)
    {
        var strategy = await _strategyRepository.GetAsync(id);
        var profile = await GetProfileAsync();
        if (strategy.TraderProfileId != profile.Id) throw new UnauthorizedAccessException();
        await _strategyRepository.DeleteAsync(id);
    }

    public async Task<TradeOrderDto> ExecuteTradeAsync(ExecuteTradeDto input)
    {
        var profile = await GetProfileAsync();
        var order = new TradeOrder(
            GuidGenerator.Create(),
            profile.Id,
            input.Symbol,
            input.Direction,
            input.Amount,
            input.Leverage,
            68500 // Mock entry price
        );
        
        order.OrderType = input.OrderType;
        order.TakeProfitPrice = order.EntryPrice * (1 + input.TakeProfitPercentage / 100);
        order.StopLossPrice = order.EntryPrice * (1 - input.StopLossPercentage / 100);

        await _orderRepository.InsertAsync(order);
        return ObjectMapper.Map<TradeOrder, TradeOrderDto>(order);
    }

    public async Task<PagedResultDto<TradeOrderDto>> GetOrderHistoryAsync(GetHistoryInput input)
    {
        var profile = await GetProfileAsync();
        var query = await _orderRepository.GetQueryableAsync();
        query = query.Where(x => x.TraderProfileId == profile.Id);

        if (!string.IsNullOrEmpty(input.Symbol))
            query = query.Where(x => x.Symbol == input.Symbol);

        var totalCount = await AsyncExecuter.CountAsync(query);
        var orders = await AsyncExecuter.ToListAsync(query.OrderByDescending(x => x.ExecutionDate).PageBy(input));

        return new PagedResultDto<TradeOrderDto>(totalCount, ObjectMapper.Map<List<TradeOrder>, List<TradeOrderDto>>(orders));
    }

    public async Task<TradingSessionDto> StartSessionAsync(StartSessionDto input)
    {
        var profile = await GetProfileAsync();
        // Deactivate previous active sessions
        var activeSessions = await _sessionRepository.GetListAsync(x => x.TraderProfileId == profile.Id && x.IsActive);
        foreach (var s in activeSessions)
        {
            s.IsActive = false;
            await _sessionRepository.UpdateAsync(s);
        }

        var session = new TradingSession(GuidGenerator.Create(), profile.Id, input.Symbol, input.Timeframe);
        session.IsActive = true;
        await _sessionRepository.InsertAsync(session, autoSave: true);

        // Notificar inicio de sesión por SignalR
        await _hubContext.Clients.All.SendAsync("SessionStarted", ObjectMapper.Map<TradingSession, TradingSessionDto>(session));

        return ObjectMapper.Map<TradingSession, TradingSessionDto>(session);
    }

    public async Task<TradingSessionDto> GetCurrentSessionAsync()
    {
        var profile = await GetProfileAsync();
        _logger.LogInformation("🔍 [GetCurrentSession] Buscando sesión para perfil {ProfileId}", profile.Id);
        
        var session = await _sessionRepository.FirstOrDefaultAsync(
            x => x.TraderProfileId == profile.Id && 
                 x.IsActive
        );
        
        if (session == null)
        {
            _logger.LogWarning("⚠️ [GetCurrentSession] NO se encontró sesión activa para perfil {ProfileId}", profile.Id);
        }
        else
        {
            _logger.LogInformation("✅ [GetCurrentSession] Sesión encontrada: {Id}, Activa: {IsActive}", 
                session.Id, session.IsActive);
        }
        
        return session != null ? ObjectMapper.Map<TradingSession, TradingSessionDto>(session) : null;
    }

    public async Task<TradingSessionDto> AdvanceStageAsync(Guid sessionId)
    {
        var session = await _sessionRepository.GetAsync(sessionId);
        if ((int)session.CurrentStage < 4)
        {
            session.CurrentStage = (TradingStage)((int)session.CurrentStage + 1);
            await _sessionRepository.UpdateAsync(session);
            
            // Notificar avance de etapa
            await _hubContext.Clients.All.SendAsync("StageAdvanced", ObjectMapper.Map<TradingSession, TradingSessionDto>(session));
        }
        return ObjectMapper.Map<TradingSession, TradingSessionDto>(session);
    }

    [HttpPost("api/app/trading/finalize-hunt/{sessionId}")]
    public async Task<TradingSessionDto> FinalizeHuntAsync(Guid sessionId)
    {
        var session = await _sessionRepository.GetAsync(sessionId);
        var profile = await GetProfileAsync();

        if (session.TraderProfileId != profile.Id)
        {
            throw new UnauthorizedAccessException("La sesión no pertenece al usuario actual.");
        }

        _logger.LogInformation("🏁 Finalizando cacería para la sesión {SessionId}", sessionId);

        session.IsActive = false;
        session.EndTime = DateTime.UtcNow;
        await _sessionRepository.UpdateAsync(session, autoSave: true);
        await _sessionRepository.DeleteAsync(session, autoSave: true); 

        // Borrar la estrategia activa asociada
        var strategy = await _strategyRepository.FirstOrDefaultAsync(x => x.TraderProfileId == profile.Id && x.IsActive);
        if (strategy != null)
        {
            strategy.IsActive = false;
            await _strategyRepository.UpdateAsync(strategy, autoSave: true);
            await _strategyRepository.DeleteAsync(strategy.Id, autoSave: true); 
            _logger.LogInformation("🗑️ Estrategia {StrategyId} eliminada físicamente", strategy.Id);
        }

        // Limpiar registros de análisis asociados a ESTA sesión
        var logs = await _analysisLogRepository.GetListAsync(x => x.TradingSessionId == sessionId);
        foreach (var log in logs)
        {
            await _analysisLogRepository.DeleteAsync(log.Id);
        }
        _logger.LogInformation("🧹 {Count} registros de análisis eliminados para la sesión {SessionId}", logs.Count, sessionId);

        // Notificar fin de sesión
        await _hubContext.Clients.All.SendAsync("SessionEnded", sessionId);

        return ObjectMapper.Map<TradingSession, TradingSessionDto>(session);
    }

    public async Task<List<AnalysisLogDto>> GetAnalysisLogsAsync(Guid sessionId, int limit = 50)
    {
        var query = await _analysisLogRepository.GetQueryableAsync();
        
        // Si sessionId NO es vacío, filtrar por sesión
        // Si es vacío (0000...), traer TODOS los logs
        if (sessionId != Guid.Empty)
        {
            query = query.Where(x => x.TradingSessionId == sessionId);
        }
        
        var logs = await AsyncExecuter.ToListAsync(
            query.OrderByDescending(x => x.Timestamp)
                 .Take(limit)
        );
        
        return ObjectMapper.Map<List<AnalysisLog>, List<AnalysisLogDto>>(logs);
    }

    public async Task<List<TradingAlertDto>> GetActiveAlertsAsync()
    {
        var profile = await GetProfileAsync();
        var alerts = await _alertRepository.GetListAsync(x => x.TraderProfileId == profile.Id && x.IsActive);
        return ObjectMapper.Map<List<TradingAlert>, List<TradingAlertDto>>(alerts);
    }

    public async Task<TradingAlertDto> CreateAlertAsync(CreateUpdateTradingAlertDto input)
    {
        var profile = await GetProfileAsync();
        var alert = new TradingAlert(GuidGenerator.Create(), profile.Id, input.Symbol, input.TriggerPrice, input.Message, input.Type);
        alert.ChannelsJson = System.Text.Json.JsonSerializer.Serialize(input.Channels);
        await _alertRepository.InsertAsync(alert);
        return ObjectMapper.Map<TradingAlert, TradingAlertDto>(alert);
    }

    public async Task DeactivateAlertAsync(Guid id)
    {
        var alert = await _alertRepository.GetAsync(id);
        alert.IsActive = false;
        await _alertRepository.UpdateAsync(alert);
    }

    public async Task<BacktestResultDto> RunBacktestAsync(RunBacktestDto input)
    {
        return await RunBacktestInternalAsync(input);
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    public virtual async Task<BacktestResultDto> RunBacktestInternalAsync(RunBacktestDto input, List<TradingSignal> preloadedSignals = null, Guid? userId = null)
    {
        // Use preloaded signals or fetch from DB
        var candles = preloadedSignals ?? await _signalRepository.GetListAsync(x => x.Symbol == input.Symbol && x.AnalyzedDate >= input.StartDate && x.AnalyzedDate <= input.EndDate);
        var strategy = await _strategyRepository.GetAsync(input.TradingStrategyId);

        var profile = await GetProfileInternalAsync(userId ?? CurrentUser.Id);
        if (profile == null) throw new UserFriendlyException("Perfil de usuario no disponible para backtesting.");
        var session = new TradingSession(GuidGenerator.Create(), profile.Id, input.Symbol, "1h")
        {
            StartTime = input.StartDate
        };

        int totalTrades = 0;
        int wins = 0;
        decimal totalPnL = 0;

        foreach (var candle in candles.OrderBy(x => x.AnalyzedDate))
        {
            var context = CreateVirtualContext(candle, candles);
            var decision = await _decisionEngine.EvaluateAsync(
                session, 
                strategy.Style, 
                context, 
                weightOverrides: input.WeightOverrides,
                entryThresholdOverride: input.EntryThresholdOverride,
                trailingMultiplierOverride: input.TrailingMultiplierOverride);

            if (decision.Decision == TradingDecision.Entry)
            {
                totalTrades++;
                if (decision.WinProbability > 0.6) 
                {
                    wins++;
                    totalPnL += 100 * (decimal)(decision.RiskRewardRatio ?? 2.0);
                }
                else
                {
                    totalPnL -= 100;
                }
            }
        }

        var (pf, sharpe, winRate) = _optimizationService.CalculateAdvancedMetrics(totalTrades, wins, totalPnL);

        return new BacktestResultDto
        {
            Symbol = input.Symbol,
            TotalTrades = totalTrades,
            WinningTrades = wins,
            WinRate = winRate,
            TotalProfit = totalPnL,
            ProfitFactor = pf,
            SharpeRatio = sharpe
        };
    }

    public async Task OptimizeRegimeAsync(string regime, string symbol)
    {
        await OptimizeRegimeInternalAsync(regime, symbol, null);
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    public virtual async Task OptimizeRegimeInternalAsync(string regime, string symbol, List<TradingSignal> preloadedSignals, Guid? userId = null)
    {
        _logger.LogInformation("🎯 Starting Mass Optimization for Regime: {Regime} | Symbol: {Symbol}", regime, symbol);

        var strategy = (await _strategyRepository.GetListAsync()).FirstOrDefault();
        if (strategy == null) return;

        var permutations = _optimizationService.GenerateWeightPermutations();
        double bestPF = -1.0;
        TemporalOptimizationResult bestResult = null;

        int[] thresholds = { 50, 60, 70 }; // Reduced steps for performance
        float[] multipliers = { 1.5f, 2.5f };

        int totalCombinations = permutations.Count * thresholds.Length * multipliers.Length;
        int current = 0;

        foreach (var p in permutations)
        {
            foreach (var thresh in thresholds)
            {
                foreach (var mult in multipliers)
                {
                    current++;
                    if (current % 50 == 0) // Update UI every 50 simulations
                    {
                        var progress = (int)((float)current / totalCombinations * 100);
                        await SendProgressAsync(regime, progress);
                    }

                    var backtest = await RunBacktestInternalAsync(new RunBacktestDto
                    {
                        TradingStrategyId = strategy.Id,
                        Symbol = symbol,
                        StartDate = DateTime.UtcNow.AddMonths(-6),
                        EndDate = DateTime.UtcNow,
                        WeightOverrides = p,
                        EntryThresholdOverride = thresh,
                        TrailingMultiplierOverride = mult
                    }, preloadedSignals, userId);

                    var metrics = _optimizationService.CalculateAdvancedMetrics(backtest.TotalTrades, backtest.WinningTrades, backtest.TotalProfit);

                    if (metrics.ProfitFactor > bestPF)
                    {
                        bestPF = metrics.ProfitFactor;
                        bestResult = new TemporalOptimizationResult(GuidGenerator.Create())
                        {
                            Regime = regime,
                            Symbol = symbol,
                            WeightsJson = JsonSerializer.Serialize(p),
                            ProfitFactor = bestPF,
                            SharpeRatio = metrics.Sharpe,
                            WinRate = metrics.WinRate,
                            TotalTrades = backtest.TotalTrades,
                            TotalPnL = backtest.TotalProfit,
                            EntryThreshold = thresh,
                            TrailingMultiplier = mult
                        };
                    }
                }
            }
        }

        if (bestResult != null)
        {
            await _optimizationResultRepository.InsertAsync(bestResult);
            _logger.LogInformation("🏆 BEST RESULT FOUND for {Regime}: PF {PF:F2}", regime, bestPF);
        }
    }

    public async Task ExecuteMassOptimizationAsync(string symbol)
    {
        // Capture current user ID from request thread
        var currentUserId = CurrentUser.Id;

        // Start background execution using a fresh scope to avoid ObjectDisposedException
        _ = Task.Run(async () => {
            using (var scope = _serviceScopeFactory.CreateScope())
            {
                var scopedTradingService = scope.ServiceProvider.GetRequiredService<TradingAppService>();
                var scopedHubContext = scope.ServiceProvider.GetRequiredService<IHubContext<TradingHub>>();
                var scopedLogger = scope.ServiceProvider.GetRequiredService<ILogger<TradingAppService>>();
                var uowManager = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();

                // Explicitly start a NEW Unit of Work (independent from the parent request)
                using (var uow = uowManager.Begin(requiresNew: true, isTransactional: false))
                {
                    try 
                    {
                        scopedLogger.LogInformation("🚀 [Background] Starting Mass Optimization for {Symbol} | User: {UserId}", symbol, currentUserId);
                        
                        // Preload signals for the last 6 months
                        var startDate = DateTime.UtcNow.AddMonths(-6);
                        var signalRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingSignal, Guid>>();
                        var preloaded = await signalRepo.GetListAsync(x => x.Symbol == symbol && x.AnalyzedDate >= startDate);

                        string[] regimes = { "BullTrend", "BearTrend", "Ranging", "HighVolatility" };
                        foreach (var regime in regimes)
                        {
                            await scopedTradingService.OptimizeRegimeInternalAsync(regime, symbol, preloaded, currentUserId);
                        }

                        // Necessary to persist changes if any
                        await uow.CompleteAsync();

                        await scopedHubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto {
                            Title = "Simulaciones Completadas",
                            Message = $"Se terminaron las simulaciones para {symbol}. Iniciando consolidación...",
                            Type = "Info",
                            Severity = "info"
                        });

                        // Phase 3: Consolidate and Calibrate
                        await scopedTradingService.ConsolidateAndCalibrateAsync(symbol);

                        await scopedHubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto {
                            Title = "Optimización y Calibración Finalizada",
                            Message = $"Se aplicaron los mejores pesos para {symbol} en todos los regímenes.",
                            Type = "Success",
                            Severity = "success"
                        });
                    }
                    catch (Exception ex)
                    {
                        scopedLogger.LogError(ex, "Error during mass optimization in background thread");
                    }
                }
            }
        });

        await Task.CompletedTask;
    }

    private async Task SendProgressAsync(string regime, int progress)
    {
        await _hubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto
        {
            Id = Guid.NewGuid().ToString(),
            Title = "Progreso Optimización",
            Message = $"Régimen {regime}: {progress}% completado...",
            Type = "System",
            Severity = "info",
            Timestamp = DateTime.UtcNow
        });
    }

    private MarketContext CreateVirtualContext(TradingSignal currentCandle, List<TradingSignal> history)
    {
        return new MarketContext
        {
            Candles = new List<MarketCandleModel>(), // Empty mock for speed
            Technicals = new TechnicalsResponseModel
            {
                Rsi = 50, 
                MacdHistogram = 0,
                Adx = 25
            },
            MarketRegime = new RegimeResponseModel
            {
                Regime = MarketRegimeType.Ranging,
                TrendStrength = 60
            }
        };
    }

    public async Task<ExchangeConnectionDto> ConnectExchangeAsync(ConnectExchangeDto input)
    {
        var profile = await GetProfileAsync();
        var connection = new ExchangeConnection(GuidGenerator.Create(), profile.Id, input.ExchangeName, input.ApiKey, input.ApiSecret);
        await _exchangeRepository.InsertAsync(connection);
        return ObjectMapper.Map<ExchangeConnection, ExchangeConnectionDto>(connection);
    }

    public async Task<List<ExchangeConnectionDto>> GetConnectionsAsync()
    {
        var profile = await GetProfileAsync();
        var connections = await _exchangeRepository.GetListAsync(x => x.TraderProfileId == profile.Id);
        return ObjectMapper.Map<List<ExchangeConnection>, List<ExchangeConnectionDto>>(connections);
    }

    public async Task<RecommendedStyleDto> RecommendTradingStyleAsync(string symbol)
    {
        _logger.LogInformation("🔍 Evaluando estilo recomendado para {Symbol}", symbol);
        
        // Obtenemos velas de 1h como base para la volatilidad y tendencia macro
        var candles = await _marketDataManager.GetCandlesAsync(symbol, "1h", 50);
        
        var (style, reason) = _analysisService.RecommendTradingStyle(candles);
        
        _logger.LogInformation("💡 Estilo recomendado para {Symbol}: {Style} - {Reason}", symbol, style, reason);
        
        return new RecommendedStyleDto
        {
            Style = style,
            Reason = reason
        };
    }

    public Task<MarketAnalysisDto> GetMarketAnalysisDummyAsync()
    {
        throw new NotImplementedException();
    }

    public Task<OpportunityDto> GetOpportunityDummyAsync()
    {
        throw new NotImplementedException();
    }

    [HttpGet("get-verge-alert-dummy")]
    public Task<VergeAlertDto> GetVergeAlertDummyAsync()
    {
        throw new NotImplementedException();
    }

    [HttpGet("api/app/trading/test-signalr")]
    public async Task TestSignalRAsync()
    {
        var userId = CurrentUser.Id?.ToString();
        if (string.IsNullOrEmpty(userId)) return;

        await _hubContext.Clients.User(userId).SendAsync("ReceiveAlert", new VergeAlertDto
        {
            Id = Guid.NewGuid().ToString(),
            Type = "System",
            Title = "Test SignalR",
            Message = "Si ves esto, SignalR funciona con cookies perfectly!",
            Timestamp = DateTime.UtcNow,
            Read = false,
            Severity = "success",
            Icon = "checkmark-circle-outline"
        });
    }

    [AllowAnonymous]
    [HttpGet("api/app/trading/test-signalr-public")]
    public async Task TestSignalRPublicAsync()
    {
        await _hubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto
        {
            Id = Guid.NewGuid().ToString(),
            Type = "System",
            Title = "Test Público SignalR",
            Message = "Si ves esto, la conexión SignalR base está establecida (incluso sin Auth funcandon).",
            Timestamp = DateTime.UtcNow,
            Read = false,
            Severity = "info",
            Icon = "megaphone-outline"
        });
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    public virtual async Task ConsolidateAndCalibrateAsync(string symbol)
    {
        _logger.LogInformation("🚀 [Consolidate] Starting final consolidation for symbol {Symbol}", symbol);
        
        var bestResults = await _optimizationResultRepository.GetListAsync(x => x.Symbol == symbol);
        if (!bestResults.Any()) return;

        // Group by regime and pick BEST (Max ProfitFactor)
        var regimes = new[] { "BullTrend", "BearTrend", "Ranging", "HighVolatility" };
        var consolidatedDict = new Dictionary<string, object>();

        foreach (var rName in regimes)
        {
            var best = bestResults
                .Where(x => x.Regime == rName)
                .OrderByDescending(x => x.ProfitFactor)
                .FirstOrDefault();

            if (best != null)
            {
                consolidatedDict[rName] = new {
                    best.WeightsJson,
                    best.EntryThreshold,
                    best.TrailingMultiplier,
                    Metrics = new {
                        best.ProfitFactor,
                        best.SharpeRatio,
                        best.WinRate,
                        best.TotalTrades
                    }
                };

                // Update StrategyCalibration in DB (Using Auto Style by default for global optimization)
                await UpdateCalibrationFromBestAsync(rName, best);
            }
        }

        // Write to output file (JSON Matrix)
        var json = JsonSerializer.Serialize(consolidatedDict, new JsonSerializerOptions { WriteIndented = true });
        var outputPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "optimal_weights.json");
        await System.IO.File.WriteAllTextAsync(outputPath, json);
        
        _logger.LogInformation("✅ [Consolidate] Optimal Matrix saved to {Path}", outputPath);
    }

    private async Task UpdateCalibrationFromBestAsync(string regimeName, TemporalOptimizationResult best)
    {
        if (!Enum.TryParse<MarketRegimeType>(regimeName, out var regimeEnum)) return;

        // Get or Create Calibration for this regime (Using Auto Style by default for global optimization)
        var calibration = await _calibrationRepository.FirstOrDefaultAsync(x => x.Regime == regimeEnum && x.Style == TradingStyle.Auto);
        
        if (calibration == null)
        {
            calibration = new StrategyCalibration(GuidGenerator.Create(), TradingStyle.Auto, regimeEnum);
            await _calibrationRepository.InsertAsync(calibration);
        }

        calibration.WeightsJson = best.WeightsJson;
        calibration.ProfitFactor = best.ProfitFactor;
        calibration.SharpeRatio = best.SharpeRatio;
        calibration.WinRate = best.WinRate;
        calibration.TotalTrades = (int)best.TotalTrades;
        calibration.EntryThreshold = best.EntryThreshold;
        calibration.TrailingMultiplier = best.TrailingMultiplier;
        calibration.LastRecalibrated = DateTime.UtcNow;

        await _calibrationRepository.UpdateAsync(calibration);
        _logger.LogInformation("💾 Calibration updated for {Regime} in DB", regimeName);
    }

    [HttpGet("api/app/trading/optimization-matrix")]
    public async Task<string> GetOptimizationMatrixAsync()
    {
        var outputPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "optimal_weights.json");
        if (System.IO.File.Exists(outputPath))
        {
            return await System.IO.File.ReadAllTextAsync(outputPath);
        }
        return "{}";
    }

    public async Task RunComparativeEvaluationAsync(List<string> symbols, bool runInBackground = true)
    {
        var userId = CurrentUser.Id;
        if (runInBackground)
        {
            _ = Task.Run(async () => {
                await RunComparativeEvaluationInternalAsync(symbols, userId);
            });
            await Task.CompletedTask;
        }
        else
        {
            await RunComparativeEvaluationInternalAsync(symbols, userId);
        }
    }

    [AllowAnonymous]
    [RemoteService(IsEnabled = false)]
    public virtual async Task RunComparativeEvaluationInternalAsync(List<string> symbols, Guid? userId)
    {
        using (var scope = _serviceScopeFactory.CreateScope())
        {
            var scopedTradingService = scope.ServiceProvider.GetRequiredService<TradingAppService>();
            var scopedLogger = scope.ServiceProvider.GetRequiredService<ILogger<TradingAppService>>();
            var scopedHubContext = scope.ServiceProvider.GetService<IHubContext<TradingHub>>();
            var strategyRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingStrategy, Guid>>();
            var signalRepo = scope.ServiceProvider.GetRequiredService<IRepository<TradingSignal, Guid>>();

            var report = new ComparativeEvaluationReportDto { EvaluationDate = DateTime.UtcNow };
            var strategy = (await strategyRepo.GetListAsync()).FirstOrDefault();
            if (strategy == null) return;

            foreach (var symbol in symbols)
            {
                scopedLogger.LogInformation("📊 [Internal] Starting Comparative Evaluation for {Symbol}", symbol);
                var signals = await signalRepo.GetListAsync(x => x.Symbol == symbol && x.AnalyzedDate >= DateTime.UtcNow.AddDays(-30));
                
                var stylesToTest = new[] { TradingStyle.Scalping, TradingStyle.DayTrading, TradingStyle.SwingTrading };
                
                foreach (var style in stylesToTest)
                {
                    var profile = scopedTradingService.GetProfileByStyle(style);
                    
                    var baselineBacktest = await scopedTradingService.RunBacktestInternalAsync(new RunBacktestDto {
                        TradingStrategyId = strategy.Id,
                        Symbol = symbol,
                        StartDate = DateTime.UtcNow.AddDays(-30),
                        EndDate = DateTime.UtcNow,
                        WeightOverrides = new Dictionary<string, float> {
                            { "Technical", profile.TechnicalWeight },
                            { "Quantitative", profile.QuantitativeWeight },
                            { "Sentiment", profile.SentimentWeight },
                            { "Fundamental", profile.FundamentalWeight },
                            { "Whales", profile.InstitutionalWeight }
                        }
                    }, signals, userId);

                    var optimizedBacktest = await scopedTradingService.RunBacktestInternalAsync(new RunBacktestDto {
                        TradingStrategyId = strategy.Id,
                        Symbol = symbol,
                        StartDate = DateTime.UtcNow.AddDays(-30),
                        EndDate = DateTime.UtcNow
                    }, signals, userId);

                    var result = new ComparativeEvaluationResultDto {
                        Symbol = symbol,
                        TradingStyle = style.ToString(),
                        Baseline = baselineBacktest,
                        Optimized = optimizedBacktest,
                        WinRateImprovement = optimizedBacktest.WinRate - baselineBacktest.WinRate,
                        ProfitFactorImprovement = (baselineBacktest.ProfitFactor > 0) ? (optimizedBacktest.ProfitFactor / baselineBacktest.ProfitFactor) - 1 : 0,
                        SharpeRatioImprovement = (baselineBacktest.SharpeRatio > 0) ? (optimizedBacktest.SharpeRatio / baselineBacktest.SharpeRatio) - 1 : 0
                    };
                    report.Results.Add(result);
                }
            }

            var reportJson = JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true });
            var reportPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "comparative_evaluation_report.json");
            await System.IO.File.WriteAllTextAsync(reportPath, reportJson);
            
            if (scopedHubContext != null)
            {
                await scopedHubContext.Clients.All.SendAsync("ReceiveAlert", new VergeAlertDto
                {
                    Title = "Evaluación Comparativa Finalizada",
                    Message = "Se ha generado el reporte de impacto institucional.",
                    Type = "Success",
                    Severity = "success"
                });
            }
        }
    }

    public async Task<ComparativeEvaluationReportDto> GetComparativeReportAsync()
    {
        var reportPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "comparative_evaluation_report.json");
        if (System.IO.File.Exists(reportPath))
        {
            var json = await System.IO.File.ReadAllTextAsync(reportPath);
            return JsonSerializer.Deserialize<ComparativeEvaluationReportDto>(json);
        }
        return new ComparativeEvaluationReportDto();
    }

    private ITradingStyleProfile GetProfileByStyle(TradingStyle style)
    {
        return style switch
        {
            TradingStyle.Scalping => new Verge.Trading.DecisionEngine.Profiles.ScalpingProfile(),
            TradingStyle.DayTrading => new Verge.Trading.DecisionEngine.Profiles.DayTradingProfile(),
            TradingStyle.SwingTrading => new Verge.Trading.DecisionEngine.Profiles.SwingTradingProfile(),
            TradingStyle.PositionTrading => new Verge.Trading.DecisionEngine.Profiles.PositionTradingProfile(),
            TradingStyle.GridTrading => new Verge.Trading.DecisionEngine.Profiles.GridTradingProfile(),
            TradingStyle.HODL => new Verge.Trading.DecisionEngine.Profiles.HodlProfile(),
            _ => new Verge.Trading.DecisionEngine.Profiles.DefaultProfile()
        };
    }
}
