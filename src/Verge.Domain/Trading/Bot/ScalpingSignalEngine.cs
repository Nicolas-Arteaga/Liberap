using System;

namespace Verge.Trading.Bot;

/// <summary>
/// Motor de señales de scalping — COMPLETAMENTE STATELESS.
/// Recibe un ScalpingContext pre-armado y devuelve una ScalpingSignal o null.
/// Toda la lógica de entrada está concentrada aquí para facilitar testing.
/// </summary>
public class ScalpingSignalEngine
{
    /// <summary>
    /// Evalúa si hay condiciones de entrada en el contexto dado.
    /// Reglas (en orden de evaluación):
    ///   1. Macro Shield: High Volatility → BLOQUEA. Quiet Period → PERMITE.
    ///   2. Cruce MA7/MA25: el trigger principal de entrada.
    ///   3. Precio vs HMA50: filtro de dirección.
    ///   4. Scanner Score ≥ MinScore: filtro de calidad.
    ///   5. [Opcional] MA25 vs MA99: confirmación de tendencia mayor (si config lo requiere).
    ///   6. Calcula SL dinámico por ATR, leverage dinámico por volatilidad, TP1 y TP2.
    /// 
    /// Retorna null si no hay señal válida.
    /// </summary>
    public ScalpingSignal? Evaluate(ScalpingContext ctx)
    {
        // ─── GUARD 1: HIGH VOLATILITY bloquea el bot ───
        // Quiet Period NO bloquea — es buen momento para scalping (menor spread, menor ruido)
        if (ctx.IsHighVolatility)
        {
            return null; // 🔴 Macro Shield activo
        }

        // ─── GUARD 2: Necesitamos datos mínimos ───
        if (ctx.Price <= 0 || ctx.ATR <= 0 || ctx.VirtualBalance <= 0)
        {
            return null;
        }

        // ─── EVALUACIÓN DE SESGO DE DIRECCIÓN ───
        // El bias NO es obligatorio pero sí preferido.
        // El cruce MA7/MA25 es el trigger principal.
        // El precio vs HMA50 es el filtro direccional hard.
        bool longPressure  = ctx.Price > ctx.HMA50;  // Precio por encima = zona alcista
        bool shortPressure = ctx.Price < ctx.HMA50;  // Precio por debajo = zona bajista

        // Filtro adicional de tendencia mayor (solo si la config lo requiere)
        bool trendConfirmLong  = !ctx.Config.RequireTrendConfirmation || ctx.MA25 > ctx.MA99;
        bool trendConfirmShort = !ctx.Config.RequireTrendConfirmation || ctx.MA25 < ctx.MA99;

        // ─── TRIGGER: CRUCE DE MAs (O CONTINUACIÓN DE TENDENCIA FUERTE) ───
        bool longCross  = IndicatorCalculator.CrossedAbove(ctx.PrevMA7, ctx.PrevMA25, ctx.MA7, ctx.MA25);
        bool shortCross = IndicatorCalculator.CrossedBelow(ctx.PrevMA7, ctx.PrevMA25, ctx.MA7, ctx.MA25);

        // Agresivo: Si ya cruzó y la tendencia se mantiene, permitimos entrada si el score es alto
        bool longTrend  = ctx.MA7 > ctx.MA25;
        bool shortTrend = ctx.MA7 < ctx.MA25;

        // ─── FILTRO DE SCORE ───
        bool scoreOk = ctx.ScannerScore >= ctx.Config.MinScore;

        // ─── CONDICIÓN FINAL ───
        // Si el scanner nos da una dirección, la respetamos a rajatabla.
        // 0 = Long, 1 = Short, 2 = Auto (ambas)
        bool canLong  = ctx.ScannerDirection == 0 || ctx.ScannerDirection == 2;
        bool canShort = ctx.ScannerDirection == 1 || ctx.ScannerDirection == 2;

        bool longEntry  = canLong  && (longCross || longTrend)   && longPressure  && trendConfirmLong  && scoreOk;
        bool shortEntry = canShort && (shortCross || shortTrend) && shortPressure && trendConfirmShort && scoreOk;

        if (!longEntry && !shortEntry) return null;

        // ─── DIRECCIÓN FINAL ───
        SignalDirection direction = longEntry ? SignalDirection.Long : SignalDirection.Short;

        // ─── CÁLCULO DE STOP LOSS (ATR-based) ───
        // SL distance = ATR * factor, clamp entre 0.6% y 1.5% del precio
        decimal atrPct = ctx.ATR / ctx.Price;
        decimal slPct   = Math.Clamp(atrPct, 0.006m, 0.015m); // 0.6% – 1.5%
        decimal slDist  = ctx.Price * slPct;

        decimal sl = direction == SignalDirection.Long
            ? ctx.Price - slDist
            : ctx.Price + slDist;

        // ─── TAKE PROFIT ───
        decimal tp1Dist = slDist * ctx.Config.PartialCloseRR;   // RR 1.5 default
        decimal tp2Dist = slDist * ctx.Config.FinalTpRR;        // RR 2.5 default

        decimal tp1 = direction == SignalDirection.Long
            ? ctx.Price + tp1Dist
            : ctx.Price - tp1Dist;

        decimal tp2 = direction == SignalDirection.Long
            ? ctx.Price + tp2Dist
            : ctx.Price - tp2Dist;

        // ─── LEVERAGE DINÁMICO ───
        int leverage = IndicatorCalculator.CalculateDynamicLeverage(
            ctx.ATR,
            ctx.Price,
            ctx.Config.MinLeverage,
            ctx.Config.MaxLeverage
        );

        // ─── TAMAÑO DE POSICIÓN ───
        // Riesgo 1% del balance: riskAmount = balance × riskPct
        // Margin (collateral) = riskAmount / slPct
        // Notional (exposición) = margin × leverage
        // PositionSize (coins) = notional / precio
        decimal riskAmount   = ctx.VirtualBalance * (ctx.Config.RiskPercent / 100m);
        decimal margin       = riskAmount / slPct;
        decimal notional     = margin * leverage;
        decimal positionSize = notional / ctx.Price;

        // ─── BIAS SUMMARY (para logs y Telegram) ───
        string biasSummary = direction == SignalDirection.Long
            ? $"LONG | Precio {(longPressure ? ">" : "~")} HMA50 | MA7 cruzó ↑ MA25 | Score {ctx.ScannerScore}"
            : $"SHORT | Precio {(shortPressure ? "<" : "~")} HMA50 | MA7 cruzó ↓ MA25 | Score {ctx.ScannerScore}";

        return new ScalpingSignal
        {
            Symbol        = ctx.Symbol,
            Direction     = direction,
            EntryPrice    = ctx.Price,
            StopLoss      = sl,
            TakeProfit1   = tp1,
            TakeProfit2   = tp2,
            Leverage      = leverage,
            Margin        = Math.Round(margin, 4),
            Notional      = Math.Round(notional, 4),
            PositionSize  = Math.Round(positionSize, 6),
            ATR           = ctx.ATR,
            ATRPercent    = Math.Round(atrPct * 100m, 3),
            SLPercent     = Math.Round(slPct * 100m, 3),
            TP1Percent    = Math.Round(tp1Dist / ctx.Price * 100m, 3),
            TP2Percent    = Math.Round(tp2Dist / ctx.Price * 100m, 3),
            ScannerScore  = ctx.ScannerScore,
            BiasSummary   = biasSummary,
            GeneratedAt   = DateTime.UtcNow
        };
    }
}
