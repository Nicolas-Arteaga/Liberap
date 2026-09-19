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
import sqlite3
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
from backtest import storage
from backtest import data_sync
from backtest import invariant_research
from backtest import funding_research
from backtest import oi_research
from backtest import liquidation_research
from backtest import forced_flow_research
from backtest import cross_venue_research

app = FastAPI(title="Verge Backtest API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness only: must not scan the multi-GB historical SQLite volume."""
    return {"ok": True, "service": "verge-backtest"}


@app.get("/research/execution-audit")
def execution_audit():
    """Read-only execution baseline generated on the host by auto_tuner."""
    path = os.getenv("VIRE_EXECUTION_AUDIT", "/app/execution-audit/auto_tuner_recommendations.json")
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {"status": "NOT_RUN"}
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"execution audit unavailable: {type(exc).__name__}")

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

        # Registro de StrategyType -> soportado por el motor. Agregar una
        # estrategia nueva (que YA reusa el patron _run_generic) es agregar
        # su nombre aca -- ver agent/backtest/engine.py::run_ma_geometry/
        # run_fvg/run_adn_compression para el ejemplo de como conectar un
        # tipo nuevo, y _parallel_worker para registrarlo tambien ahi.
        strategy_type = profile.get("strategyType")
        supported = ("MaGeometry", "FVG", "AdnCompression")
        if strategy_type not in supported:
            job["status"] = "failed"
            job["error"] = f"StrategyType='{strategy_type}' aun no conectado al motor (soportados: {list(supported)})"
            return

        # run_parallel reparte los simbolos entre procesos (CPU-bound, el
        # GIL no deja que threads ayuden aca) y aplica el capital de 3 slots
        # UNA sola vez sobre el total combinado -- mismo resultado que la
        # version secuencial, mucho mas rapido (corrida de 8 meses/425
        # simbolos: de ~100min a una fraccion de eso).
        result = engine.run_parallel(strategy_type, profile, symbols, start_ms, end_ms, progress_cb=progress_cb)
        result.pop("all_signals_raw", None)
        result.pop("shadow_signals", None)
        job["result"] = result
        job["status"] = "completed"

        # Persistencia -- cada corrida completada se guarda sola, nunca se
        # pisa una anterior (tabla backtest_runs, ver backtest/storage.py).
        try:
            start_date = job.get("start_date")
            end_date = job.get("end_date")
            run_id = storage.save_run(engine.conn, result, profile, start_date, end_date)
            job["run_id"] = run_id
        except Exception as e:
            # No fallar el job por un error de persistencia -- el resultado
            # ya esta disponible via /backtest/result/{job_id} igual.
            job["persist_error"] = str(e)
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
    _jobs[job_id] = {
        "status": "running", "done": 0, "total": len(symbols), "created_at": time.time(),
        "start_date": req.startDate, "end_date": req.endDate,
    }

    t = threading.Thread(target=_run_job, args=(job_id, profile, symbols, start_ms, end_ms), daemon=True)
    t.start()

    return {"jobId": job_id}


@app.get("/backtest/jobs/active")
def get_active_jobs():
    """
    Fallback de recuperacion de progreso cuando la UI no tiene NADA guardado
    en localStorage (ej. la corrida arranco antes de que existiera ese
    guardado, o el usuario abre la pantalla desde otro navegador/dispositivo)
    -- lista los jobs con status='running' para que el frontend se pueda
    reenganchar igual, sin depender exclusivamente del localStorage.
    """
    active = [
        {"jobId": jid, "kind": "run" if "start_date" in job else "sync",
         "done": job.get("done", 0), "total": job.get("total", 0)}
        for jid, job in _jobs.items() if job.get("status") == "running"
    ]
    return {"active": active}


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


@app.get("/backtest/symbols/top40")
def list_top40_symbols():
    return {"symbols": get_engine().top40_symbols()}


# ── Historial de corridas (backtest/storage.py) ──────────────────────────
@app.get("/backtest/runs")
def get_runs(strategyProfileId: Optional[str] = None):
    return {"runs": storage.list_runs(get_engine().conn, strategyProfileId)}


@app.get("/backtest/runs/{run_id}")
def get_run_detail(run_id: str):
    result = storage.get_run(get_engine().conn, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="corrida no encontrada")
    return result


# ── Sincronizacion de datos (backtest/data_sync.py) ──────────────────────
class SyncRequest(BaseModel):
    startDate: str
    endDate: str
    symbols: Optional[list[str]] = None


