using System;
using Volo.Abp.Domain.Entities.Auditing;

namespace Verge.Trading;

public class SimulatedTrade : FullAuditedAggregateRoot<Guid>
{
    public Guid UserId { get; set; }
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Side { get; set; }
    public int Leverage { get; set; }
    public decimal Size { get; set; } // Quantity in base currency (e.g. BTC)
    public decimal Amount { get; set; } // Quantity in quote currency (e.g. USDT)
    
    public decimal EntryPrice { get; set; }
    public decimal MarkPrice { get; set; }
    public decimal LiquidationPrice { get; set; }
    public decimal Margin { get; set; } // Initial Margin
    public decimal MarginRate { get; set; }
    
    public decimal UnrealizedPnl { get; set; }
    public decimal ROIPercentage { get; set; }
    public TradeStatus Status { get; set; }
    
    public decimal? ClosePrice { get; set; }
    public decimal? RealizedPnl { get; set; }
    
    public decimal? TpPrice { get; set; }
    public decimal? SlPrice { get; set; }
    
    public decimal EntryFee { get; set; }
    public decimal ExitFee { get; set; }
    public decimal TotalFundingPaid { get; set; }
    
    public DateTime OpenedAt { get; set; }
    public DateTime? ClosedAt { get; set; }
    
    public Guid? TradingSignalId { get; set; }

    /// <summary>
    /// Exchange where this trade was opened. Used by the worker to ensure
    /// price evaluation always uses the same exchange, preventing phantom closes
    /// caused by cross-exchange price discrepancies.
    /// Default: "Binance"
    /// </summary>
    public string Exchange { get; set; } = "Binance";

    /// <summary>
    /// JSON snapshot of Nexus-15 / SCAR / LSE / sizing at open time (Python agent).
    /// Null for manually opened simulated trades.
    /// </summary>
    public string? AgentDecisionJson { get; set; }

    /// <summary>
    /// The farthest adverse price reached during the trade.
    /// For LONG: the lowest price seen. For SHORT: the highest price seen.
    /// Null if tracking wasn't available (legacy trades).
    /// </summary>
    public decimal? MaxAdversePrice { get; set; }

    /// <summary>
    /// The farthest favorable price reached during the trade.
    /// For LONG: the highest price seen. For SHORT: the lowest price seen.
    /// Null if tracking wasn't available (legacy trades).
    /// </summary>
    public decimal? MaxFavorablePrice { get; set; }

    /// <summary>
    /// Why the trade was closed: "tp_hit", "sl_hit", "btc_dump", "timeout", "manual", "trailing_stop", "regime_change"
    /// </summary>
    public string? ExitReason { get; set; }

    /// <summary>
    /// Distance from entry price to MA7 at entry time (percentage).
    /// Example: 0.8 means price was 0.8% away from MA7 when entering.
    /// Used for Sniper filter validation.
    /// </summary>
    public decimal? Ma7DistancePctAtEntry { get; set; }

    /// <summary>
    /// BTC price at the moment this trade was closed.
    /// Used for BTC correlation analysis.
    /// </summary>
    public decimal? BtcPriceAtClose { get; set; }

    /// <summary>
    /// Full exit audit JSON block (v12.1): MAE%, MFE%, candles_held, BTC context at exit, etc.
    /// Populated by the Python agent via update-exit-info endpoint.
    /// </summary>
    public string? ExitAuditJson { get; set; }

    /// <summary>
    /// Etiqueta manual para excluir un trade puntual de las estadísticas
    /// agregadas (GetPerformanceStatsAsync) sin borrarlo — el trade sigue
    /// visible en el Historial para auditoría, solo no cuenta para el
    /// Win Rate/Ganancia Total/Avg. Null = cuenta normal.
    /// </summary>
    public string? ExclusionTag { get; set; }

    /// <summary>
    /// Links this trade to the StrategyProfile that generated it.
    /// Null for trades opened before multi-strategy was implemented.
    /// </summary>
    public Guid? StrategyProfileId { get; set; }

    /// <summary>
    /// Live progress toward TP as of the last mark price update, as a percentage of the
    /// entry-to-TP distance. 0 = at entry, 100 = at TP. Can go negative (moving toward SL)
    /// or exceed 100 (price ran past TP before the closing tick landed).
    /// Null when TpPrice isn't set. Computed server-side by SimulationMarkPriceWorker.
    /// </summary>
    public decimal? TpProgressPct { get; set; }

    /// <summary>
    /// The highest TpProgressPct ever reached during the trade's life (derived from
    /// MaxFavorablePrice). Answers "how close did this get to TP before reversing".
    /// Persists after close. Null when TpPrice isn't set.
    /// </summary>
    public decimal? MaxTpProgressPct { get; set; }

    /// <summary>
    /// The highest percentage of the entry-to-SL distance ever covered during the trade's
    /// life (derived from MaxAdversePrice). Answers "how close did this get to blowing the stop".
    /// Persists after close. Null when SlPrice isn't set.
    /// </summary>
    public decimal? MaxSlProgressPct { get; set; }

