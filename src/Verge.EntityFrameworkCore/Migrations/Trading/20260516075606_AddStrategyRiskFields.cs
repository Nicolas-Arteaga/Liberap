using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddStrategyRiskFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<float>(
                name: "LseMaxEntrySlippagePct",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<float>(
                name: "MaxEntrySlippagePct",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<float>(
                name: "MaxNexusSignalAgeSeconds",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<float>(
                name: "MinEstimatedRangePct",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<float>(
                name: "MinSlDistancePct",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<float>(
                name: "MinTpDistancePct",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);

            migrationBuilder.AddColumn<float>(
                name: "NexusMaxPriceDriftPct",
                table: "StrategyProfiles",
                type: "real",
                nullable: false,
                defaultValue: 0f);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "LseMaxEntrySlippagePct",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "MaxEntrySlippagePct",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "MaxNexusSignalAgeSeconds",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "MinEstimatedRangePct",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "MinSlDistancePct",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "MinTpDistancePct",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "NexusMaxPriceDriftPct",
                table: "StrategyProfiles");
        }
    }
}
