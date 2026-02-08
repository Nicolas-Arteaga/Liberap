using AutoMapper;
using Verge.Trading;

namespace Verge;

public class VergeApplicationAutoMapperProfile : Profile
{
    public VergeApplicationAutoMapperProfile()
    {
        CreateMap<TraderProfile, TraderProfileDto>();
        CreateMap<TradingSignal, TradingSignalDto>();
        CreateMap<TradingStrategy, TradingStrategyDto>();
        CreateMap<TradeOrder, TradeOrderDto>();
        CreateMap<TradingSession, TradingSessionDto>();
        CreateMap<TradingAlert, TradingAlertDto>();
        CreateMap<BacktestResult, BacktestResultDto>();
        CreateMap<ExchangeConnection, ExchangeConnectionDto>();
        
        CreateMap<CreateUpdateTradingStrategyDto, TradingStrategy>();
        CreateMap<CreateUpdateTradingAlertDto, TradingAlert>();
    }
}
