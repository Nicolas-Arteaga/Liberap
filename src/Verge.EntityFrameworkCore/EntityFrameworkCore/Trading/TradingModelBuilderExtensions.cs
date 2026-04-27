using Verge.Trading;
using Verge.Trading.DecisionEngine;
using Verge.Trading.Optimization;
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

        builder.Entity<AnalysisLog>(b =>
        {
            b.ToTable("AnalysisLogs");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.Property(x => x.Message).IsRequired().HasMaxLength(512);
            b.Property(x => x.Level).IsRequired().HasMaxLength(20);
            b.HasIndex(x => x.TradingSessionId);
            b.HasIndex(x => x.TraderProfileId);
        });
        
        builder.Entity<StrategyCalibration>(b =>
        {
            b.ToTable("StrategyCalibrations");
            b.ConfigureByConvention();
            b.HasIndex(x => new { x.Style, x.Regime }).IsUnique();
        });

        builder.Entity<WhaleMovement>(b =>
        {
            b.ToTable("WhaleMovements");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.Property(x => x.WalletAddress).IsRequired().HasMaxLength(128);
            b.HasIndex(x => x.Symbol);
            b.HasIndex(x => x.WalletAddress);
        });

        builder.Entity<TemporalOptimizationResult>(b =>
        {
            b.ToTable("TemporalOptimizationResults");
            b.ConfigureByConvention();
            b.Property(x => x.Regime).IsRequired().HasMaxLength(64);
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.Property(x => x.WeightsJson).IsRequired();
            b.HasIndex(x => new { x.Regime, x.Symbol });
        });

        builder.Entity<SimulatedTrade>(b =>
        {
            b.ToTable("SimulatedTrades");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.HasIndex(x => x.UserId);
            b.HasIndex(x => x.Symbol);
            b.HasIndex(x => x.Status);
        });

        builder.Entity<AlertHistory>(b =>
        {
            b.ToTable("AlertHistories");
            b.ConfigureByConvention();
            b.Property(x => x.Symbol).IsRequired().HasMaxLength(20);
            b.Property(x => x.Style).IsRequired().HasMaxLength(50);
            b.Property(x => x.Status).IsRequired().HasMaxLength(50);
            b.Property(x => x.AlertTier).IsRequired().HasMaxLength(50);
            b.HasIndex(x => x.Symbol);
            b.HasIndex(x => x.Style);
            b.HasIndex(x => x.Status);
            b.HasIndex(x => x.AlertTier);
            b.HasIndex(x => x.AlertType);
            b.HasIndex(x => x.IsRead);
            b.HasIndex(x => x.EmittedAt);
            b.Property(x => x.AlertType).IsRequired().HasMaxLength(50);
            b.Property(x => x.EntryPrice).HasColumnType("decimal(18,8)");
            b.Property(x => x.TargetPrice).HasColumnType("decimal(18,8)");
            b.Property(x => x.StopLossPrice).HasColumnType("decimal(18,8)");
            b.Property(x => x.ExpectedDrawdownPct).HasColumnType("decimal(18,8)");
            b.Property(x => x.ActualExitPrice).HasColumnType("decimal(18,8)");
            b.Property(x => x.ActualPnlPct).HasColumnType("decimal(18,8)");
        });

    }
}
