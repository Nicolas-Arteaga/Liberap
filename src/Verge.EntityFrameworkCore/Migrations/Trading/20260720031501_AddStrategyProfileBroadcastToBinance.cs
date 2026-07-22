using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddStrategyProfileBroadcastToBinance : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<string>(
                name: "StrategyType",
                table: "StrategyProfiles",
                type: "text",
                nullable: false,
                oldClrType: typeof(string),
                oldType: "text",
                oldDefaultValue: "Generic");

            migrationBuilder.AddColumn<bool>(
                name: "BroadcastToBinance",
                table: "StrategyProfiles",
                type: "boolean",
                nullable: false,
                defaultValue: false);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "BroadcastToBinance",
                table: "StrategyProfiles");

            migrationBuilder.AlterColumn<string>(
                name: "StrategyType",
                table: "StrategyProfiles",
                type: "text",
                nullable: false,
                defaultValue: "Generic",
                oldClrType: typeof(string),
                oldType: "text");
        }
    }
}