# ── VIRE: research aislado de relaciones estructurales ───────────────────
class InvariantResearchRequest(BaseModel):
    startDate: str
    endDate: str
    symbols: Optional[list[str]] = None
    maxPairs: int = 80
    minBars: int = 600
    minOosTrades: int = 8
    feeBpsPerLeg: float = 4.0
    slippageBpsPerLeg: float = 2.0
    perturbationBpsPerLeg: float = 3.0
    capitalPerTrade: float = 150.0


class FundingResearchRequest(BaseModel):
    startDate: str
    endDate: str
    capitalPerTrade: float = 150.0
    minOosTrades: int = 15


class OIResearchRequest(BaseModel):
    startDate: str
    endDate: str
    capitalPerTrade: float = 150.0
    minOosTrades: int = 30


class ForcedFlowResearchRequest(BaseModel):
    startDate: str
    endDate: str
    capitalPerTrade: float = 150.0
    minOosTrades: int = 30


class CrossVenueResearchRequest(BaseModel):
    startDate: str
    endDate: str
    capitalPerTrade: float = 150.0
    minOosTrades: int = 30


def _run_invariant_research(job_id: str, req: InvariantResearchRequest, symbols: list[str]):
    job = _jobs[job_id]
    try:
        # El motor lee solo SQLite histórico. No consulta perfiles, no llama
        # endpoints de ejecución y no puede crear una estrategia live.
        cfg = invariant_research.ResearchConfig(
            start_date=req.startDate, end_date=req.endDate, symbols=tuple(symbols),
            max_pairs=max(1, min(req.maxPairs, 500)), min_bars=max(100, req.minBars),
            min_oos_trades=max(1, req.minOosTrades), fee_bps_per_leg=req.feeBpsPerLeg,
            slippage_bps_per_leg=req.slippageBpsPerLeg,
            perturbation_bps_per_leg=req.perturbationBpsPerLeg,
            capital_per_trade=req.capitalPerTrade,
        )
        result = invariant_research.run_research(get_engine().conn, cfg)
        job["result"] = result
        job["done"] = result["summary"]["pairs_screened"]
        job["status"] = "completed"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.post("/research/invariants/run")
def run_invariant_research(req: InvariantResearchRequest):
    # VIRE owns its data contract. Do not route through the legacy top40
    # endpoint: its universe/table schema is unrelated to this research track.
    engine = get_engine()
    symbols = req.symbols or invariant_research.available_symbols(engine.conn, 400)
    if len(symbols) < 2:
        raise HTTPException(status_code=400, detail="Se necesitan al menos dos símbolos con datos históricos")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "done": 0,
                     "total": min(req.maxPairs, len(symbols) * (len(symbols) - 1) // 2),
                     "created_at": time.time(), "kind": "invariant_research"}
    threading.Thread(target=_run_invariant_research, args=(job_id, req, symbols), daemon=True).start()
    return {"jobId": job_id}


@app.get("/research/invariants/runs")
def invariant_research_runs(limit: int = 20):
    return {"runs": invariant_research.list_runs(get_engine().conn, max(1, min(limit, 100)))}


@app.get("/research/invariants/runs/{run_id}")
def invariant_research_run(run_id: str):
    result = invariant_research.get_run(get_engine().conn, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Corrida de research no encontrada")
    return result


@app.get("/research/strategies")
def invariant_research_strategies(limit: int = 100):
    """Unified VIRE hypothesis registry; never exposes execution profiles.

    Each vertical keeps its immutable native ledger.  This endpoint projects
    those ledgers into one audit registry without copying them into profiles
    or treating a rejected experiment as a tradable strategy.
    """
    conn = get_engine().conn
    strategies = invariant_research.list_strategies(conn, 500)
    verticals = (
        funding_research.list_runs(conn, 100),
        oi_research.list_runs(conn, 100),
        forced_flow_research.list_runs(conn, 100),
        cross_venue_research.list_runs(conn, 100),
    )
    for runs in verticals:
        for run in runs:
            strategy = run.get("strategy")
            if not strategy:
                continue  # Old ledgers remain visible in their own vertical.
            strategies.append({"strategy_id": strategy["id"], "name": strategy["name"],
                               "family": strategy["family"], "version": strategy["version"],
                               "thesis": strategy["thesis"], "first_seen": run["created_at"],
                               "last_seen": run["created_at"], "status": run["status"], "candidate": run})
    unique = {item["strategy_id"]: item for item in strategies}
    ordered = sorted(unique.values(), key=lambda item: item["last_seen"], reverse=True)
    return {"strategies": ordered[:max(1, min(limit, 500))]}


def _run_funding_research(job_id: str, req: FundingResearchRequest):
    try:
        cfg = funding_research.FundingConfig(
            start_ms=invariant_research._ms(req.startDate), end_ms=invariant_research._ms(req.endDate),
            capital=req.capitalPerTrade, min_oos_trades=max(1, req.minOosTrades),
        )
        _jobs[job_id]["result"] = funding_research.run(get_engine().conn, cfg)
        _jobs[job_id]["done"] = 1
        _jobs[job_id]["status"] = "completed"
    except Exception as exc:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)


