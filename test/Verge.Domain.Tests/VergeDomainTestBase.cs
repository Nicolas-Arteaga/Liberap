using Volo.Abp.Modularity;

namespace Verge;

/* Inherit from this class for your domain layer tests. */
public abstract class VergeDomainTestBase<TStartupModule> : VergeTestBase<TStartupModule>
    where TStartupModule : IAbpModule
{

}
