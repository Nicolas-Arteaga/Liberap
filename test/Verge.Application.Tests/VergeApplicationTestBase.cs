using Volo.Abp.Modularity;

namespace Verge;

public abstract class VergeApplicationTestBase<TStartupModule> : VergeTestBase<TStartupModule>
    where TStartupModule : IAbpModule
{

}
