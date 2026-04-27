using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class RemoveFreqtrade : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "TradingBots");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "TradingBots",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    IsActive = table.Column<bool>(type: "boolean", nullable: false),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    Leverage = table.Column<int>(type: "integer", nullable: false),
                    StakeAmount = table.Column<decimal>(type: "numeric", nullable: false),
                    StopLossPercentage = table.Column<decimal>(type: "numeric", nullable: false),
                    Strategy = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Symbol = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    TakeProfitPercentage = table.Column<decimal>(type: "numeric", nullable: false),
                    Timeframe = table.Column<string>(type: "character varying(10)", maxLength: 10, nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: true)
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
    }
}
