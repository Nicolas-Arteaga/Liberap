using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public interface ITradingAppService : IApplicationService
{
    // Trader Profile
    Task<TraderProfileDto> GetProfileAsync();
    Task<TraderProfileDto> UpdateProfileAsync(UpdateTraderProfileDto input);

    // Signals
    Task<PagedResultDto<TradingSignalDto>> GetSignalsAsync(GetSignalsInput input);

    // Strategies
    Task<List<TradingStrategyDto>> GetStrategiesAsync();
    Task<TradingStrategyDto> CreateStrategyAsync(CreateUpdateTradingStrategyDto input);
    Task<TradingStrategyDto> UpdateStrategyAsync(Guid id, CreateUpdateTradingStrategyDto input);
    Task DeleteStrategyAsync(Guid id);

    // Orders
    Task<TradeOrderDto> ExecuteTradeAsync(ExecuteTradeDto input);
    Task<PagedResultDto<TradeOrderDto>> GetOrderHistoryAsync(GetHistoryInput input);

    // Sessions
    Task<TradingSessionDto> StartSessionAsync(StartSessionDto input);
    Task<TradingSessionDto> GetCurrentSessionAsync();
    Task<TradingSessionDto> AdvanceStageAsync(Guid sessionId);
    Task<TradingSessionDto> FinalizeHuntAsync(Guid sessionId);
    Task<List<AnalysisLogDto>> GetAnalysisLogsAsync(Guid sessionId, int limit = 50);

    // Alerts
    Task<List<TradingAlertDto>> GetActiveAlertsAsync();
    Task<TradingAlertDto> CreateAlertAsync(CreateUpdateTradingAlertDto input);
    Task DeactivateAlertAsync(Guid id);

    // Backtesting
    Task<BacktestResultDto> RunBacktestAsync(RunBacktestDto input);
    Task OptimizeRegimeAsync(string regime, string symbol);
    Task ExecuteMassOptimizationAsync(string symbol);

    // Exchange Connections
    Task<ExchangeConnectionDto> ConnectExchangeAsync(ConnectExchangeDto input);
    Task<List<ExchangeConnectionDto>> GetConnectionsAsync();

    // Forced Proxies
    Task<MarketAnalysisDto> GetMarketAnalysisDummyAsync();
    Task<OpportunityDto> GetOpportunityDummyAsync();
    Task<VergeAlertDto> GetVergeAlertDummyAsync();

    // Recommendation
    Task<RecommendedStyleDto> RecommendTradingStyleAsync(string symbol);

    // Test SignalR manually
    Task TestSignalRAsync();
    Task TestSignalRPublicAsync();

    // Evaluation
    Task RunComparativeEvaluationAsync(List<string> symbols, bool runInBackground = true);
    Task<ComparativeEvaluationReportDto> GetComparativeReportAsync();
    
    // Exhaustive Validation
    Task RunExhaustiveValidationAsync(List<string> symbols, bool runInBackground = true);

    // Signal Analytics (Mode B)
    Task<SignalStatsDto> GetSignalStatsAsync(string? symbol = null, MarketRegimeType? regime = null);
}

public class GetSignalsInput : PagedAndSortedResultRequestDto
{
    public TradeStatus? Status { get; set; }
    public SignalConfidence? Confidence { get; set; }
}

public class GetHistoryInput : PagedAndSortedResultRequestDto
{
    public string Symbol { get; set; }
    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }
}
