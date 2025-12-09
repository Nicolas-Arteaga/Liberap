using Volo.Abp.Modularity;

namespace Liberap;

/* Inherit from this class for your domain layer tests. */
public abstract class LiberapDomainTestBase<TStartupModule> : LiberapTestBase<TStartupModule>
    where TStartupModule : IAbpModule
{

}
