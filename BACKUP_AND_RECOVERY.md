# Backup y recuperación de Verge

Docker no es el respaldo. Los datos que dan estado a Verge son PostgreSQL,
las bases SQLite de mercado y los artefactos de investigación. Un reset de
contenedores no debe poder destruirlos.

## Qué se versiona en Git

Código, migraciones, especificaciones, pruebas, scripts de descarga,
manifiestos y evidencia legible. Nunca se versionan claves, `.env`, dumps ni
bases SQLite multigigabyte.

## Qué se guarda en un snapshot recuperable

`scripts/backup-research-state.ps1` crea un directorio autocontenido con:

- dump consistente de PostgreSQL (`Verge.dump`);
- snapshots consistentes de `binance_vision_clean.db` y `klines.db`;
- ledger auxiliar del agente, modelos y artefactos de investigación;
- `MANIFEST.json` con SHA-256 de cada archivo y el commit de código asociado.

Ejecutar desde la raíz del repo:

```powershell
.\scripts\backup-research-state.ps1
.\scripts\restore-research-state.ps1 -SnapshotPath .\backups\verge-state-YYYYMMDD-HHMMSS -VerifyOnly
```

Los snapshots se excluyen deliberadamente de Git: el histórico SQLite actual
supera 9 GB. Para resiliencia ante pérdida de la computadora, el directorio
`backups\verge-state-*` debe copiarse a almacenamiento remoto privado y
cifrado. GitHub normal no es apto para esas bases por sus límites de tamaño.

## Restauración

1. Verificar checksums con `-VerifyOnly`.
2. Detener Verge y Docker.
3. Ejecutar el restore con `-Force`.
4. Levantar `docker compose up -d` y verificar salud.

El script rechaza restaurar sin `-Force` y no toma ni restaura `.env` ni
secretos.
