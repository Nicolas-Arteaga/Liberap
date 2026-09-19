using Volo.Abp.Settings;

namespace Verge.Settings;

public class VergeSettingDefinitionProvider : SettingDefinitionProvider
{
    public override void Define(ISettingDefinitionContext context)
    {
        //Define your own settings here. Example:
        //context.Add(new SettingDefinition(VergeSettings.MySetting1));

        // ROUND 43 -- interruptor maestro global de Trail-1. Default "false"
        // (string, como exige SettingDefinition) -- mismo valor seguro que
        // tenía en appsettings.json. IsVisibleToClients=true para poder
        // leerlo/mostrarlo desde la pantalla de administración en Angular.
        context.Add(new SettingDefinition(
            VergeSettings.TrailStopEnabled,
            defaultValue: "false",
            isVisibleToClients: true));
    }
}
