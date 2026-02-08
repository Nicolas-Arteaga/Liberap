using Verge.EntityFrameworkCore;
using Volo.Abp.Autofac;
using Volo.Abp.Modularity;

namespace Verge.DbMigrator;

[DependsOn(
    typeof(AbpAutofacModule),
    typeof(VergeEntityFrameworkCoreModule),
    typeof(VergeApplicationContractsModule)
)]
public class VergeDbMigratorModule : AbpModule
{
}
