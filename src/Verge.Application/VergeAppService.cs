using Verge.Localization;
using Volo.Abp.Application.Services;

namespace Verge;

/* Inherit your application services from this class.
 */
public abstract class VergeAppService : ApplicationService
{
    protected VergeAppService()
    {
        LocalizationResource = typeof(VergeResource);
    }
}
