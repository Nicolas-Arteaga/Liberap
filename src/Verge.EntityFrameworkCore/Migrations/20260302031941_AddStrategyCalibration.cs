using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddStrategyCalibration : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "StrategyCalibrations",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Style = table.Column<int>(type: "integer", nullable: false),
                    Regime = table.Column<int>(type: "integer", nullable: false),
                    TechnicalMultiplier = table.Column<float>(type: "real", nullable: false),
                    QuantitativeMultiplier = table.Column<float>(type: "real", nullable: false),
                    SentimentMultiplier = table.Column<float>(type: "real", nullable: false),
                    FundamentalMultiplier = table.Column<float>(type: "real", nullable: false),
                    EntryThresholdShift = table.Column<int>(type: "integer", nullable: false),
                    TakeProfitMultiplier = table.Column<int>(type: "integer", nullable: false),
                    LastRecalibrated = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
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
                    table.PrimaryKey("PK_StrategyCalibrations", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_StrategyCalibrations_Style_Regime",
                table: "StrategyCalibrations",
                columns: new[] { "Style", "Regime" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "StrategyCalibrations");
        }
    }
}
