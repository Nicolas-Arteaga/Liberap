using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddInstitutionalToSession : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<bool>(
                name: "MacroQuietPeriod",
                table: "TradingSessions",
                type: "boolean",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "MacroReason",
                table: "TradingSessions",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "WhaleInfluenceScore",
                table: "TradingSessions",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "WhaleSentiment",
                table: "TradingSessions",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "MacroQuietPeriod",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "MacroReason",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "WhaleInfluenceScore",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "WhaleSentiment",
                table: "TradingSessions");
        }
    }
}
