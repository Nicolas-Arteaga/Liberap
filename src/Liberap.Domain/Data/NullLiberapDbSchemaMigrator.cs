using System.Threading.Tasks;
using Volo.Abp.DependencyInjection;

namespace Liberap.Data;

/* This is used if database provider does't define
 * ILiberapDbSchemaMigrator implementation.
 */
public class NullLiberapDbSchemaMigrator : ILiberapDbSchemaMigrator, ITransientDependency
{
    public Task MigrateAsync()
    {
        return Task.CompletedTask;
    }
}
