using System.Threading.Tasks;
using Volo.Abp.DependencyInjection;

namespace Verge.Data;

/* This is used if database provider does't define
 * IVergeDbSchemaMigrator implementation.
 */
public class NullVergeDbSchemaMigrator : IVergeDbSchemaMigrator, ITransientDependency
{
    public Task MigrateAsync()
    {
        return Task.CompletedTask;
    }
}
