using System;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Liberap.Data;
using Volo.Abp.DependencyInjection;

namespace Liberap.EntityFrameworkCore;

public class EntityFrameworkCoreLiberapDbSchemaMigrator
    : ILiberapDbSchemaMigrator, ITransientDependency
{
    private readonly IServiceProvider _serviceProvider;

    public EntityFrameworkCoreLiberapDbSchemaMigrator(IServiceProvider serviceProvider)
    {
        _serviceProvider = serviceProvider;
    }

    public async Task MigrateAsync()
    {
        /* We intentionally resolving the LiberapDbContext
         * from IServiceProvider (instead of directly injecting it)
         * to properly get the connection string of the current tenant in the
         * current scope.
         */

        await _serviceProvider
            .GetRequiredService<LiberapDbContext>()
            .Database
            .MigrateAsync();
    }
}
