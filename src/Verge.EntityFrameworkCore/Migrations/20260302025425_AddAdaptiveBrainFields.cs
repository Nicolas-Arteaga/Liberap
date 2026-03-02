using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddAdaptiveBrainFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "EntryDayOfWeek",
                table: "TradingSessions",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "EntryHour",
                table: "TradingSessions",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "InitialConfidence",
                table: "TradingSessions",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "InitialRegime",
                table: "TradingSessions",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "InitialScore",
                table: "TradingSessions",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "InitialVolatility",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "InitialVolumeMcapRatio",
                table: "TradingSessions",
                type: "numeric",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "EntryDayOfWeek",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "EntryHour",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "InitialConfidence",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "InitialRegime",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "InitialScore",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "InitialVolatility",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "InitialVolumeMcapRatio",
                table: "TradingSessions");
        }
    }
}
