using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddTpSlProgressToSimulatedTrade : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<decimal>(
                name: "MaxSlProgressPct",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "MaxTpProgressPct",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "TpProgressPct",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "MaxSlProgressPct",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "MaxTpProgressPct",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "TpProgressPct",
                table: "SimulatedTrades");
        }
    }
}
