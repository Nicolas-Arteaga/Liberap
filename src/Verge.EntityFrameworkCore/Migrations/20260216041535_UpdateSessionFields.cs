using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class UpdateSessionFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<decimal>(
                name: "StopLossPercentage",
                table: "TradingStrategies",
                type: "numeric",
                nullable: false,
                defaultValue: 0m);

            migrationBuilder.AddColumn<decimal>(
                name: "EntryPrice",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "StopLossPrice",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "TakeProfitPrice",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "StopLossPercentage",
                table: "TradingStrategies");

            migrationBuilder.DropColumn(
                name: "EntryPrice",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "StopLossPrice",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "TakeProfitPrice",
                table: "TradingSessions");
        }
    }
}
