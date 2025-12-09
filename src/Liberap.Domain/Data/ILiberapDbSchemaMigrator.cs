using System.Threading.Tasks;

namespace Liberap.Data;

public interface ILiberapDbSchemaMigrator
{
    Task MigrateAsync();
}
