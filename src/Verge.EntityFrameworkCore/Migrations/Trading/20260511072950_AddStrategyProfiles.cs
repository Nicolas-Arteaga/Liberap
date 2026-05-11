using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddStrategyProfiles : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "StrategyProfileId",
                table: "SimulatedTrades",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "StrategyProfiles",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    IsActive = table.Column<bool>(type: "boolean", nullable: false),
                    MinConfluenceScore = table.Column<float>(type: "real", nullable: false),
                    MinNexusConfidence = table.Column<float>(type: "real", nullable: false),
                    MaxRsiLong = table.Column<float>(type: "real", nullable: false),
                    MinRsiShort = table.Column<float>(type: "real", nullable: false),
                    MaxMa7DistancePct = table.Column<float>(type: "real", nullable: false),
                    RequireMacdPositive = table.Column<bool>(type: "boolean", nullable: true),
                    AllowedSources = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    AllowLong = table.Column<bool>(type: "boolean", nullable: false),
                    AllowShort = table.Column<bool>(type: "boolean", nullable: false),
                    MarginPerTrade = table.Column<decimal>(type: "numeric(18,2)", nullable: false),
                    TpMultiplier = table.Column<float>(type: "real", nullable: false),
                    SlMultiplier = table.Column<float>(type: "real", nullable: false),
                    MinRR = table.Column<float>(type: "real", nullable: false),
                    MaxOpenPositions = table.Column<int>(type: "integer", nullable: false),
                    MaxTradeDurationCandles = table.Column<int>(type: "integer", nullable: false),
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
                    table.PrimaryKey("PK_StrategyProfiles", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_StrategyProfiles_IsActive",
                table: "StrategyProfiles",
                column: "IsActive");

            migrationBuilder.CreateIndex(
                name: "IX_StrategyProfiles_UserId",
                table: "StrategyProfiles",
                column: "UserId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "StrategyProfiles");

            migrationBuilder.DropColumn(
                name: "StrategyProfileId",
                table: "SimulatedTrades");
        }
    }
}
