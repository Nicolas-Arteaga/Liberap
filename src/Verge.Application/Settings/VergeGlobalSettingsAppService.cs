using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Volo.Abp.SettingManagement;

namespace Verge.Settings;

/// <summary>
/// ROUND 43 -- lee/escribe el setting global ABP "Verge.TrailStop.Enabled"
/// (ver VergeSettings.cs / VergeSettingDefinitionProvider.cs) usando
/// ISettingManager en scope Global (no por usuario/tenant): es el mismo
/// interruptor para todo el sistema, coherente con como lo lee
/// SimulationMarkPriceWorker vía ISettingProvider.
/// </summary>
public class VergeGlobalSettingsAppService : ApplicationService, IVergeGlobalSettingsAppService
{
    private readonly ISettingManager _settingManager;

    public VergeGlobalSettingsAppService(ISettingManager settingManager)
    {
        _settingManager = settingManager;
    }

    public async Task<TrailStopGlobalSettingDto> GetTrailStopSettingAsync()
    {
        var value = await _settingManager.GetOrNullGlobalAsync(VergeSettings.TrailStopEnabled);
        return new TrailStopGlobalSettingDto { Enabled = value == "true" };
    }

    public async Task<TrailStopGlobalSettingDto> SetTrailStopSettingAsync(TrailStopGlobalSettingDto input)
    {
        await _settingManager.SetGlobalAsync(VergeSettings.TrailStopEnabled, input.Enabled ? "true" : "false");
        return input;
    }
}
