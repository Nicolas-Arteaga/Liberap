using System;
using System.IO;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace Verge.EntityFrameworkCore;

/* This class is needed for EF Core console commands
 * (like Add-Migration and Update-Database commands) */
public class VergeDbContextFactory : IDesignTimeDbContextFactory<VergeDbContext>
{
    public VergeDbContext CreateDbContext(string[] args)
    {
        var configuration = BuildConfiguration();
        
        VergeEfCoreEntityExtensionMappings.Configure();

        var builder = new DbContextOptionsBuilder<VergeDbContext>()
            .UseNpgsql(configuration.GetConnectionString("Default"));
        
        return new VergeDbContext(builder.Options);
    }

    private static IConfigurationRoot BuildConfiguration()
    {
        var builder = new ConfigurationBuilder()
            .SetBasePath(Path.Combine(Directory.GetCurrentDirectory(), "../Verge.DbMigrator/"))
            .AddJsonFile("appsettings.json", optional: false)
            .AddEnvironmentVariables();

        return builder.Build();
    }
}
