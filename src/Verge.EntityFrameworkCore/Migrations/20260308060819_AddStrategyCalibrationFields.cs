using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddStrategyCalibrationFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "EntryThreshold",
                table: "StrategyCalibrations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<float>(
                name: "InstitutionalMultiplier",
                table: "StrategyCalibrations",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<double>(
                name: "ProfitFactor",
                table: "StrategyCalibrations",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "SharpeRatio",
                table: "StrategyCalibrations",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "TotalTrades",
                table: "StrategyCalibrations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<float>(
                name: "TrailingMultiplier",
                table: "StrategyCalibrations",
                type: "real",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "WeightsJson",
                table: "StrategyCalibrations",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "WinRate",
                table: "StrategyCalibrations",
                type: "double precision",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "TemporalOptimizationResults",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Regime = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Symbol = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    Timeframe = table.Column<string>(type: "text", nullable: false),
                    WeightsJson = table.Column<string>(type: "text", nullable: false),
                    ProfitFactor = table.Column<double>(type: "double precision", nullable: false),
                    SharpeRatio = table.Column<double>(type: "double precision", nullable: false),
                    WinRate = table.Column<double>(type: "double precision", nullable: false),
                    TotalTrades = table.Column<int>(type: "integer", nullable: false),
                    TotalPnL = table.Column<decimal>(type: "numeric", nullable: false),
                    EntryThreshold = table.Column<int>(type: "integer", nullable: false),
                    TrailingMultiplier = table.Column<float>(type: "real", nullable: false),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_TemporalOptimizationResults", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_TemporalOptimizationResults_Regime_Symbol",
                table: "TemporalOptimizationResults",
                columns: new[] { "Regime", "Symbol" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "TemporalOptimizationResults");

            migrationBuilder.DropColumn(
                name: "EntryThreshold",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "InstitutionalMultiplier",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "ProfitFactor",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "SharpeRatio",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "TotalTrades",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "TrailingMultiplier",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "WeightsJson",
                table: "StrategyCalibrations");

            migrationBuilder.DropColumn(
                name: "WinRate",
                table: "StrategyCalibrations");
        }
    }
}
