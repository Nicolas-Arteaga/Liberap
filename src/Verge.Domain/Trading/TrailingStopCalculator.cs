using System;

namespace Verge.Trading;

/// <summary>
/// "Trail-1" — trailing stop validado en ROUND 36/37
/// (agent/backtest/r36_exit_management.py, r37_trail1_validation.py,
/// TRAIL1_FINAL_VALIDATION_ROUND37.md): PASS sobre 2,985 trades reales,
/// mejora consistente en TRAIN/VAL/OOS, ambas mitades temporales, 11/12
/// perfiles de estrategia, ambas direcciones y los 3 regímenes de
/// volatilidad probados.
///
/// Niveles (excursión favorable desde entrada, en puntos básicos):
///   +100bp -> SL = entry (breakeven)
///   +150bp -> SL asegura +50bp
///   +200bp -> SL asegura +100bp
///
/// Función pura, sin efectos de lado ni acceso a DB/reloj — así se puede
/// testear exhaustivamente sin infraestructura y se puede llamar tanto
/// desde el worker de producción como desde el replay histórico en
/// Python (misma matemática, dos implementaciones).
/// </summary>
public static class TrailingStopCalculator
{
    public static readonly (decimal ThresholdBp, decimal LockBp)[] Levels =
    {
        (100m, 0m),
        (150m, 50m),
        (200m, 100m),
    };

    public readonly record struct Result(decimal NewSlPrice, int NewTrailLevel, bool Changed);

    /// <summary>
    /// Calcula el nuevo SL y nivel de trail dado el estado actual de un trade.
    /// - Nunca retrocede TrailLevelApplied (monotónico).
    /// - Nunca empeora SlPrice (solo lo mueve si mejora la protección).
    /// - Si la excursión favorable saltó varios umbrales entre dos
    ///   actualizaciones (ej. de +80bp a +220bp en un solo tick), aplica
    ///   directamente el nivel MÁS ALTO alcanzado -- es matemáticamente
    ///   equivalente a aplicarlos en secuencia (cada nivel superior tiene
    ///   un lockBp mayor o igual al anterior) y evita trabajo innecesario.
    /// - Idempotente: llamarla repetidamente con el mismo estado (mismo
    ///   currentTrailLevel, mismo favorableExcursionBp) no cambia nada
    ///   una vez que el nivel más alto alcanzable ya fue aplicado.
    /// </summary>
    public static Result Compute(
        bool isLong,
        decimal entryPrice,
        decimal favorableExcursionBp,
        decimal currentSlPrice,
        int currentTrailLevel)
    {
        for (int lvl = Levels.Length; lvl >= 1; lvl--)
        {
            var (thresholdBp, lockBp) = Levels[lvl - 1];
            if (favorableExcursionBp < thresholdBp || lvl <= currentTrailLevel)
            {
                continue;
            }

            var candidateSl = isLong
                ? entryPrice * (1 + lockBp / 10000m)
                : entryPrice * (1 - lockBp / 10000m);

            bool improves = isLong
                ? candidateSl > currentSlPrice
                : candidateSl < currentSlPrice;

            // Aunque el candidato no mejore el SL actual (ej. una estrategia de
            // inyección directa ya trae un SL propio más ajustado), el nivel se
            // marca igual como alcanzado -- así no se re-evalúa en cada tick
            // siguiente ni se puede "mejorar" hacia un valor peor más adelante.
            return new Result(
                NewSlPrice: improves ? candidateSl : currentSlPrice,
                NewTrailLevel: lvl,
                Changed: improves);
        }

        return new Result(currentSlPrice, currentTrailLevel, false);
    }

    /// <summary>Excursión favorable en puntos básicos desde entrada, usando el
    /// ratchet MaxFavorablePrice ya persistido (no requiere estado nuevo).</summary>
    public static decimal FavorableExcursionBp(bool isLong, decimal entryPrice, decimal maxFavorablePrice)
    {
        if (entryPrice <= 0) return 0m;
        var diff = isLong ? maxFavorablePrice - entryPrice : entryPrice - maxFavorablePrice;
        return diff / entryPrice * 10000m;
    }
}
