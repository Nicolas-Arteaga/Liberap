using System;
using System.Collections.Generic;
using System.Text.Json;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class TradingStrategy : FullAuditedAggregateRoot<Guid>
{
    public Guid TraderProfileId { get; set; }
    public string Name { get; set; } = string.Empty;
    public SignalDirection DirectionPreference { get; set; } // Long, Short, Auto
    public string SelectedCryptosJson { get; set; } = string.Empty; // Serialized list of symbols
    public int Leverage { get; set; }
    public decimal Capital { get; set; }
    public RiskTolerance RiskLevel { get; set; }
    public bool AutoStopLoss { get; set; }
    public decimal TakeProfitPercentage { get; set; }
    public decimal StopLossPercentage { get; set; }
    public bool NotificationsEnabled { get; set; }
    public bool IsActive { get; set; }
    public bool IsAutoMode { get; set; }
    public string? CustomSymbolsJson { get; set; } // Opcional: lista de símbolos cuando no es auto-full
    public TradingStyle Style { get; set; }
    public string? StyleParametersJson { get; set; }

    protected TradingStrategy() { }

    public TradingStrategy(Guid id, Guid traderProfileId, string name) : base(id)
    {
        TraderProfileId = traderProfileId;
        Name = name;
        IsActive = true;
    }

    public List<string> GetSelectedCryptos()
    {
        if (string.IsNullOrEmpty(SelectedCryptosJson)) return new List<string>();
        try { return JsonSerializer.Deserialize<List<string>>(SelectedCryptosJson) ?? new List<string>(); }
        catch { return new List<string>(); }
    }
}
