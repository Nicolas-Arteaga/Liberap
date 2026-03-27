using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class AlertHistory : FullAuditedAggregateRoot<Guid>
{
    public string Symbol { get; set; } = string.Empty;
    public string Style { get; set; } = string.Empty; // Scalping, DayTrading, Swing, PositionTrading
    public int Direction { get; set; } // 0=Long, 1=Short, 2=Auto
    public decimal EntryPrice { get; set; }
    public decimal TargetPrice { get; set; }
    public decimal StopLossPrice { get; set; }
    public int Confidence { get; set; } // 0-100
    public int EstimatedTimeMinutes { get; set; } // Tiempo estimado hasta TP
    public decimal ExpectedDrawdownPct { get; set; } // Drawdown esperado antes del TP (ej: 1.2)
    public string ReasoningJson { get; set; } = "{}"; // Opinión de cada agente IA
    public string RawDataJson { get; set; } = "{}"; // Payload completo
    public DateTime EmittedAt { get; set; } // Momento de emisión
    public DateTime ExpiresAt { get; set; } // Validez estimada
    public string Status { get; set; } = "Pending"; // Pending, Hit, Failed, Expired
    public decimal? ActualExitPrice { get; set; }
    public decimal? ActualPnlPct { get; set; }
    public int? TimeToResolutionMinutes { get; set; }
    public string AlertTier { get; set; } = "Normal"; // Normal, SangreEnElAgua, CaceriaAbierta, GolpeLetal, EjecucionTotal
    public string AlertType { get; set; } = "Scanner"; // Scanner, Opportunity, Whale, Liquidation
    public bool IsRead { get; set; } = false;
    protected AlertHistory() { }

    public AlertHistory(
        Guid id,
        string symbol,
        string style,
        int direction,
        decimal entryPrice,
        decimal targetPrice,
        decimal stopLossPrice,
        int confidence,
        int estimatedTimeMinutes,
        decimal expectedDrawdownPct,
        string reasoningJson,
        string rawDataJson,
        DateTime emittedAt,
        DateTime expiresAt,
        string alertTier,
        string alertType = "Scanner",
        bool isRead = false
    ) : base(id)
    {
        Symbol = symbol;
        Style = style;
        Direction = direction;
        EntryPrice = entryPrice;
        TargetPrice = targetPrice;
        StopLossPrice = stopLossPrice;
        Confidence = confidence;
        EstimatedTimeMinutes = estimatedTimeMinutes;
        ExpectedDrawdownPct = expectedDrawdownPct;
        ReasoningJson = reasoningJson;
        RawDataJson = rawDataJson;
        EmittedAt = emittedAt;
        ExpiresAt = expiresAt;
        AlertTier = alertTier;
        AlertType = alertType;
        IsRead = isRead;
    }

    /// <summary>
    /// Computes the AlertTier based on confidence score.
    /// </summary>
    public static string ComputeTier(int confidence) => confidence switch
    {
        >= 100 => "EjecucionTotal",
        >= 90 => "GolpeLetal",
        >= 80 => "CaceriaAbierta",
        >= 70 => "SangreEnElAgua",
        _ => "Normal"
    };

    /// <summary>
    /// Returns the display name with emoji for the tier.
    /// </summary>
    public static string GetTierDisplayName(string tier) => tier switch
    {
        "EjecucionTotal" => "💀 Ejecución Total",
        "GolpeLetal" => "⚡ Golpe Letal",
        "CaceriaAbierta" => "🎯 Cacería Abierta",
        "SangreEnElAgua" => "🩸 Sangre en el Agua",
        _ => "📊 Scanner"
    };

    /// <summary>
    /// Computes estimated time in minutes and expected drawdown % based on trading style.
    /// </summary>
    public static (int estimatedMinutes, decimal drawdownPct) GetStyleEstimates(string style) => style?.ToLower() switch
    {
        "scalping" => (22, 0.4m),        // ~15-30 min, ~0.3-0.5%
        "daytrading" => (150, 1.2m),      // ~1-4 hours, ~1.0-1.5%
        "swing" => (720, 2.5m),           // ~4-24 hours, ~2.0-3.0%
        "positiontrading" => (2880, 4.0m), // ~1-7 days, ~3.0-5.0%
        _ => (150, 1.2m) // Default to DayTrading
    };
}
