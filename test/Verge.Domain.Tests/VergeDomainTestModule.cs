using Volo.Abp.Modularity;

namespace Verge;

[DependsOn(
    typeof(VergeDomainModule),
    typeof(VergeTestBaseModule)
)]
public class VergeDomainTestModule : AbpModule
{

}
