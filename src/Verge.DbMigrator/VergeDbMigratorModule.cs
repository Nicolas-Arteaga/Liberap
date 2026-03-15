using System;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
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
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        var configuration = context.Services.GetConfiguration();
        var connStr = configuration.GetConnectionString("Default");
        Console.WriteLine($"DEBUG: Connection String 'Default': '{connStr}'");
    }
}
