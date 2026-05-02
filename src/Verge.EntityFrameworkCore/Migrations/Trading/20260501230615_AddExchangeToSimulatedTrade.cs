using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddExchangeToSimulatedTrade : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "Exchange",
                table: "SimulatedTrades",
                type: "character varying(32)",
                maxLength: 32,
                nullable: false,
                defaultValue: "Binance");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Exchange",
                table: "SimulatedTrades");
        }
    }
}
