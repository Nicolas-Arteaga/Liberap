using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddStrategyFidelityFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "CustomSymbolsJson",
                table: "TradingStrategies",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "IsAutoMode",
                table: "TradingStrategies",
                type: "boolean",
                nullable: false,
                defaultValue: false);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "CustomSymbolsJson",
                table: "TradingStrategies");

            migrationBuilder.DropColumn(
                name: "IsAutoMode",
                table: "TradingStrategies");
        }
    }
}
