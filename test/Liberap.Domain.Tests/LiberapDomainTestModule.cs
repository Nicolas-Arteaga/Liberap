using Volo.Abp.Modularity;

namespace Liberap;

[DependsOn(
    typeof(LiberapDomainModule),
    typeof(LiberapTestBaseModule)
)]
public class LiberapDomainTestModule : AbpModule
{

}
