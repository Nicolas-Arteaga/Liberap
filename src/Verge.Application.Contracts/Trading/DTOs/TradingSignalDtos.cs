using System;
using System.Collections.Generic;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading;

public class TradingSignalDto : EntityDto<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }
    public decimal EntryPrice { get; set; }
    public SignalConfidence Confidence { get; set; }
    public decimal ProfitPotential { get; set; }
    public DateTime AnalyzedDate { get; set; }
    public TradeStatus Status { get; set; }    
    public decimal? RealizedPnL { get; set; }
    public MarketRegimeType? Regime { get; set; }
}

public class CreateTradingSignalDto
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }
    public decimal EntryPrice { get; set; }
    public SignalConfidence Confidence { get; set; }
    public decimal ProfitPotential { get; set; }
}

public class VergeAlertDto
{
    public string Id { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public DateTime Timestamp { get; set; }
    public bool Read { get; set; }

    // Trading specific data
    public string? Crypto { get; set; }
    public decimal? Price { get; set; }
    public SignalConfidence? Confidence { get; set; }
    public SignalDirection? Direction { get; set; }
    public TradingStage? Stage { get; set; }
    public int? Score { get; set; }
    
    public TargetZoneDto? TargetZone { get; set; }
    
    // Institutional 1% metrics
    public double? RiskRewardRatio { get; set; }
    public double? WinProbability { get; set; }
    public int? HistoricSampleSize { get; set; }
    public string? PatternSignal { get; set; }

    // Structure (Sprint 2)
    public string? Structure { get; set; }
    public bool BosDetected { get; set; }
    public bool ChochDetected { get; set; }
    public System.Collections.Generic.List<float> LiquidityZones { get; set; } = new();

    // UI
    public string Severity { get; set; } = "info"; 
    public string Icon { get; set; } = string.Empty;
}

public class TargetZoneDto
{
    public decimal Low { get; set; }
    public decimal High { get; set; }
}

public class SignalStatsDto
{
    public string Symbol { get; set; } = string.Empty;
    public int TotalSignals { get; set; }
    public int Wins { get; set; }
    public int Losses { get; set; }
    public double WinRate { get; set; }
    public decimal TotalRealizedPnL { get; set; }
    public decimal AveragePnLPerTrade { get; set; }
    public List<SignalRegimeStatDto> ByRegime { get; set; } = new();
}

public class SignalRegimeStatDto
{
    public string Regime { get; set; } = string.Empty;
    public int Wins { get; set; }
    public int Losses { get; set; }
    public double WinRate { get; set; }
    public decimal TotalPnL { get; set; }
}
