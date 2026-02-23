using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddSelectedFieldsToTradingSession : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "SelectedDirection",
                table: "TradingSessions",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "SelectedStyle",
                table: "TradingSessions",
                type: "integer",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "SelectedDirection",
                table: "TradingSessions");

            migrationBuilder.DropColumn(
                name: "SelectedStyle",
                table: "TradingSessions");
        }
    }
}
