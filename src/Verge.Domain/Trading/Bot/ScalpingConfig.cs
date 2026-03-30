using System.Collections.Generic;

namespace Verge.Trading.Bot;

/// <summary>
/// Configuración completa del bot de scalping agresivo.
/// Se bindea desde appsettings.json sección "ScalpingBot".
/// Todos los valores son configurables desde el panel Angular en tiempo real.
/// </summary>
public class ScalpingConfig
{
    /// <summary>Activa/desactiva el bot. Por defecto false (manual).</summary>
    public bool Enabled { get; set; } = false;

    /// <summary>Timeframe principal en minutos. Default: 5m.</summary>
    public string Timeframe { get; set; } = "5";

    /// <summary>Si true, el bot toma el top N del scanner en cada ciclo.</summary>
    public bool DynamicSymbols { get; set; } = true;

    /// <summary>Cuántos símbolos del top tomar dinámicamente.</summary>
    public int TopSymbolsCount { get; set; } = 10;

    /// <summary>
    /// Whitelist fija adicional. Estos símbolos siempre se monitorean.
    /// También sirve para excluir mencionando explícitamente los que querés.
    /// </summary>
    public List<string> WhitelistSymbols { get; set; } = new() { "BTCUSDT", "ETHUSDT", "SOLUSDT" };

    /// <summary>Símbolos a excluir absolutamente (memes tóxicos, etc.).</summary>
    public List<string> BlacklistSymbols { get; set; } = new();

    /// <summary>Riesgo máximo por trade expresado como % del balance virtual.</summary>
    public decimal RiskPercent { get; set; } = 1.0m;

    /// <summary>Score mínimo del scanner para generar señal.</summary>
    public int MinScore { get; set; } = 70;

    /// <summary>Máximo de posiciones del bot abiertas simultáneamente.</summary>
    public int MaxOpenPositions { get; set; } = 5;

    /// <summary>Leverage mínimo (mercados con alta volatilidad).</summary>
    public int MinLeverage { get; set; } = 8;

    /// <summary>Leverage máximo (mercados tranquilos).</summary>
    public int MaxLeverage { get; set; } = 20;

    /// <summary>RR donde se cierra el 50% de la posición (cierre parcial).</summary>
    public decimal PartialCloseRR { get; set; } = 1.5m;

    /// <summary>RR del Take Profit final (trailing se activa antes de esto).</summary>
    public decimal FinalTpRR { get; set; } = 2.5m;

    /// <summary>
    /// Si true, el bot puede operar durante Quiet Period (noticias próximas).
    /// SOLO bloquea en High Volatility.
    /// </summary>
    public bool AllowQuietPeriodTrading { get; set; } = true;

    /// <summary>
    /// Si true, requiere que MA25 > MA99 para LONG (filtro de tendencia fuerte).
    /// Si false, basta con precio vs HMA50 + cruce MA7/MA25 + Score alto.
    /// Por defecto false para ser más agresivo.
    /// </summary>
    public bool RequireTrendConfirmation { get; set; } = false;

    /// <summary>Nombre descriptivo del bot visible en el panel.</summary>
    public string BotName { get; set; } = "VERGE Scalper 5m";
}
