using Volo.Abp.Modularity;

namespace Verge;

[DependsOn(
    typeof(VergeApplicationModule),
    typeof(VergeDomainTestModule)
)]
public class VergeApplicationTestModule : AbpModule
{

}
