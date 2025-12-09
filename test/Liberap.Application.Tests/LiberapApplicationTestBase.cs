using Volo.Abp.Modularity;

namespace Liberap;

public abstract class LiberapApplicationTestBase<TStartupModule> : LiberapTestBase<TStartupModule>
    where TStartupModule : IAbpModule
{

}
