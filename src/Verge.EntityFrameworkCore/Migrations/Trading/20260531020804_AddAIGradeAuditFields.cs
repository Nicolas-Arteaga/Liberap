using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddAIGradeAuditFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<decimal>(
                name: "BtcPriceAtClose",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ExitReason",
                table: "SimulatedTrades",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "Ma7DistancePctAtEntry",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "MaxFavorablePrice",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "BtcPriceAtClose",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "ExitReason",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "Ma7DistancePctAtEntry",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "MaxFavorablePrice",
                table: "SimulatedTrades");
        }
    }
}
