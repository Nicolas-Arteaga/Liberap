using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradingSignalDto : EntityDto<Guid>
{
    public string Symbol { get; set; }
    public SignalDirection Direction { get; set; }
    public decimal EntryPrice { get; set; }
    public SignalConfidence Confidence { get; set; }
    public decimal ProfitPotential { get; set; }
    public DateTime AnalyzedDate { get; set; }
    public TradeStatus Status { get; set; }
}

public class CreateTradingSignalDto
{
    public string Symbol { get; set; }
    public SignalDirection Direction { get; set; }
    public decimal EntryPrice { get; set; }
    public SignalConfidence Confidence { get; set; }
    public decimal ProfitPotential { get; set; }
}
