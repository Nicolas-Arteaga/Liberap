using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Settings;

/// <summary>
/// ROUND 43 -- expone el interruptor maestro global de Trail-1
/// (Verge.TrailStop.Enabled) para que sea administrable desde la UI de
/// Verge, sin editar appsettings.json ni reiniciar el proceso. No es un
/// AppService de settings genérico: solo cubre este switch puntual,
/// siguiendo el mismo alcance acotado que el resto de los endpoints de
/// Verge (nada de infraestructura de configuración genérica sin uso real).
/// </summary>
public interface IVergeGlobalSettingsAppService : IApplicationService
{
    Task<TrailStopGlobalSettingDto> GetTrailStopSettingAsync();

    Task<TrailStopGlobalSettingDto> SetTrailStopSettingAsync(TrailStopGlobalSettingDto input);
}
