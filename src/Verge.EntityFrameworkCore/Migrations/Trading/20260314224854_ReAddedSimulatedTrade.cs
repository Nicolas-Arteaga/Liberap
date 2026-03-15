using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class ReAddedSimulatedTrade : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<decimal>(
                name: "VirtualBalance",
                table: "TraderProfiles",
                type: "numeric",
                nullable: false,
                defaultValue: 0m);

            migrationBuilder.CreateTable(
                name: "SimulatedTrades",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    Side = table.Column<int>(type: "integer", nullable: false),
                    Leverage = table.Column<int>(type: "integer", nullable: false),
                    Size = table.Column<decimal>(type: "numeric", nullable: false),
                    Amount = table.Column<decimal>(type: "numeric", nullable: false),
                    EntryPrice = table.Column<decimal>(type: "numeric", nullable: false),
                    MarkPrice = table.Column<decimal>(type: "numeric", nullable: false),
                    LiquidationPrice = table.Column<decimal>(type: "numeric", nullable: false),
                    Margin = table.Column<decimal>(type: "numeric", nullable: false),
                    MarginRate = table.Column<decimal>(type: "numeric", nullable: false),
                    UnrealizedPnl = table.Column<decimal>(type: "numeric", nullable: false),
                    ROIPercentage = table.Column<decimal>(type: "numeric", nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    ClosePrice = table.Column<decimal>(type: "numeric", nullable: true),
                    RealizedPnl = table.Column<decimal>(type: "numeric", nullable: true),
                    EntryFee = table.Column<decimal>(type: "numeric", nullable: false),
                    ExitFee = table.Column<decimal>(type: "numeric", nullable: false),
                    TotalFundingPaid = table.Column<decimal>(type: "numeric", nullable: false),
                    OpenedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ClosedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    TradingSignalId = table.Column<Guid>(type: "uuid", nullable: true),
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
                    table.PrimaryKey("PK_SimulatedTrades", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_SimulatedTrades_Status",
                table: "SimulatedTrades",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_SimulatedTrades_Symbol",
                table: "SimulatedTrades",
                column: "Symbol");

            migrationBuilder.CreateIndex(
                name: "IX_SimulatedTrades_UserId",
                table: "SimulatedTrades",
                column: "UserId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "VirtualBalance",
                table: "TraderProfiles");
        }
    }
}
