"""Cola persistente, local y explícitamente sólo-de-investigación.

No genera candidatos, no arranca evolutionary_lab y no conoce producción. Sólo
acepta revisiones 1 ya materializadas y verificadas por LOOP_PROTOCOL, y las
entrega a ``run_autonomous`` exactamente una vez por lease.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import json
import os
import sqlite3
import time
import uuid
import hashlib
from contextlib import contextmanager
from pathlib import Path

from research_loop import run_autonomous, verify_revision


PENDING, RUNNING, IMPROVED, DISCARDED, INVALID, FAILED = (
    "PENDING", "RUNNING", "IMPROVED", "DISCARDED", "INVALID", "FAILED")
TERMINAL = {IMPROVED, DISCARDED, INVALID, FAILED}
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "research_queue.db"
WORKER_RSS_BYTES = 7 * 1024**3
SYSTEM_RESERVE_BYTES = 6 * 1024**3


def utc_ms() -> int:
    return int(time.time() * 1000)


def available_memory_bytes() -> int | None:
    if os.name != "nt":
        return None
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    status = Status(); status.length = ctypes.sizeof(status)
    return int(status.available) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None


def safe_worker_limit(requested: int = 3, available_bytes: int | None = None) -> dict:
    """Límite duro por memoria libre; nunca promete 2 workers sin margen."""
    available = available_memory_bytes() if available_bytes is None else available_bytes
    if available is None:
        allowed = 1
    else:
        allowed = max(1, (available - SYSTEM_RESERVE_BYTES) // WORKER_RSS_BYTES)
    return {"requested": int(requested), "allowed": min(int(requested), int(allowed)),
            "available_bytes": available, "worker_rss_bytes": WORKER_RSS_BYTES,
            "system_reserve_bytes": SYSTEM_RESERVE_BYTES}


class ResearchQueue:
    def __init__(self, path: str | os.PathLike = DEFAULT_DB):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS research_queue (
                candidate_id TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                catalog_path TEXT NOT NULL,
                funding_db TEXT,
                status TEXT NOT NULL,
                enqueued_at_ms INTEGER NOT NULL,
                started_at_ms INTEGER,
                finished_at_ms INTEGER,
                worker_id TEXT,
                result_status TEXT,
                result_json TEXT,
                error TEXT
            )""")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def enqueue(self, root, candidate_id: str, catalog_path, funding_db=None) -> dict:
        root = Path(root).resolve(); revision = root / candidate_id / "1"
        # El contrato formal es gate de admisión, no una convención informal.
        verify_revision(revision)
        with self.connection() as conn:
            conn.execute("""INSERT INTO research_queue(candidate_id,root,catalog_path,funding_db,status,enqueued_at_ms)
                VALUES(?,?,?,?,?,?) ON CONFLICT(candidate_id) DO NOTHING""",
                (candidate_id, str(root), str(Path(catalog_path).resolve()),
                 str(Path(funding_db).resolve()) if funding_db else None, PENDING, utc_ms()))
        return self.get(candidate_id)

    def get(self, candidate_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM research_queue WHERE candidate_id=?", (candidate_id,)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict]:
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM research_queue ORDER BY enqueued_at_ms,candidate_id")]

    def claim(self, worker_id: str) -> dict | None:
        """Claim atómico: dos procesos no pueden ejecutar el mismo candidato."""
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM research_queue WHERE status=? ORDER BY enqueued_at_ms,candidate_id LIMIT 1", (PENDING,)).fetchone()
            if row is None:
                conn.execute("COMMIT"); return None
            changed = conn.execute("UPDATE research_queue SET status=?,started_at_ms=?,worker_id=?,error=NULL WHERE candidate_id=? AND status=?",
                                   (RUNNING, utc_ms(), worker_id, row["candidate_id"], PENDING)).rowcount
            conn.execute("COMMIT")
        return self.get(row["candidate_id"]) if changed else None

    def complete(self, candidate_id: str, history: dict):
        raw = json.dumps(history, sort_keys=True)
        status = IMPROVED if history.get("status") == "IMPROVED" else (INVALID if history.get("status") == "INVALID" else DISCARDED)
        with self.connection() as conn:
            conn.execute("UPDATE research_queue SET status=?,finished_at_ms=?,result_status=?,result_json=? WHERE candidate_id=? AND status=?",
                         (status, utc_ms(), history.get("status"), raw, candidate_id, RUNNING))

    def fail(self, candidate_id: str, error: str):
        with self.connection() as conn:
            conn.execute("UPDATE research_queue SET status=?,finished_at_ms=?,error=? WHERE candidate_id=? AND status=?",
                         (FAILED, utc_ms(), error[:4000], candidate_id, RUNNING))


def clone_seed_revision(source_root, source_candidate_id: str, destination_root,
                        destination_candidate_id: str,
                        provenance_key: str = "queue_e2e_provenance") -> Path:
    """Clona sólo revisión 1 para una E2E sin alterar evidencia inmutable.

    Las entradas permanecen byte a byte idénticas; el manifiesto conserva la
    procedencia y recibe un nuevo id, imprescindible porque la cola deduplica
    por candidato y el orquestador creará revisiones hijas nuevas.
    """
    source = Path(source_root).resolve() / source_candidate_id / "1"
    manifest, _entries, _fingerprint = verify_revision(source)
    destination = Path(destination_root).resolve() / destination_candidate_id / "1"
    if destination.exists():
        raise FileExistsError(f"destino inmutable ya existe: {destination}")
    destination.mkdir(parents=True)
    payload = (source / "entries.jsonl").read_bytes()
    (destination / "entries.jsonl").write_bytes(payload)
    cloned = dict(manifest)
    cloned["candidate_id"] = destination_candidate_id
    cloned[provenance_key] = {
        "source_candidate_id": source_candidate_id,
        "source_entries_sha256": hashlib.sha256(payload).hexdigest(),
    }
    (destination / "candidate.json").write_text(json.dumps(cloned, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    verify_revision(destination)
    return destination


def _run_claim(db_path: str, worker_id: str) -> dict | None:
    queue = ResearchQueue(db_path); job = queue.claim(worker_id)
    if job is None:
        return None
    try:
        history = run_autonomous(job["root"], job["candidate_id"], job["catalog_path"], job["funding_db"])
        queue.complete(job["candidate_id"], history)
        snapshot = history.get("snapshot_path")
        positive_improved = False
        if history.get("status") == "IMPROVED" and snapshot:
            diagnosis = json.loads((Path(snapshot) / "diagnosis.json").read_text(encoding="utf8"))
            tv = diagnosis.get("train_validation", {}).get("net_expectancy_pct")
            oos = diagnosis.get("oos_once", {}).get("net_expectancy_pct")
            positive_improved = tv is not None and oos is not None and tv > 0 and oos > 0
        return {"candidate_id": job["candidate_id"], "status": history.get("status"),
                "positive_improved": positive_improved}
    except Exception as exc:
        queue.fail(job["candidate_id"], repr(exc))
        return {"candidate_id": job["candidate_id"], "status": FAILED, "error": repr(exc)}


def drain(db_path: str | os.PathLike = DEFAULT_DB, requested_workers: int = 3,
          once: bool = False, stop_on_positive_improved: bool = False) -> list[dict]:
    """Vacía candidatos pendientes; workers aislados y limitados por memoria.

    ``stop_on_positive_improved`` deja intactos los trabajos restantes sólo
    cuando una mejora pasa TV y OOS con expectancy neta estrictamente positiva.
    """
    plan = safe_worker_limit(requested_workers)
    workers = 1 if once else plan["allowed"]
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        while True:
            futures = [pool.submit(_run_claim, str(db_path), f"queue-{os.getpid()}-{uuid.uuid4().hex[:8]}") for _ in range(workers)]
            batch = [future.result() for future in futures]
            claimed = [item for item in batch if item]
            results.extend(claimed)
            if stop_on_positive_improved and any(item.get("positive_improved") for item in claimed):
                break
            if once or not claimed:
                break
    return results


def main():
    parser = argparse.ArgumentParser(description="Consumidor persistente Research→Máquina; jamás activa producción.")
    parser.add_argument("--db", default=str(DEFAULT_DB)); parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--once", action="store_true"); parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop-on-positive-improved", action="store_true",
                        help="detiene la cola sólo tras IMPROVED con TV y OOS netos > 0")
    parser.add_argument("--enqueue", metavar="CANDIDATE_ID")
    parser.add_argument("--root", help="raíz research_loop que contiene <candidate>/1")
    parser.add_argument("--catalog", help="IMPROVEMENT_FAMILIES.md canónico")
    parser.add_argument("--funding-db")
    args = parser.parse_args(); queue = ResearchQueue(args.db)
    if args.enqueue:
        if not args.root or not args.catalog:
            parser.error("--enqueue requiere --root y --catalog")
        print(json.dumps(queue.enqueue(args.root, args.enqueue, args.catalog, args.funding_db), indent=2)); return
    if args.status:
        print(json.dumps({"worker_plan": safe_worker_limit(args.workers), "jobs": queue.list()}, indent=2)); return
    print(json.dumps({"worker_plan": safe_worker_limit(args.workers),
                      "results": drain(args.db, args.workers, args.once,
                                       args.stop_on_positive_improved)}, indent=2))


if __name__ == "__main__":
    main()
