using Liberap.EntityFrameworkCore;
using Volo.Abp.Autofac;
using Volo.Abp.Modularity;

namespace Liberap.DbMigrator;

[DependsOn(
    typeof(AbpAutofacModule),
    typeof(LiberapEntityFrameworkCoreModule),
    typeof(LiberapApplicationContractsModule)
)]
public class LiberapDbMigratorModule : AbpModule
{
}
