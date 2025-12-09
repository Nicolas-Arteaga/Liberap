using Volo.Abp.Modularity;

namespace Liberap;

[DependsOn(
    typeof(LiberapApplicationModule),
    typeof(LiberapDomainTestModule)
)]
public class LiberapApplicationTestModule : AbpModule
{

}
