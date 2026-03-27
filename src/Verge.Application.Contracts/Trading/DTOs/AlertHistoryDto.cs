using System;
using Volo.Abp.Application.Dtos;

namespace Verge.Trading.DTOs;

public class AlertHistoryDto : FullAuditedEntityDto<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public string Style { get; set; } = string.Empty;
    public int Direction { get; set; }
    public decimal EntryPrice { get; set; }
    public decimal TargetPrice { get; set; }
    public decimal StopLossPrice { get; set; }
    public int Confidence { get; set; }
    public int EstimatedTimeMinutes { get; set; }
    public decimal ExpectedDrawdownPct { get; set; }
    public string ReasoningJson { get; set; } = "{}";
    public string RawDataJson { get; set; } = "{}";
    public DateTime EmittedAt { get; set; }
    public DateTime ExpiresAt { get; set; }
    public string Status { get; set; } = "Pending";
    public decimal? ActualExitPrice { get; set; }
    public decimal? ActualPnlPct { get; set; }
    public int? TimeToResolutionMinutes { get; set; }
    public string AlertTier { get; set; } = "Normal";
    public string AlertType { get; set; } = "Scanner";
    public bool IsRead { get; set; } = false;

    // Derived properties for UI
    public string DirectionName => Direction == 0 ? "Long" : (Direction == 1 ? "Short" : "Auto");
    public string TierDisplayName => GetTierDisplayName(AlertTier);

    private string GetTierDisplayName(string tier) => tier switch
    {
        "EjecucionTotal" => "💀 Ejecución Total",
        "GolpeLetal" => "⚡ Golpe Letal",
        "CaceriaAbierta" => "🎯 Cacería Abierta",
        "SangreEnElAgua" => "🩸 Sangre en el Agua",
        _ => "📊 Scanner"
    };
}
