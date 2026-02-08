using System.Threading.Tasks;

namespace Verge.Data;

public interface IVergeDbSchemaMigrator
{
    Task MigrateAsync();
}