@app.post("/research/funding/run")
def run_funding_research(req: FundingResearchRequest):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "done": 0, "total": 1, "kind": "funding_research", "created_at": time.time()}
    threading.Thread(target=_run_funding_research, args=(job_id, req), daemon=True).start()
    return {"jobId": job_id}


@app.get("/research/funding/result/{job_id}")
def funding_research_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Corrida funding no encontrada")
    if job["status"] != "completed":
        return {"status": job["status"], "error": job.get("error")}
    return job["result"]


@app.get("/research/funding/runs")
def funding_research_runs(limit: int = 20):
    return {"runs": funding_research.list_runs(get_engine().conn, max(1, min(limit, 100)))}


def _run_oi_research(job_id: str, req: OIResearchRequest):
    try:
        cfg = oi_research.OIConfig(start_ms=invariant_research._ms(req.startDate), end_ms=invariant_research._ms(req.endDate), capital=req.capitalPerTrade, min_oos_trades=max(1, req.minOosTrades))
        _jobs[job_id]["result"] = oi_research.run(get_engine().conn, cfg)
        _jobs[job_id].update({"done": 1, "status": "completed"})
    except Exception as exc:
        _jobs[job_id].update({"status": "failed", "error": str(exc)})


@app.post("/research/oi/run")
def run_oi_research(req: OIResearchRequest):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "done": 0, "total": 1, "kind": "oi_research", "created_at": time.time()}
    threading.Thread(target=_run_oi_research, args=(job_id, req), daemon=True).start()
    return {"jobId": job_id}


@app.get("/research/oi/result/{job_id}")
def oi_research_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Corrida OI no encontrada")
    return job.get("result") if job["status"] == "completed" else {"status": job["status"], "error": job.get("error")}


@app.get("/research/oi/runs")
def oi_research_runs(limit: int = 20):
    return {"runs": oi_research.list_runs(get_engine().conn, max(1, min(limit, 100)))}


def _run_forced_flow_research(job_id: str, req: ForcedFlowResearchRequest):
    try:
        cfg = forced_flow_research.ForcedFlowConfig(
            start_ms=invariant_research._ms(req.startDate), end_ms=invariant_research._ms(req.endDate),
            capital=req.capitalPerTrade, min_oos_trades=max(1, req.minOosTrades),
        )
        _jobs[job_id]["result"] = forced_flow_research.run(get_engine().conn, cfg)
        _jobs[job_id].update({"done": 1, "status": "completed"})
    except Exception as exc:
        _jobs[job_id].update({"status": "failed", "error": str(exc)})


@app.post("/research/forced-flow/run")
def run_forced_flow_research(req: ForcedFlowResearchRequest):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "done": 0, "total": 1, "kind": "forced_flow_research", "created_at": time.time()}
    threading.Thread(target=_run_forced_flow_research, args=(job_id, req), daemon=True).start()
    return {"jobId": job_id}


@app.get("/research/forced-flow/result/{job_id}")
def forced_flow_research_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Corrida forced-flow no encontrada")
    return job.get("result") if job["status"] == "completed" else {"status": job["status"], "error": job.get("error")}


@app.get("/research/forced-flow/runs")
def forced_flow_research_runs(limit: int = 20):
    return {"runs": forced_flow_research.list_runs(get_engine().conn, max(1, min(limit, 100)))}


