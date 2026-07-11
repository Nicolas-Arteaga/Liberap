"""
BUCKET CALIBRATOR — recalibración dinámica de prioridad por rango de score.

Reemplaza el enfoque de "poner un umbral fijo a mano en el código o en el
perfil" por un multiplicador que se recalcula solo, directamente contra
Postgres (la fuente de verdad real), cada N horas.

Idea: para cada estrategia, algunos rangos de score de entrada (confluence_score)
ganan sistemáticamente más que otros — no necesariamente "cuanto más alto,
mejor". En vez de que un humano mire un reporte y escriba un número fijo,
este módulo:

  1. Lee todos los trades cerrados (Win/Loss) de cada estrategia desde Postgres.
  2. Agrupa por rango de score (bucket).
  3. Calcula el winrate de cada bucket relativo al winrate promedio de ESA
     estrategia (no un umbral absoluto global).
  4. Convierte esa relación en un multiplicador acotado — >1 prioriza,
     <1 desprioriza, nunca vetea.
  5. Si un bucket no tiene muestra mínima (MIN_SAMPLE_SIZE), no se le asigna
     multiplicador — queda neutro (1.0), o sea: sin efecto hasta que haya
     evidencia real.

No es un veto ni un filtro hardcodeado: es un peso de ranking que compite
contra otros candidatos por el mismo slot dentro de la misma estrategia.
Se recalcula automáticamente — ver `should_recalculate()` / `recalculate_and_save()`,
llamado desde el loop principal del agente cada BUCKET_CALIBRATOR_INTERVAL_HOURS.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("BUCKET-CALIBRATOR")

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - degradación segura si falta el driver
    psycopg2 = None

# ── Configuración ────────────────────────────────────────────────────────────
MIN_SAMPLE_SIZE = int(os.getenv("BUCKET_CALIBRATOR_MIN_SAMPLE", "30"))
MULTIPLIER_MIN = float(os.getenv("BUCKET_CALIBRATOR_MULT_MIN", "0.5"))
MULTIPLIER_MAX = float(os.getenv("BUCKET_CALIBRATOR_MULT_MAX", "1.5"))
RECALC_INTERVAL_HOURS = float(os.getenv("BUCKET_CALIBRATOR_INTERVAL_HOURS", "24"))

# Bordes de los buckets de score (confluence_score, 0-100+). Fijos por ahora;
# si en el futuro conviene que también se autoajusten, este es el lugar.
SCORE_BUCKET_EDGES = [0, 60, 70, 80, 90, 101]

# Estrategias cuya lógica de entrada cambió de raíz en una fecha reciente
# (Scalping Clone dejó de ser espejo de Standard Scalping; Arrow Reversal pasó
# de Nexus/Nexus5 genérico a arrow_peak exclusivo, ambas el 2026-07-09).
# Los trades anteriores a ese cambio pertenecen a un comportamiento que ya no
# existe — se descartan de la calibración hasta que cada una junte su propia
# muestra bajo la lógica nueva. No es una exclusión permanente: en cuanto haya
# suficiente historia posterior al cutoff, esta entrada deja de tener efecto
# por sí sola (el filtro de fecha nunca vuelve a excluir nada).
STRATEGY_DATA_CUTOFF_UTC = {
    "00000000-0000-0000-0000-000000000001": "2026-07-09",  # Scalping Clone
    "3a222379-a3b4-5fee-aa9d-98d865ea9509": "2026-07-09",  # Arrow Reversal
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MULTIPLIERS_FILE = os.path.join(DATA_DIR, "score_bucket_multipliers.json")

os.makedirs(DATA_DIR, exist_ok=True)


def _pg_connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        dbname=os.getenv("POSTGRES_DB", "Verge"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        connect_timeout=10,
    )


def _bucket_for_score(score: float) -> Optional[tuple]:
    for i in range(len(SCORE_BUCKET_EDGES) - 1):
        lo, hi = SCORE_BUCKET_EDGES[i], SCORE_BUCKET_EDGES[i + 1]
        if lo <= score < hi:
            return (lo, hi)
    return None


def recalculate_and_save() -> dict:
    """
    Lee Postgres, recalcula todos los multiplicadores vigentes y los persiste
    en MULTIPLIERS_FILE. Devuelve el payload calculado (o {} si no pudo).
    """
    if psycopg2 is None:
        logger.warning("[BUCKET-CALIBRATOR] psycopg2 no disponible — se salta el recálculo.")
        return {}

    try:
        conn = _pg_connect()
    except Exception as e:
        logger.warning(f"[BUCKET-CALIBRATOR] No se pudo conectar a Postgres: {e}")
        return {}

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            '''
            SELECT
                "StrategyProfileId" AS strategy_id,
                "Status" AS status,
                "RealizedPnl" AS realized_pnl,
                "OpenedAt" AS opened_at,
                ("AgentDecisionJson"::json->'candidate'->>'confluence_score')::numeric AS score
            FROM "SimulatedTrades"
            WHERE "Status" IN (1, 2)
              AND "AgentDecisionJson" IS NOT NULL
              AND "StrategyProfileId" IS NOT NULL
            '''
        )
        rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"[BUCKET-CALIBRATOR] Error consultando Postgres: {e}")
        conn.close()
        return {}
    finally:
        conn.close()

    # ── Agrupar por estrategia (respetando el cutoff de datos obsoletos) ──
    by_strategy: dict = {}
    skipped_stale = 0
    for r in rows:
        sid = str(r["strategy_id"])
        score = r["score"]
        if score is None:
            continue
        cutoff = STRATEGY_DATA_CUTOFF_UTC.get(sid)
        if cutoff and r["opened_at"] and r["opened_at"].date().isoformat() < cutoff:
            skipped_stale += 1
            continue
        by_strategy.setdefault(sid, []).append(
            {"status": r["status"], "pnl": float(r["realized_pnl"] or 0), "score": float(score)}
        )

    if skipped_stale:
        logger.info(f"[BUCKET-CALIBRATOR] {skipped_stale} trade(s) descartado(s) por cutoff de datos obsoletos.")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "min_sample_size": MIN_SAMPLE_SIZE,
        "multiplier_range": [MULTIPLIER_MIN, MULTIPLIER_MAX],
        "strategies": {},
    }

    for sid, trades in by_strategy.items():
        total_n = len(trades)
        if total_n == 0:
            continue
        overall_wins = sum(1 for t in trades if t["status"] == 1)
        overall_wr = overall_wins / total_n

        buckets_out = []
        for i in range(len(SCORE_BUCKET_EDGES) - 1):
            lo, hi = SCORE_BUCKET_EDGES[i], SCORE_BUCKET_EDGES[i + 1]
            bucket_trades = [t for t in trades if lo <= t["score"] < hi]
            n = len(bucket_trades)
            if n < MIN_SAMPLE_SIZE:
                continue  # sin evidencia suficiente — no se reporta, queda neutro (1.0) en tiempo de uso

            wins = sum(1 for t in bucket_trades if t["status"] == 1)
            wr = wins / n
            avg_pnl = sum(t["pnl"] for t in bucket_trades) / n

            if overall_wr > 0:
                raw_multiplier = wr / overall_wr
            else:
                raw_multiplier = 1.0
            multiplier = max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, raw_multiplier))

            buckets_out.append({
                "score_min": lo,
                "score_max": hi,
                "n": n,
                "winrate": round(wr, 4),
                "avg_pnl": round(avg_pnl, 4),
                "multiplier": round(multiplier, 4),
            })

        if buckets_out:
            payload["strategies"][sid] = {
                "overall_n": total_n,
                "overall_winrate": round(overall_wr, 4),
                "buckets": buckets_out,
            }

    try:
        with open(MULTIPLIERS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.warning(
            f"[BUCKET-CALIBRATOR] Recalculado: {len(payload['strategies'])} estrategia(s) con "
            f"buckets calibrados (piso de muestra={MIN_SAMPLE_SIZE}). Archivo: {MULTIPLIERS_FILE}"
        )
    except Exception as e:
        logger.warning(f"[BUCKET-CALIBRATOR] No se pudo escribir {MULTIPLIERS_FILE}: {e}")

    return payload


def should_recalculate() -> bool:
    """True si nunca se calculó o si pasaron >= RECALC_INTERVAL_HOURS desde la última vez."""
    if not os.path.isfile(MULTIPLIERS_FILE):
        return True
    try:
        with open(MULTIPLIERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        gen_at = datetime.fromisoformat(data.get("generated_at_utc", "").replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - gen_at).total_seconds() / 3600.0
        return age_hours >= RECALC_INTERVAL_HOURS
    except Exception:
        return True


_cache: Optional[dict] = None


def load_multipliers(force_reload: bool = False) -> dict:
    """Carga (con cache en memoria) el archivo de multiplicadores vigente."""
    global _cache
    if _cache is not None and not force_reload:
        return _cache
    if not os.path.isfile(MULTIPLIERS_FILE):
        _cache = {}
        return _cache
    try:
        with open(MULTIPLIERS_FILE, encoding="utf-8") as f:
            _cache = json.load(f)
    except Exception as e:
        logger.warning(f"[BUCKET-CALIBRATOR] Error leyendo {MULTIPLIERS_FILE}: {e}")
        _cache = {}
    return _cache


def get_multiplier(strategy_id, score) -> float:
    """
    Devuelve el multiplicador vigente para (estrategia, score). 1.0 (neutro)
    si la estrategia no tiene calibración todavía, o si el bucket de ese score
    no juntó muestra suficiente aún.
    """
    if strategy_id is None or score is None:
        return 1.0
    data = load_multipliers()
    strat = data.get("strategies", {}).get(str(strategy_id))
    if not strat:
        return 1.0
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return 1.0
    for b in strat.get("buckets", []):
        if b["score_min"] <= score_f < b["score_max"]:
            return float(b["multiplier"])
    return 1.0
