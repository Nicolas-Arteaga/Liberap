"""
2026-08-18: servicio de control del laboratorio, pedido explicito del
usuario -- "quiero un boton en el laboratorio para iniciarlo... si algun
dia no te tengo a vos, quiero resolverlo con el boton de arranque y
listo". Corre en el HOST (no en Docker, a diferencia de api.py/:8010) --
un contenedor no puede arrancar procesos del host directamente, y
strategy_lab.py corre en el host. El frontend (Angular, en el navegador
del propio usuario) le habla directo por localhost, sin pasar por Docker.

Uso: python -m backtest.lab_control_server   (desde agent/, puerto 8011)
Se auto-arranca con la tarea programada Verge-LabControl-AutoStart.
"""
import os
import sys
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON_EXE = sys.executable
PID_FILE = os.path.join(os.path.dirname(__file__), "lab_control.pid")
STDOUT_LOG = os.path.join(os.path.dirname(__file__), "lab_stdout.log")
CURRENT_PATH = os.path.join(os.path.dirname(__file__), "lab_current.json")

app = FastAPI(title="Verge Lab Control")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # solo escucha en localhost, no expuesto a internet
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_pid() -> int | None:
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    """Windows no tiene os.kill(pid, 0) -- usa tasklist para chequear si el PID vive."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL, text=True,
        )
        return str(pid) in out
    except Exception:
        return False


@app.get("/control/status")
def status():
    pid = _read_pid()
    tracked_running = bool(pid and _is_running(pid))
    heartbeat_age = None
    if os.path.exists(CURRENT_PATH):
        try:
            age = time.time() - os.path.getmtime(CURRENT_PATH)
            heartbeat_age = round(age, 1)
        except OSError:
            pass
    # Fallback: si el proceso arranco por fuera de este control server (ej.
    # manualmente, o antes de que este servicio existiera), no hay PID
    # trackeado -- el heartbeat fresco es igual de valido como señal de vida.
    running = tracked_running or (heartbeat_age is not None and heartbeat_age < 60)
    return {"running": running, "pid": pid if tracked_running else None, "heartbeatAgeSec": heartbeat_age}


def _start_lab_process() -> dict:
    pid = _read_pid()
    if pid and _is_running(pid):
        return {"ok": True, "already_running": True, "pid": pid}
    if os.path.exists(CURRENT_PATH):
        try:
            if time.time() - os.path.getmtime(CURRENT_PATH) < 60:
                return {"ok": True, "already_running": True, "pid": None,
                         "note": "heartbeat fresco de un proceso no trackeado por este control server"}
        except OSError:
            pass

    log_f = open(STDOUT_LOG, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON_EXE, "-u", "-m", "backtest.evolutionary_lab"],
        cwd=AGENT_DIR,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))
    return {"ok": True, "already_running": False, "pid": proc.pid}


@app.on_event("startup")
def _auto_start_on_boot():
    """2026-08-18: arranca el laboratorio solo, apenas este servicio de
    control levanta (ej. al iniciar sesion en Windows, via la tarea
    programada) -- asi el usuario no necesita apretar el boton despues de
    cada reinicio, sigue funcionando "solo" como antes. El boton del
    frontend queda para pausar/reiniciar manualmente cuando quiera."""
    _start_lab_process()


@app.post("/control/start")
def start():
    return _start_lab_process()


@app.post("/control/stop")
def stop():
    pid = _read_pid()
    if not pid or not _is_running(pid):
        return {"ok": True, "was_running": False}
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    return {"ok": True, "was_running": True}


# ── "Crear Estrategia" -- 2026-08-18, pedido explicito del usuario: un
# boton que, con la estrategia que el laboratorio encontro, la inserte
# directo en la base de produccion y arranque a operar sola, sin tocar
# SQL a mano. Solo soporta los entry_types que YA tienen un scan real
# conectado en verge_agent.py (level_sweep, band_touch, rsi_extreme,
# ma_pullback) -- ma_cross NO tiene scan real todavia, se rechaza. Level
# Sweep/Band Touch son SHORT-unicamente en produccion real (el scan real
# ni siquiera chequea el lado, esta hardcodeado) -- una estrategia LONG/
# BOTH de esos dos tipos no puede desplegarse, se rechaza con un mensaje
# claro en vez de crear un perfil que nunca va a generar señales.
ALLOWED_SOURCES_BY_ENTRY_TYPE = {
    "level_sweep": "level_sweep_1h",
    "band_touch": "band_touch",
    "rsi_extreme": "rsi_extreme",
    "ma_pullback": "ma_pullback",
}
SHORT_ONLY_ENTRY_TYPES = {"level_sweep", "band_touch"}

# Perfil real usado como plantilla para no adivinar el schema completo de
# StrategyProfiles -- Level Sweep 1H (laboratorio), UserId real (necesario
# para el FK), demas campos por defecto razonables.
TEMPLATE_PROFILE_ID = "a5ac7221-7cbd-43f4-87cc-af7628f14c79"


class DeployRequest(BaseModel):
    strat: dict
    result: dict
    name: str | None = None


def _pattern_params_for(strat: dict) -> dict:
    et = strat["entry_type"]
    base = {"tfMin": strat["tf_min"], "atrSlMult": strat["atr_sl_mult"], "rrMult": strat["rr_mult"]}
    if et == "level_sweep":
        base["lookback"] = strat.get("lookback", 10)
        base["capSlLoss"] = False
    elif et == "band_touch":
        base["capSlLoss"] = False
    elif et == "rsi_extreme":
        rsi_thresh = strat.get("rsi_thresh", [75, 25])
        base["rsiHi"] = rsi_thresh[0]
        base["rsiLo"] = rsi_thresh[1]
    elif et == "ma_pullback":
        base["lookback"] = strat.get("lookback", 10)
        base["slopeMinPct"] = strat.get("slope_min_pct", 1.0)
    return base


@app.post("/control/deploy")
def deploy(req: DeployRequest):
    strat = req.strat
    result = req.result
    et = strat.get("entry_type")

    if et not in ALLOWED_SOURCES_BY_ENTRY_TYPE:
        raise HTTPException(400, detail=f"'{et}' todavia no tiene un scan real conectado en produccion "
                                          f"(solo level_sweep, band_touch, rsi_extreme, ma_pullback) -- no se puede desplegar.")

    side = strat.get("side", "SHORT")
    if et in SHORT_ONLY_ENTRY_TYPES and side != "SHORT":
        raise HTTPException(400, detail=f"'{et}' es SHORT-unicamente en produccion real (el scan no soporta LONG/BOTH "
                                          f"todavia) -- esta estrategia encontrada es {side}, no se puede desplegar tal cual.")

    try:
        import psycopg2
    except ImportError:
        raise HTTPException(500, detail="psycopg2 no disponible en este entorno")

    allow_long = side in ("LONG", "BOTH")
    allow_short = side in ("SHORT", "BOTH")
    new_id = str(uuid.uuid4())
    name = req.name or f"{et} {strat['tf_min']}m {side} (evolutivo)"
    pattern_params = json.dumps(_pattern_params_for(strat))
    concurrency_stamp = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = psycopg2.connect(host="localhost", port=5433, dbname="Verge", user="postgres", password="postgres")
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "UserId" FROM "StrategyProfiles" WHERE "Id"=%s', (TEMPLATE_PROFILE_ID,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(500, detail="perfil plantilla no encontrado, no se puede desplegar")
            user_id = row[0]

            cur.execute('''
                INSERT INTO "StrategyProfiles" (
                    "Id", "UserId", "Name", "IsActive", "MinConfluenceScore", "MinNexusConfidence",
                    "MaxRsiLong", "MinRsiShort", "MaxMa7DistancePct", "AllowedSources",
                    "AllowLong", "AllowShort", "MarginPerTrade", "TpMultiplier", "SlMultiplier",
                    "MinRR", "MaxOpenPositions", "MaxTradeDurationCandles", "ExtraProperties",
                    "ConcurrencyStamp", "CreationTime", "IsDeleted", "Color", "Description",
                    "ExtremeRsiVeto", "LseMaxEntrySlippagePct", "MaxEntrySlippagePct",
                    "MaxNexusSignalAgeSeconds", "MinEstimatedRangePct", "MinSlDistancePct",
                    "MinTpDistancePct", "NexusMaxPriceDriftPct", "PatternParamsJson",
                    "StrategyType", "BroadcastToBinance"
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            ''', (
                new_id, user_id, name, True, 80.0, 50.0,
                80.0, 20.0, 5.0, ALLOWED_SOURCES_BY_ENTRY_TYPE[et],
                allow_long, allow_short, 150.0, 4.0, 2.0,
                2.0, 3, 96, "{}",
                concurrency_stamp, now_iso, False, "#00e68f",
                f"Creada por el laboratorio evolutivo ({now_iso[:10]}) -- backtest: {result.get('n')} trades, "
                f"WR={result.get('wr_pct')}%, ${result.get('monthly')}/mes, estable={result.get('stable_between_halves')}.",
                True, 0.015, 0.002,
                120.0, 3.0, 0.002,
                0.003, 0.025, pattern_params,
                "Generic", False,
            ))
            conn.commit()
    finally:
        conn.close()

    return {"ok": True, "id": new_id, "name": name, "allowedSources": ALLOWED_SOURCES_BY_ENTRY_TYPE[et]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011)
