using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddSignalTrackingFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<decimal>(
                name: "RealizedPnL",
                table: "TradingSignals",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Regime",
                table: "TradingSignals",
                type: "integer",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "RealizedPnL",
                table: "TradingSignals");

            migrationBuilder.DropColumn(
                name: "Regime",
                table: "TradingSignals");
        }
    }
}
