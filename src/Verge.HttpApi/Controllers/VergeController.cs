using Verge.Localization;
using Volo.Abp.AspNetCore.Mvc;

namespace Verge.Controllers;

/* Inherit your controllers from this class.
 */
public abstract class VergeController : AbpControllerBase
{
    protected VergeController()
    {
        LocalizationResource = typeof(VergeResource);
    }
}
