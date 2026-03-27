using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddAlertHistoryTypeAndRead : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "AlertHistories",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Symbol = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    Style = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    Direction = table.Column<int>(type: "integer", nullable: false),
                    EntryPrice = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    TargetPrice = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    StopLossPrice = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    Confidence = table.Column<int>(type: "integer", nullable: false),
                    EstimatedTimeMinutes = table.Column<int>(type: "integer", nullable: false),
                    ExpectedDrawdownPct = table.Column<decimal>(type: "numeric(18,8)", nullable: false),
                    ReasoningJson = table.Column<string>(type: "text", nullable: false),
                    RawDataJson = table.Column<string>(type: "text", nullable: false),
                    EmittedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ExpiresAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    Status = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    ActualExitPrice = table.Column<decimal>(type: "numeric(18,8)", nullable: true),
                    ActualPnlPct = table.Column<decimal>(type: "numeric(18,8)", nullable: true),
                    TimeToResolutionMinutes = table.Column<int>(type: "integer", nullable: true),
                    AlertTier = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    AlertType = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    IsRead = table.Column<bool>(type: "boolean", nullable: false),
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
                    table.PrimaryKey("PK_AlertHistories", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_AlertTier",
                table: "AlertHistories",
                column: "AlertTier");

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_AlertType",
                table: "AlertHistories",
                column: "AlertType");

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_EmittedAt",
                table: "AlertHistories",
                column: "EmittedAt");

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_IsRead",
                table: "AlertHistories",
                column: "IsRead");

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_Status",
                table: "AlertHistories",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_Style",
                table: "AlertHistories",
                column: "Style");

            migrationBuilder.CreateIndex(
                name: "IX_AlertHistories_Symbol",
                table: "AlertHistories",
                column: "Symbol");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "AlertHistories");
        }
    }
}