    /// <summary>
    /// 2026-08-18: true una vez que el SL de este trade fue movido a breakeven
    /// (entry + fees) porque llegó a BreakevenLockTpProgressPct de progreso hacia
    /// el TP (ver SimulationMarkPriceWorker). Evidencia real que motivó esto: en
    /// 45 días, 140 trades llegaron a ≥70% del camino al TP y terminaron en
    /// pérdida total (sl_hit/timeout) sin nada que rescate esa ganancia ya
    /// alcanzada -- $227 dejados en la mesa. Distinto de "Cosecha Inteligente"
    /// (trailing continuo, removido 2026-07-15): esto NUNCA mueve el SL antes de
    /// ese umbral y nunca mueve el TP -- solo evita que un trade ya ganado
    /// termine en rojo total.
    /// </summary>
    public bool BreakevenLocked { get; set; } = false;

    /// <summary>
    /// ROUND 36/37 (research/agent/backtest/r36_exit_management.py,
    /// r37_trail1_validation.py) — nivel de trailing stop "Trail-1" ya
    /// aplicado a este trade: 0 = ninguno, 1 = +100bp (SL a breakeven),
    /// 2 = +150bp (SL asegura +50bp), 3 = +200bp (SL asegura +100bp).
    /// Monotónico (nunca retrocede) e idempotente (TrailingStopCalculator
    /// solo actúa si el nivel objetivo es mayor a este valor). Persistido
    /// en DB, no en memoria del proceso -- sobrevive reinicios sin estado
    /// adicional. DESACTIVADO en producción (ver
    /// SimulationMarkPriceWorker.TrailStopEnabled) hasta decisión
    /// explícita del usuario tras el replay de ROUND 38.
    /// </summary>
    public int TrailLevelApplied { get; set; } = 0;

    /// <summary>
    /// ROUND 40 (canary) — null hasta que el worker evalúa este trade por
    /// primera vez con el feature activo; a partir de ahí, fijo para
    /// siempre (asignación determinística por Id, ver
    /// SimulationMarkPriceWorker.IsCanaryAssigned). true = este trade
    /// recibe gestión Trail-1 en vivo (grupo canary); false = se
    /// gestiona exactamente como hoy, sin trailing (grupo control),
    /// para poder comparar resultados reales sin abrir trades
    /// duplicados. No se re-evalúa nunca una vez asignado.
    /// </summary>
    public bool? TrailStopCanary { get; set; }

    /// <summary>
    /// ROUND 40 (canary) — copia del SlPrice ORIGINAL (antes de que
    /// cualquier movimiento de Trail-1 lo modifique), capturada la
    /// primera vez que este trade entra al grupo canary. Necesaria para
    /// poder reconstruir post-hoc "qué hubiera pasado sin Trail-1" sobre
    /// un trade cuyo SlPrice en vivo sí cambió -- sin esto se pierde el
    /// dato para el contrafactual (Parte 6 del brief).
    /// </summary>
    public decimal? OriginalSlPrice { get; set; }

    /// <summary>
    /// ROUND 40 (canary) — bitácora de auditoría de Trail-1, JSON array
    /// acotado (máximo 3 entradas, una por nivel: 100/150/200bp). Cada
    /// entrada: {level, ts, favBp, oldSl, newSl, changed}. Se escribe
    /// SOLO en los eventos relevantes (cruce de umbral), nunca por tick
    /// — así se puede auditar cada movimiento del stop sin loggear cada
    /// segundo. Null si el trade nunca entró al grupo canary o nunca
    /// cruzó ningún umbral.
    /// </summary>
    public string? TrailAuditJson { get; set; }

    protected SimulatedTrade() { }

    public SimulatedTrade(
        Guid id, 
        Guid userId, 
        string symbol, 
        SignalDirection side, 
        int leverage, 
        decimal entryPrice, 
        decimal size, 
        decimal amount,
        decimal margin,
        decimal liquidationPrice,
        decimal entryFee,
        decimal? tpPrice = null,
        decimal? slPrice = null,
        Guid? tradingSignalId = null,
        string exchange = "Binance") : base(id)
    {
        UserId = userId;
        Symbol = symbol;
        Side = side;
        Leverage = leverage;
        EntryPrice = entryPrice;
        MarkPrice = entryPrice;
        Size = size;
        Amount = amount;
        Margin = margin;
        LiquidationPrice = liquidationPrice;
        EntryFee = entryFee;
        TpPrice = tpPrice;
        SlPrice = slPrice;
        TradingSignalId = tradingSignalId;
        Exchange = exchange;
        Status = TradeStatus.Open;
        OpenedAt = DateTime.UtcNow;
        UnrealizedPnl = 0;
        ROIPercentage = 0;
        MarginRate = 0;
    }
}
