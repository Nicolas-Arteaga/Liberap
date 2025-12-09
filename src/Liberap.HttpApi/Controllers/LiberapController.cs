using Liberap.Localization;
using Volo.Abp.AspNetCore.Mvc;

namespace Liberap.Controllers;

/* Inherit your controllers from this class.
 */
public abstract class LiberapController : AbpControllerBase
{
    protected LiberapController()
    {
        LocalizationResource = typeof(LiberapResource);
    }
}
