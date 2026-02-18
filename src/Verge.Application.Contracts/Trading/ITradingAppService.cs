using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;

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

    // Exchange Connections
    Task<ExchangeConnectionDto> ConnectExchangeAsync(ConnectExchangeDto input);
    Task<List<ExchangeConnectionDto>> GetConnectionsAsync();

    // Forced Proxies
    Task<MarketAnalysisDto> GetMarketAnalysisDummyAsync();
    Task<OpportunityDto> GetOpportunityDummyAsync();
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
