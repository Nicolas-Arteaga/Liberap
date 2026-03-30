using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddScalpingBotTrades : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "BotTrades",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    Direction = table.Column<int>(type: "integer", nullable: false),
                    Timeframe = table.Column<string>(type: "character varying(5)", maxLength: 5, nullable: false),
                    EntryPrice = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    StopLoss = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    TakeProfit1 = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    TakeProfit2 = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    Leverage = table.Column<int>(type: "integer", nullable: false),
                    Margin = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    PositionSize = table.Column<decimal>(type: "numeric", nullable: false),
                    PositionSizeRemaining = table.Column<decimal>(type: "numeric", nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    PartialCloseDone = table.Column<bool>(type: "boolean", nullable: false),
                    TrailingActive = table.Column<bool>(type: "boolean", nullable: false),
                    TrailingStopPrice = table.Column<decimal>(type: "numeric(18,8)", nullable: true),
                    PartialPnl = table.Column<decimal>(type: "numeric(18,8)", nullable: true),
                    FinalPnl = table.Column<decimal>(type: "numeric(18,8)", nullable: true),
                    TotalPnl = table.Column<decimal>(type: "numeric(18,8)", nullable: true),
                    CloseReason = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    OpenedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    PartialClosedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ClosedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ATR = table.Column<decimal>(type: "numeric", nullable: false),
                    ATRPercent = table.Column<decimal>(type: "numeric", nullable: false),
                    SLPercent = table.Column<decimal>(type: "numeric", nullable: false),
                    ScannerScore = table.Column<int>(type: "integer", nullable: false),
                    EntryConditionsJson = table.Column<string>(type: "character varying(4000)", maxLength: 4000, nullable: false),
                    SimulatedTradeId = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
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
                    table.PrimaryKey("PK_BotTrades", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_BotTrades_OpenedAt",
                table: "BotTrades",
                column: "OpenedAt");

            migrationBuilder.CreateIndex(
                name: "IX_BotTrades_Status",
                table: "BotTrades",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_BotTrades_Symbol",
                table: "BotTrades",
                column: "Symbol");

            migrationBuilder.CreateIndex(
                name: "IX_BotTrades_UserId",
                table: "BotTrades",
                column: "UserId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "BotTrades");
        }
    }
}
