using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations
{
    /// <inheritdoc />
    public partial class AddLiveExecutionTrackingFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "DurationMinutes",
                table: "TradingSignals",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "EquityAfter",
                table: "TradingSignals",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "ExitPrice",
                table: "TradingSignals",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "ExitTime",
                table: "TradingSignals",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Score",
                table: "TradingSignals",
                type: "integer",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "DurationMinutes",
                table: "TradingSignals");

            migrationBuilder.DropColumn(
                name: "EquityAfter",
                table: "TradingSignals");

            migrationBuilder.DropColumn(
                name: "ExitPrice",
                table: "TradingSignals");

            migrationBuilder.DropColumn(
                name: "ExitTime",
                table: "TradingSignals");

            migrationBuilder.DropColumn(
                name: "Score",
                table: "TradingSignals");
        }
    }
}
