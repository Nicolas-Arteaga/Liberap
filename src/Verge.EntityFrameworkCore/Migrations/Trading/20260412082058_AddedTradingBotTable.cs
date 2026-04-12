using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddedTradingBotTable : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "TradingBots",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    Strategy = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Timeframe = table.Column<string>(type: "character varying(10)", maxLength: 10, nullable: false),
                    StakeAmount = table.Column<decimal>(type: "numeric", nullable: false),
                    Leverage = table.Column<int>(type: "integer", nullable: false),
                    TakeProfitPercentage = table.Column<decimal>(type: "numeric", nullable: false),
                    StopLossPercentage = table.Column<decimal>(type: "numeric", nullable: false),
                    IsActive = table.Column<bool>(type: "boolean", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: true),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_TradingBots", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_TradingBots_IsActive",
                table: "TradingBots",
                column: "IsActive");

            migrationBuilder.CreateIndex(
                name: "IX_TradingBots_Symbol",
                table: "TradingBots",
                column: "Symbol");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "TradingBots");
        }
    }
}
