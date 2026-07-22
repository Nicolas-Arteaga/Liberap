using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

/// <summary>
/// A named set of trading parameters that the agent evaluates independently.
/// Multiple active profiles allow A/B testing strategies in parallel.
/// </summary>
public class StrategyProfile : FullAuditedAggregateRoot<Guid>
{
    public Guid UserId { get; set; }
    public string Name { get; set; } = string.Empty;
    public string Description { get; set; }
    public string Color { get; set; } = "#00C47D";
    public bool IsActive { get; set; } = true;

    // ── Entry Filters ──────────────────────────────────────────────────────
    public float MinConfluenceScore { get; set; } = 50f;
    public float MinNexusConfidence { get; set; } = 70f;
    public float MaxRsiLong { get; set; } = 80f;    // Block LONGs above this RSI
    public float MinRsiShort { get; set; } = 20f;   // Block SHORTs below this RSI
    public float MaxMa7DistancePct { get; set; } = 3.5f; // % max distance from MA7
    public bool? RequireMacdPositive { get; set; } = null; // null=any, true=positive only
    public string AllowedSources { get; set; } = "LSE,Nexus,Nexus5,Bridge"; // comma-separated
    public bool AllowLong { get; set; } = true;
    public bool AllowShort { get; set; } = true;

    // ── Risk Management ────────────────────────────────────────────────────
    public decimal MarginPerTrade { get; set; } = 150m;
    public float TpMultiplier { get; set; } = 3.0f;
    public float SlMultiplier { get; set; } = 0.8f;
    public float MinRR { get; set; } = 1.5f;
    public int MaxOpenPositions { get; set; } = 3;
    public int MaxTradeDurationCandles { get; set; } = 8;
    public bool ExtremeRsiVeto { get; set; } = true;

    // ── Advanced Execution Constraints ──────────────────────────────────────
    public float MaxEntrySlippagePct { get; set; } = 0.002f; // e.g. 0.002 = 0.2%
    public float LseMaxEntrySlippagePct { get; set; } = 0.015f; 
    public float MinTpDistancePct { get; set; } = 0.003f; // Minimum TP distance vs price
    public float MinSlDistancePct { get; set; } = 0.002f; // Minimum SL distance vs price
    public float MinEstimatedRangePct { get; set; } = 3.0f; // Minimum allowed estimated range
    public float MaxNexusSignalAgeSeconds { get; set; } = 120.0f;
    public float NexusMaxPriceDriftPct { get; set; } = 0.025f; // Max allowed drift if signal is old

    // ── Motor de patrones (genérico, sin límites de tipo) ───────────────────
    // "Generic" = filtros de arriba (Nexus/LSE/etc., como siempre).
    // "MaGeometry" = geometría de medias móviles configurable vía PatternParamsJson
    // (orden, pendiente, toque, distancia entre medias, proximidad a pico/valle, salida)
    // en vez de código Python hardcodeado por caso.
    public string StrategyType { get; set; } = "Generic";
    public string? PatternParamsJson { get; set; }

    // ── Ejecución real contra Binance ────────────────────────────────────────
    // Si es true, el agente (en modo Testnet o Mainnet) espeja cada entrada/salida
    // de esta estrategia contra Binance ademas de la simulacion interna.
    // Reemplaza el hardcodeo por id/nombre que existia antes (solo "MA Cross
    // Momentum"), ver agent/verge_agent.py.
    public bool BroadcastToBinance { get; set; } = false;

    protected StrategyProfile() { }

    public StrategyProfile(Guid id, Guid userId, string name) : base(id)
    {
        UserId = userId;
        Name = name;
    }
}
