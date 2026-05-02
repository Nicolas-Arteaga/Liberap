using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Verge.EntityFrameworkCore;

#nullable disable

namespace Verge.Migrations.Trading
{
    [DbContext(typeof(VergeDbContext))]
    [Migration("20260502120000_AddAgentDecisionJsonToSimulatedTrade")]
    /// <inheritdoc />
    public class AddAgentDecisionJsonToSimulatedTrade : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "AgentDecisionJson",
                table: "SimulatedTrades",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AgentDecisionJson",
                table: "SimulatedTrades");
        }
    }
}