def _run_cross_venue_research(job_id: str, req: CrossVenueResearchRequest):
    try:
        cfg = cross_venue_research.CrossVenueConfig(start_ms=invariant_research._ms(req.startDate), end_ms=invariant_research._ms(req.endDate), capital=req.capitalPerTrade, min_oos_trades=max(1, req.minOosTrades))
        canonical = os.getenv("VIRE_CANONICAL_DB")
        source = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True) if canonical else None
        try:
            _jobs[job_id]["result"] = cross_venue_research.run(get_engine().conn, cfg, source)
        finally:
            if source: source.close()
        _jobs[job_id].update({"done": 1, "status": "completed"})
    except Exception as exc:
        _jobs[job_id].update({"status": "failed", "error": str(exc)})


@app.post("/research/cross-venue/run")
def run_cross_venue_research(req: CrossVenueResearchRequest):
    job_id = str(uuid.uuid4()); _jobs[job_id] = {"status":"running","done":0,"total":1,"kind":"cross_venue_research","created_at":time.time()}
    threading.Thread(target=_run_cross_venue_research,args=(job_id,req),daemon=True).start()
    return {"jobId":job_id}


@app.get("/research/cross-venue/runs")
def cross_venue_research_runs(limit: int = 20):
    return {"runs": cross_venue_research.list_runs(get_engine().conn, max(1, min(limit, 100)))}


@app.get("/research/liquidations/eligibility")
def liquidation_research_eligibility():
    return liquidation_research.assess(get_engine().conn, invariant_research.LIVE_RESEARCH_DB_PATH, os.getenv("VIRE_CANONICAL_DB"))


def _sync_job(job_id: str, symbols: list, start_ms: int, end_ms: int):
    job = _jobs[job_id]
    try:
        def progress_cb(done, total):
            job["done"] = done
            job["total"] = total

        summary = data_sync.sync_coverage(symbols, start_ms, end_ms, progress_cb=progress_cb)
        job["result"] = summary
        job["status"] = "completed"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.get("/backtest/data/coverage")
