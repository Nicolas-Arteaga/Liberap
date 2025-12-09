using Microsoft.Extensions.Localization;
using Liberap.Localization;
using Volo.Abp.DependencyInjection;
using Volo.Abp.Ui.Branding;

namespace Liberap;

[Dependency(ReplaceServices = true)]
public class LiberapBrandingProvider : DefaultBrandingProvider
{
    private IStringLocalizer<LiberapResource> _localizer;

    public LiberapBrandingProvider(IStringLocalizer<LiberapResource> localizer)
    {
        _localizer = localizer;
    }

    public override string AppName => _localizer["AppName"];
}
