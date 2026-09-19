namespace Verge.Settings;

public static class VergeSettings
{
    private const string Prefix = "Verge";

    //Add your own setting names here. Example:
    //public const string MySetting1 = Prefix + ".MySetting1";

    /// <summary>
    /// ROUND 43 -- interruptor MAESTRO GLOBAL de Trail-1 (gestión de salida
    /// validada R36-R41, ver TRAIL1_FINAL_VALIDATION_ROUND37.md). Con este
    /// setting en false, ningún StrategyProfile.UseTrailStop tiene efecto
    /// (defensa en profundidad). Reemplaza la lectura de "TrailStop:Enabled"
    /// desde appsettings.json/IConfiguration -- ahora administrable desde
    /// la pantalla de Configuración de Verge sin editar archivos ni
    /// reiniciar el proceso (los settings de ABP se leen en caliente).
    /// </summary>
    public const string TrailStopEnabled = Prefix + ".TrailStop.Enabled";
}
