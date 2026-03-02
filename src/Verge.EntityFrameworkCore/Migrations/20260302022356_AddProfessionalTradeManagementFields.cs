using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddProfessionalTradeManagementFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<decimal>(
                name: "CurrentInvestment",
                table: "TradingSessions",
                type: "numeric",
                nullable: false,
                defaultValue: 0m);

            migrationBuilder.AddColumn<decimal>(
                name: "InitialStopLoss",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "IsBreakEvenActive",
                table: "TradingSessions",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<int>(
                name: "PartialTpsCount",
                table: "TradingSessions",
                type: "integer",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<decimal>(
                name: "TrailingStopPrice",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "CurrentInvestment",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "InitialStopLoss",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "IsBreakEvenActive",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "PartialTpsCount",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "TrailingStopPrice",
                table: "TradingSessions");
        }
    }
}
