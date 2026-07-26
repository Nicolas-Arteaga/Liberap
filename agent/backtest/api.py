"""
API HTTP del motor de backtest (agent/backtest/engine.py). Corre como proceso
propio dentro del contexto de `agent/` (necesita importar verge_agent.py /
risk_manager.py / config.py directo, no via HTTP a python-service).

Endpoints:
  POST /backtest/run    {strategyProfileId, startDate, endDate} -> {jobId}
  GET  /backtest/status/{job_id} -> {status, done, total}
  GET  /backtest/result/{job_id} -> resultado completo (cuando status=="completed")

Uso: python -m backtest.api   (desde agent/, sirve en 0.0.0.0:8010)
"""
import os
import sys
import json
import uuid
import threading
import time
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

import config
from auth_manager import AuthManager
from backtest.engine import BacktestEngine

app = FastAPI(title="Verge Backtest API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth = AuthManager()
_jobs: dict[str, dict] = {}
_engine: Optional[BacktestEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> BacktestEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = BacktestEngine()
        return _engine


class RunRequest(BaseModel):
    strategyProfileId: str
    startDate: str  # "YYYY-MM-DD"
    endDate: str    # "YYYY-MM-DD"
    symbols: Optional[list[str]] = None  # None = watchlist completo


def _fetch_profile(profile_id: str) -> dict:
    headers = _auth.get_auth_headers()
    if not headers:
        raise HTTPException(status_code=502, detail="No se pudo autenticar contra el backend ABP")
    url = f"{config.ABP_BACKEND_URL}/api/app/strategy-profile/{profile_id}"
    resp = requests.get(url, headers=headers, verify=False, timeout=30)
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Perfil no encontrado ({resp.status_code})")
    return resp.json()


def _run_job(job_id: str, profile: dict, symbols: list, start_ms: int, end_ms: int):
    job = _jobs[job_id]
    try:
        engine = get_engine()

        def progress_cb(done, total):
            job["done"] = done
            job["total"] = total

        # Registro de StrategyType -> metodo del motor. Agregar una nueva
        # estrategia (que YA reusa el patron _run_generic) es agregar una
        # linea aca -- ver agent/backtest/engine.py::run_ma_geometry/run_fvg
        # para el ejemplo de como conectar un tipo nuevo.
        strategy_type = profile.get("strategyType")
        runners = {
            "MaGeometry": engine.run_ma_geometry,
            "FVG": engine.run_fvg,
        }
        runner = runners.get(strategy_type)
        if not runner:
            job["status"] = "failed"
            job["error"] = f"StrategyType='{strategy_type}' aun no conectado al motor (soportados: {list(runners.keys())})"
            return

        result = runner(profile, symbols, start_ms, end_ms, progress_cb=progress_cb)
        result.pop("all_signals_raw", None)
        result.pop("shadow_signals", None)
        job["result"] = result
        job["status"] = "completed"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.post("/backtest/run")
def run_backtest(req: RunRequest):
    profile = _fetch_profile(req.strategyProfileId)

    engine = get_engine()
    symbols = req.symbols or engine.available_symbols()

    start_ms = int(datetime.strptime(req.startDate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(req.endDate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "done": 0, "total": len(symbols), "created_at": time.time()}

    t = threading.Thread(target=_run_job, args=(job_id, profile, symbols, start_ms, end_ms), daemon=True)
    t.start()

    return {"jobId": job_id}


@app.get("/backtest/status/{job_id}")
def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return {"status": job["status"], "done": job.get("done", 0), "total": job.get("total", 0),
             "error": job.get("error")}


@app.get("/backtest/result/{job_id}")
def get_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job no encontrado")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"job en estado '{job['status']}', todavia no hay resultado")
    return job["result"]


@app.get("/backtest/symbols")
def list_symbols():
    return {"symbols": get_engine().available_symbols()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
