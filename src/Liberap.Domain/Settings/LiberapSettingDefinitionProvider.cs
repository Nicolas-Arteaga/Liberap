using Volo.Abp.Settings;

namespace Liberap.Settings;

public class LiberapSettingDefinitionProvider : SettingDefinitionProvider
{
    public override void Define(ISettingDefinitionContext context)
    {
        //Define your own settings here. Example:
        //context.Add(new SettingDefinition(LiberapSettings.MySetting1));
    }
}
