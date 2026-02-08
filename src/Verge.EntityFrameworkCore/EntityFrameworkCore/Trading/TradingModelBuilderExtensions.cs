using Verge.Trading;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Volo.Abp.EntityFrameworkCore.Modeling;

namespace Verge.EntityFrameworkCore.Trading;

public static class TradingModelBuilderExtensions
{
    public static void ConfigureTrading(this ModelBuilder builder)
    {
        builder.Entity<TraderProfile>(b =>
        {
            b.ToTable("TraderProfiles");
            b.ConfigureByConvention();
            b.Property(x => x.Name).IsRequired().HasMaxLength(128);
            b.Property(x => x.Email).IsRequired().HasMaxLength(128);
        });

        builder.Entity<TradingSignal>(b =>
        {
            b.ToTable("TradingSignals");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.HasIndex(x => x.Symbol);
        });

        builder.Entity<TradingStrategy>(b =>
        {
            b.ToTable("TradingStrategies");
            b.ConfigureByConvention();
            b.Property(x => x.Name).IsRequired().HasMaxLength(128);
        });

        builder.Entity<TradeOrder>(b =>
        {
            b.ToTable("TradeOrders");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.HasIndex(x => x.Symbol);
        });

        builder.Entity<TradingSession>(b =>
        {
            b.ToTable("TradingSessions");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
        });

        builder.Entity<TradingAlert>(b =>
        {
            b.ToTable("TradingAlerts");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
        });

        builder.Entity<BacktestResult>(b =>
        {
            b.ToTable("BacktestResults");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
        });

        builder.Entity<ExchangeConnection>(b =>
        {
            b.ToTable("ExchangeConnections");
            b.ConfigureByConvention();
            b.Property(x => x.ExchangeName).IsRequired().HasMaxLength(64);
        });
    }
}
