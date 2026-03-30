using System;
using System.Collections.Generic;
using Verge.Trading.DecisionEngine;

namespace Verge.Trading.Bot;

/// <summary>
/// Contexto de mercado pre-calculado para una evaluación de señal.
/// El ScalpingBotService arma este objeto con todos los datos necesarios
/// y lo pasa al ScalpingSignalEngine que es completamente stateless.
/// </summary>
public class ScalpingContext
{
    public string Symbol { get; set; } = string.Empty;
    public decimal Price { get; set; }       // Último precio (WebSocket)

    // Indicadores calculados por IndicatorCalculator
    public decimal HMA50 { get; set; }
    public decimal MA7 { get; set; }
    public decimal MA25 { get; set; }
    public decimal MA99 { get; set; }
    public decimal ATR { get; set; }

    // Valores de la vela anterior (para detectar cruces)
    public decimal PrevMA7 { get; set; }
    public decimal PrevMA25 { get; set; }

    // Score del scanner (leído desde DB/Redis — no recalculado)
    public int ScannerScore { get; set; }
    public int ScannerDirection { get; set; } // 0=Long, 1=Short

    // Macro Shield
    public bool IsHighVolatility { get; set; }   // Bloquea al bot
    public bool IsQuietPeriod { get; set; }       // NO bloquea — el bot opera

    // Whale confluence (opcional — suma confianza)
    public double WhaleNetFlowScore { get; set; } // -1.0 a 1.0

    // Balance virtual para calcular tamaño de posición
    public decimal VirtualBalance { get; set; }

    // Configuración activa en este ciclo
    public ScalpingConfig Config { get; set; } = new();

    // Velas completas (para recalcular HMA50 en trailing monitor)
    public List<MarketCandleModel> Candles { get; set; } = new();
}

/// <summary>
/// Resultado de una evaluación exitosa del ScalpingSignalEngine.
/// Contiene todo lo necesario para abrir la posición.
/// </summary>
public class ScalpingSignal
{
    public string Symbol { get; set; } = string.Empty;
    public SignalDirection Direction { get; set; }

    // Precios exactos
    public decimal EntryPrice { get; set; }
    public decimal StopLoss { get; set; }
    public decimal TakeProfit1 { get; set; }   // 50% cierre parcial en RR 1.5
    public decimal TakeProfit2 { get; set; }   // Resto con trailing

    // Parámetros de posición
    public int Leverage { get; set; }
    public decimal Margin { get; set; }        // USDT a poner como collateral
    public decimal Notional { get; set; }      // Exposición total = Margin * Leverage
    public decimal PositionSize { get; set; }  // Cantidad en base asset (BTC, ETH, etc.)

    // Metadata para auditoría y backtesting
    public decimal ATR { get; set; }
    public decimal ATRPercent { get; set; }
    public decimal SLPercent { get; set; }
    public decimal TP1Percent { get; set; }
    public decimal TP2Percent { get; set; }
    public int ScannerScore { get; set; }
    public string BiasSummary { get; set; } = string.Empty;  // "Alcista — precio>HMA50 + cruce MA7/MA25"
    public DateTime GeneratedAt { get; set; } = DateTime.UtcNow;
}
