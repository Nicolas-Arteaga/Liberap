using Microsoft.Extensions.Localization;
using Verge.Localization;
using Volo.Abp.DependencyInjection;
using Volo.Abp.Ui.Branding;

namespace Verge;

[Dependency(ReplaceServices = true)]
public class VergeBrandingProvider : DefaultBrandingProvider
{
    private IStringLocalizer<VergeResource> _localizer;

    public VergeBrandingProvider(IStringLocalizer<VergeResource> localizer)
    {
        _localizer = localizer;
    }

    public override string AppName => _localizer["AppName"];
}
