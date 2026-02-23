using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddTelemetryToTradingSession : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "ExitReason",
                table: "TradingSessions",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "NetProfit",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Outcome",
                table: "TradingSessions",
                type: "integer",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "ExitReason",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "NetProfit",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "Outcome",
                table: "TradingSessions");
        }
    }
}
