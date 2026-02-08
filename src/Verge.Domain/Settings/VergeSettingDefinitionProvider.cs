using Volo.Abp.Settings;

namespace Verge.Settings;

public class VergeSettingDefinitionProvider : SettingDefinitionProvider
{
    public override void Define(ISettingDefinitionContext context)
    {
        //Define your own settings here. Example:
        //context.Add(new SettingDefinition(VergeSettings.MySetting1));
    }
}
