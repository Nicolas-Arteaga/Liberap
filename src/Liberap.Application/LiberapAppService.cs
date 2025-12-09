using Liberap.Localization;
using Volo.Abp.Application.Services;

namespace Liberap;

/* Inherit your application services from this class.
 */
public abstract class LiberapAppService : ApplicationService
{
    protected LiberapAppService()
    {
        LocalizationResource = typeof(LiberapResource);
    }
}
