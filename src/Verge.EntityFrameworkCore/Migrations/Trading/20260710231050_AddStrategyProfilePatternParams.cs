using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddStrategyProfilePatternParams : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "PatternParamsJson",
                table: "StrategyProfiles",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "StrategyType",
                table: "StrategyProfiles",
                type: "text",
                nullable: false,
                defaultValue: "Generic");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "PatternParamsJson",
                table: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "StrategyType",
                table: "StrategyProfiles");
        }
    }
}
