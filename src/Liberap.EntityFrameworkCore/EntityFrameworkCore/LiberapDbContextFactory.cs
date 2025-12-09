using System;
using System.IO;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace Liberap.EntityFrameworkCore;

/* This class is needed for EF Core console commands
 * (like Add-Migration and Update-Database commands) */
public class LiberapDbContextFactory : IDesignTimeDbContextFactory<LiberapDbContext>
{
    public LiberapDbContext CreateDbContext(string[] args)
    {
        var configuration = BuildConfiguration();
        
        LiberapEfCoreEntityExtensionMappings.Configure();

        var builder = new DbContextOptionsBuilder<LiberapDbContext>()
            .UseSqlServer(configuration.GetConnectionString("Default"));
        
        return new LiberapDbContext(builder.Options);
    }

    private static IConfigurationRoot BuildConfiguration()
    {
        var builder = new ConfigurationBuilder()
            .SetBasePath(Path.Combine(Directory.GetCurrentDirectory(), "../Liberap.DbMigrator/"))
            .AddJsonFile("appsettings.json", optional: false)
            .AddEnvironmentVariables();

        return builder.Build();
    }
}