def data_coverage(startDate: str, endDate: str, symbols: Optional[str] = None):
    """symbols: coma-separado opcional, si se omite usa el watchlist completo ya cacheado."""
    sym_list = symbols.split(",") if symbols else get_engine().available_symbols()
    start_ms = int(datetime.strptime(startDate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(endDate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    gaps = data_sync.check_coverage(sym_list, start_ms, end_ms)
    total_gaps = sum(len(v) for table in gaps.values() for v in table.values())
    return {"gaps": gaps, "total_missing_symbol_days": total_gaps}


@app.post("/backtest/data/sync")
def data_sync_run(req: SyncRequest):
    sym_list = req.symbols or get_engine().available_symbols()
    start_ms = int(datetime.strptime(req.startDate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(req.endDate, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "done": 0, "total": 0, "created_at": time.time()}
    t = threading.Thread(target=_sync_job, args=(job_id, sym_list, start_ms, end_ms), daemon=True)
    t.start()
    return {"jobId": job_id}


# ── Laboratorio de estrategias (backtest/strategy_lab.py) ────────────────
# Lee directo de los .jsonl que escribe el proceso del laboratorio (corre
# aparte, `python -m backtest.strategy_lab`, en un loop infinito sin
# supervision). Solo lectura -- este endpoint nunca escribe ni toca el
# proceso del lab, así que se puede consultar sin riesgo mientras corre.
_LAB_DIR = os.path.dirname(__file__)
_LAB_FOUND_PATH = os.path.join(_LAB_DIR, "found_strategies.jsonl")
_LAB_TESTED_PATH = os.path.join(_LAB_DIR, "lab_tested_all.jsonl")
_LAB_PROGRESS_PATH = os.path.join(_LAB_DIR, "lab_progress.log")
_LAB_CURRENT_PATH = os.path.join(_LAB_DIR, "lab_current.json")


def _read_jsonl(path: str, limit: Optional[int] = None) -> list:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if limit:
        rows = rows[-limit:]
    return rows


@app.get("/lab/status")
def lab_status():
    """Ultima linea de progreso parseada + conteos reales de los archivos."""
    progress = None
    if os.path.exists(_LAB_PROGRESS_PATH):
        with open(_LAB_PROGRESS_PATH, encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f if l.strip()]
        if lines:
            progress = lines[-1]

    tested_count = sum(1 for _ in open(_LAB_TESTED_PATH, encoding="utf-8", errors="replace")) if os.path.exists(_LAB_TESTED_PATH) else 0
    found_count = sum(1 for _ in open(_LAB_FOUND_PATH, encoding="utf-8", errors="replace")) if os.path.exists(_LAB_FOUND_PATH) else 0

    # isRunning real: heartbeat de lab_current.json, escrito por
    # strategy_lab.py en CADA iteracion (no cada 10 como lab_progress.log).
    # El check anterior via psutil no servia -- este API corre en un
    # container Docker separado del proceso host que corre el lab, asi que
    # nunca lo veia (namespace distinto), siempre devolvia None/False.
    is_running = False
    heartbeat_age_sec = None
    if os.path.exists(_LAB_CURRENT_PATH):
        try:
            with open(_LAB_CURRENT_PATH, encoding="utf-8", errors="replace") as f:
                cur = json.load(f)
            hb = datetime.fromisoformat(cur["heartbeat"])
            heartbeat_age_sec = (datetime.now(timezone.utc) - hb).total_seconds()
            is_running = heartbeat_age_sec < 60
        except Exception:
            is_running = False

    return {
        "progressLine": progress,
        "testedCount": tested_count,
        "foundCount": found_count,
        "isRunning": is_running,
        "heartbeatAgeSec": round(heartbeat_age_sec, 1) if heartbeat_age_sec is not None else None,
    }


@app.get("/lab/current")
def lab_current():
    """Estrategia que se esta backtesteando AHORA MISMO (heartbeat en vivo)."""
    if not os.path.exists(_LAB_CURRENT_PATH):
        return {"available": False}
    try:
        with open(_LAB_CURRENT_PATH, encoding="utf-8", errors="replace") as f:
            cur = json.load(f)
    except Exception:
        return {"available": False}
    hb = datetime.fromisoformat(cur["heartbeat"])
    age_sec = (datetime.now(timezone.utc) - hb).total_seconds()
    return {
        "available": True,
        "isRunning": age_sec < 60,
        "heartbeatAgeSec": round(age_sec, 1),
        "tried": cur.get("tried"),
        "found": cur.get("found"),
        "currentLabel": cur.get("current_label"),
        "currentStrat": cur.get("current_strat"),
        "elapsedSec": cur.get("elapsed_sec"),
        "daysCovered": cur.get("days_covered"),
    }


@app.get("/lab/strategies/found")
def lab_strategies_found():
    """Las que pasaron TODOS los filtros (ambas mitades positivas, estables, >= umbral $/mes)."""
    rows = _read_jsonl(_LAB_FOUND_PATH)
    rows.sort(key=lambda r: r.get("result", {}).get("monthly", -999999), reverse=True)
    rows = _dedupe_by_strategy(rows)
    return {"strategies": rows}


def _canonical_strat_key(strat: dict) -> tuple:
    """
    Firma de los parametros que REALMENTE afectan la señal, ignorando los
    que el generador rellena con random pero detect_signal() nunca lee
    para ese entry_type (ma_pair fuera de ma_cross, rsi_thresh fuera de
    rsi_extreme, lookback fuera de level_sweep) -- antes del fix de
    2026-08-16 esto producia hasta 15 filas identicas en el Top 10 para
    la misma estrategia real. Se aplica en lectura para tambien deduplicar
    el historico ya acumulado con el generador viejo.
    """
    et = strat.get("entry_type")
    return (
        et,
        strat.get("tf_min"),
        strat.get("side"),
        strat.get("atr_sl_mult"),
        strat.get("rr_mult"),
        tuple(strat.get("ma_pair")) if et == "ma_cross" and strat.get("ma_pair") else None,
        strat.get("lookback") if et in ("level_sweep", "ma_pullback") else None,
        tuple(strat.get("rsi_thresh")) if et == "rsi_extreme" and strat.get("rsi_thresh") else None,
        strat.get("slope_min_pct") if et == "ma_pullback" else None,
        strat.get("volume_mult") if et == "ma_pullback" else None,
    )


def _dedupe_by_strategy(rows: list) -> list:
    seen = set()
    out = []
    for r in rows:
        key = _canonical_strat_key(r.get("strat", {}))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


@app.get("/lab/strategies/top")
def lab_strategies_top(limit: int = 100):
    """Top N por $/mes de TODAS las probadas (pasen o no el filtro estricto) -- panorama completo, sin duplicados funcionales."""
    rows = _read_jsonl(_LAB_TESTED_PATH)
    rows = [r for r in rows if not r.get("result", {}).get("insufficient_data")]
    rows.sort(key=lambda r: r.get("result", {}).get("monthly", -999999), reverse=True)
    rows = _dedupe_by_strategy(rows)
    return {"strategies": rows[:limit]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
