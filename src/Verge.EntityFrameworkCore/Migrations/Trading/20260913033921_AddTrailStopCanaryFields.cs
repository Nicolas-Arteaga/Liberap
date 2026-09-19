using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Verge.Migrations.Trading
{
    /// <inheritdoc />
    public partial class AddTrailStopCanaryFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // NOTA (ROUND 40): "BreakevenLocked" fue removido de este Up() a
            // mano -- la columna YA EXISTE en la base de produccion (Postgres
            // localhost:5433/Verge), verificado por SQL directo antes de
            // generar esta migracion. EF la propuso porque nunca hubo una
            // migracion anterior que la capturara (drift preexistente entre
            // el modelo y la base, no causado por este cambio). Incluirla acá
            // haria fallar el Up() con "column already exists" al aplicarse.
            // El ModelSnapshot SI la sigue listando (correcto: describe el
            // estado final, no los pasos incrementales).

            migrationBuilder.AddColumn<decimal>(
                name: "OriginalSlPrice",
                table: "SimulatedTrades",
                type: "numeric",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "TrailAuditJson",
                table: "SimulatedTrades",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "TrailLevelApplied",
                table: "SimulatedTrades",
                type: "integer",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<bool>(
                name: "TrailStopCanary",
                table: "SimulatedTrades",
                type: "boolean",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // No se dropea "BreakevenLocked" -- no fue esta migracion la que
            // la agrego (ver nota en Up()), asi que revertir esta migracion
            // no debe borrarla.

            migrationBuilder.DropColumn(
                name: "OriginalSlPrice",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "TrailAuditJson",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "TrailLevelApplied",
                table: "SimulatedTrades");

            migrationBuilder.DropColumn(
                name: "TrailStopCanary",
                table: "SimulatedTrades");
        }
    }
}
