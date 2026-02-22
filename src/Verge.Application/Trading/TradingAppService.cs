using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Mvc;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Users;
using Microsoft.AspNetCore.SignalR;

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
    private readonly ILogger<TradingAppService> _logger;
    private readonly IHubContext<TradingHub> _hubContext;

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
        ILogger<TradingAppService> logger,
        IHubContext<TradingHub> hubContext)
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
        _logger = logger;
        _hubContext = hubContext;
    }

    public async Task<TraderProfileDto> GetProfileAsync()
    {
        var profile = await _profileRepository.FirstOrDefaultAsync(x => x.UserId == CurrentUser.GetId());
        if (profile == null)
        {
            profile = new TraderProfile(
                GuidGenerator.Create(),
                CurrentUser.GetId(),
                CurrentUser.UserName ?? "Usuario", // Added null check
                CurrentUser.Email ?? "email@ejemplo.com", // Added null check
                TradingLevel.Beginner,
                RiskTolerance.Medium
            );
            await _profileRepository.InsertAsync(profile);
        }
        return ObjectMapper.Map<TraderProfile, TraderProfileDto>(profile);
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
        // Mock backtest logic
        var result = new BacktestResult(GuidGenerator.Create(), input.TradingStrategyId, input.Symbol)
        {
            Timeframe = input.Timeframe,
            StartDate = input.StartDate,
            EndDate = input.EndDate,
            TotalTrades = 42,
            WinningTrades = 28,
            LosingTrades = 14,
            WinRate = 66.6,
            TotalProfit = 1250.45m,
            MaxDrawdown = 8.5m,
            SharpeRatio = 1.8,
            EquityCurveJson = "[]"
        };
        await _backtestRepository.InsertAsync(result);
        return ObjectMapper.Map<BacktestResult, BacktestResultDto>(result);
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

    public Task<MarketAnalysisDto> GetMarketAnalysisDummyAsync()
    {
        throw new NotImplementedException();
    }

    public Task<OpportunityDto> GetOpportunityDummyAsync()
    {
        throw new NotImplementedException();
    }
}
