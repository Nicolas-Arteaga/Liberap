"""Persistencia y cálculo causal de funding histórico USDⓈ-M.

Este módulo es deliberadamente independiente de ``agent/funding_rates.py``:
aquél observa presión reciente para el agente vivo; éste conserva settlements
históricos para contabilidad reproducible del laboratorio.  Nunca escribe en
StrategyProfiles, Scan Ledger ni en el proceso del agente.
"""
from __future__ import annotations

import os
import json
import bisect
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BINANCE_USDM = "binance_usdm"
SETTLEMENT_RATE = "settlement_rate"
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "funding_history.db"


@dataclass(frozen=True)
class FundingAccrual:
    status: str
    cashflow_usdt: float | None
    return_pct: float | None
    event_count: int
    events: tuple[dict, ...]
    coverage_reasons: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.status == "FUNDING_COVERAGE_COMPLETE"


def _side_is_short(side: object) -> bool:
    if isinstance(side, str):
        return side.strip().upper() in {"SHORT", "SELL", "1"}
    return int(side) == 1


class FundingStore:
    """SQLite/WAL, igual al patrón de ``kline_cache.py`` pero separado del live cache."""

    def __init__(self, db_path: str | os.PathLike = DEFAULT_DB):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._state_cache: dict[tuple[str, str, str], dict | None] = {}
        self._event_cache: dict[tuple[str, str, str], tuple[list[int], list[dict]]] = {}
        # Estado y huecos dependen sólo del símbolo/backfill; reutilizarlos
        # evita recalcular la serie completa de settlements por cada trade.
        self._coverage_base_cache: dict[tuple[str, str, str], dict] = {}
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _connection(self):
        """Commit/rollback y cierre explícito: crucial para SQLite en Windows."""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS historical_funding_events (
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    funding_time_ms INTEGER NOT NULL,
                    rate_type TEXT NOT NULL,
                    funding_rate REAL NOT NULL,
                    mark_price REAL,
                    source TEXT NOT NULL,
                    ingested_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (venue, symbol, funding_time_ms, rate_type)
                );
                CREATE INDEX IF NOT EXISTS idx_historical_funding_lookup
                    ON historical_funding_events(venue, symbol, rate_type, funding_time_ms);

                CREATE TABLE IF NOT EXISTS funding_backfill_state (
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    rate_type TEXT NOT NULL,
                    requested_start_ms INTEGER NOT NULL,
                    requested_end_ms INTEGER NOT NULL,
                    next_cursor_ms INTEGER NOT NULL,
                    last_funding_time_ms INTEGER,
                    completed_at_ms INTEGER,
                    last_error TEXT,
                    updated_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (venue, symbol, rate_type)
                );
                CREATE TABLE IF NOT EXISTS funding_sign_validation (
                    venue TEXT PRIMARY KEY,
                    validated_at_ms INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL,
                    validated INTEGER NOT NULL,
                    result_json TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(historical_funding_events)")}
            if "mark_price" not in columns:
                conn.execute("ALTER TABLE historical_funding_events ADD COLUMN mark_price REAL")

    def state(self, venue: str, symbol: str, rate_type: str = SETTLEMENT_RATE) -> dict | None:
        key = (venue, symbol, rate_type)
        if key in self._state_cache:
            cached = self._state_cache[key]
            return dict(cached) if cached else None
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM funding_backfill_state WHERE venue=? AND symbol=? AND rate_type=?",
                               (venue, symbol, rate_type)).fetchone()
        result = dict(row) if row else None
        self._state_cache[key] = result
        return dict(result) if result else None

    def _invalidate(self, venue: str, symbol: str, rate_type: str = SETTLEMENT_RATE) -> None:
        key = (venue, symbol, rate_type)
        self._state_cache.pop(key, None)
        self._event_cache.pop(key, None)
        self._coverage_base_cache.pop(key, None)

    def begin(self, venue: str, symbol: str, start_ms: int, end_ms: int,
              rate_type: str = SETTLEMENT_RATE) -> int:
        """Devuelve cursor reanudable; nunca retrocede ni vuelve a pedir páginas persistidas."""
        current = self.state(venue, symbol, rate_type)
        if current:
            # Un backfill previo puede haber empezado antes que una nueva
            # auditoría. Esa cobertura es un superconjunto válido: se conserva
            # el inicio más antiguo y sólo se extiende el cursor hacia adelante.
            # Lo que no es seguro es pedir un comienzo anterior al ya
            # registrado, porque requeriría retroceder el cursor y volver a
            # consultar páginas ya cerradas.
            if int(current["requested_start_ms"]) > start_ms:
                raise ValueError("el rango solicitado empieza antes del backfill ya iniciado; use una base nueva o ejecute un backfill retroactivo explícito")
            if current["completed_at_ms"] and current["requested_end_ms"] >= end_ms:
                return end_ms + 1
            cursor = max(int(current["next_cursor_ms"]), start_ms)
            with self._connection() as conn:
                conn.execute("UPDATE funding_backfill_state SET requested_end_ms=?, completed_at_ms=NULL, updated_at_ms=? WHERE venue=? AND symbol=? AND rate_type=?",
                             (end_ms, int(time.time() * 1000), venue, symbol, rate_type))
            self._invalidate(venue, symbol, rate_type)
            return cursor
        with self._connection() as conn:
            conn.execute("""INSERT INTO funding_backfill_state
                (venue,symbol,rate_type,requested_start_ms,requested_end_ms,next_cursor_ms,updated_at_ms)
                VALUES (?,?,?,?,?,?,?)""", (venue, symbol, rate_type, start_ms, end_ms, start_ms, int(time.time() * 1000)))
        self._invalidate(venue, symbol, rate_type)
        return start_ms

    def persist_page(self, venue: str, symbol: str, records: Iterable[dict], cursor_after: int,
                     rate_type: str = SETTLEMENT_RATE, source: str = "binance_usdm_funding_rate_rest") -> int:
        rows = list(records)
        now_ms = int(time.time() * 1000)
        with self._connection() as conn:
            conn.executemany("""INSERT INTO historical_funding_events
                (venue,symbol,funding_time_ms,rate_type,funding_rate,mark_price,source,ingested_at_ms)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(venue,symbol,funding_time_ms,rate_type) DO UPDATE SET
                  funding_rate=excluded.funding_rate, mark_price=excluded.mark_price,
                  source=excluded.source, ingested_at_ms=excluded.ingested_at_ms""",
                [(venue, symbol, int(row["fundingTime"]), rate_type, float(row["fundingRate"]),
                  float(row["markPrice"]) if row.get("markPrice") is not None else None, source, now_ms) for row in rows])
            last = max((int(row["fundingTime"]) for row in rows), default=None)
            conn.execute("""UPDATE funding_backfill_state
                SET next_cursor_ms=?, last_funding_time_ms=COALESCE(?,last_funding_time_ms),
                    last_error=NULL, updated_at_ms=? WHERE venue=? AND symbol=? AND rate_type=?""",
                (cursor_after, last, now_ms, venue, symbol, rate_type))
        self._invalidate(venue, symbol, rate_type)
        return len(rows)

    def record_error(self, venue: str, symbol: str, message: str, rate_type: str = SETTLEMENT_RATE) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE funding_backfill_state SET last_error=?, updated_at_ms=? WHERE venue=? AND symbol=? AND rate_type=?",
                         (message[:1000], int(time.time() * 1000), venue, symbol, rate_type))
        self._invalidate(venue, symbol, rate_type)

    def complete(self, venue: str, symbol: str, rate_type: str = SETTLEMENT_RATE) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE funding_backfill_state SET completed_at_ms=?, updated_at_ms=? WHERE venue=? AND symbol=? AND rate_type=?",
                         (int(time.time() * 1000), int(time.time() * 1000), venue, symbol, rate_type))
        self._invalidate(venue, symbol, rate_type)

    def events(self, venue: str, symbol: str, start_ms: int, end_ms: int,
               rate_type: str = SETTLEMENT_RATE) -> list[dict]:
        key = (venue, symbol, rate_type)
        cached = self._event_cache.get(key)
        if cached is None:
            with self._connection() as conn:
                rows = conn.execute("""SELECT funding_time_ms, funding_rate, mark_price FROM historical_funding_events
                    WHERE venue=? AND symbol=? AND rate_type=? ORDER BY funding_time_ms""",
                                    (venue, symbol, rate_type)).fetchall()
            times = [int(row["funding_time_ms"]) for row in rows]
            events = [{"funding_time_ms": int(row["funding_time_ms"]), "funding_rate": float(row["funding_rate"]),
                       "mark_price": float(row["mark_price"]) if row["mark_price"] is not None else None} for row in rows]
            cached = (times, events)
            self._event_cache[key] = cached
        times, all_events = cached
        lo, hi = bisect.bisect_right(times, start_ms), bisect.bisect_right(times, end_ms)
        return all_events[lo:hi]

    def _all_times(self, venue: str, symbol: str, rate_type: str) -> list[int]:
        key = (venue, symbol, rate_type)
        if key not in self._event_cache:
            self.events(venue, symbol, -1, 2**63 - 1, rate_type)
        return self._event_cache[key][0]

    @staticmethod
    def _gaps(times: list[int]) -> list[tuple[int, int]]:
        """Huecos conservadores, inferidos de la cadencia observada del propio símbolo.

        No codifica una regla de 8 horas. Binance puede cambiar la cadencia de un
        contrato (por ejemplo, de 1 h a 8 h); un cambio sostenido de cadencia no
        es un hueco. Se marca solamente un salto aislado que excede de forma
        material a sus intervalos vecinos: una página ausente produce ese patrón,
        mientras que una nueva cadencia persiste a ambos lados del cambio.
        """
        if len(times) < 3:
            return []
        deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
        gaps = []
        for index, delta in enumerate(deltas):
            # Hasta dos vecinos de cada lado permiten validar transiciones como
            # 1 h -> 8 h sin asumir cuál de las dos es la cadencia correcta.
            neighbors = deltas[max(0, index - 2):index] + deltas[index + 1:index + 3]
            if not neighbors:
                continue
            reference = max(neighbors)
            # Un intervalo perdido duplica (o más) la cadencia local. 1.75 deja
            # margen al jitter de milisegundos del endpoint, pero no inventa un
            # calendario fijo para el contrato.
            if delta > 1.75 * reference:
                gaps.append((times[index], times[index + 1]))
        return gaps

    def coverage(self, venue: str, symbol: str, start_ms: int, end_ms: int,
                 rate_type: str = SETTLEMENT_RATE) -> dict:
        key = (venue, symbol, rate_type)
        base = self._coverage_base_cache.get(key)
        if base is None:
            times = self._all_times(venue, symbol, rate_type)
            base = {
                "state": self.state(venue, symbol, rate_type),
                "times": times,
                "gaps": self._gaps(times),
            }
            self._coverage_base_cache[key] = base
        state, times = base["state"], base["times"]
        reasons: list[str] = []
        if not state or not state["completed_at_ms"] or state["requested_start_ms"] > start_ms or state["requested_end_ms"] < end_ms:
            reasons.append("BACKFILL_NOT_COMPLETE")
        # La cobertura primaria es la ventana que respondió el endpoint, no
        # el primer/último settlement observado: puede no haber settlement
        # dentro de los bordes de una ventana válidamente descargada.
        if not state or state["requested_start_ms"] > start_ms or state["requested_end_ms"] < end_ms:
            reasons.append("OUTSIDE_REQUESTED_COVERAGE")
        gaps = [(a, b) for a, b in base["gaps"] if a < end_ms and b > start_ms]
        if gaps:
            reasons.append("OBSERVED_EVENT_GAP")
        return {"complete": not reasons, "reasons": reasons, "first_funding_time_ms": times[0] if times else None,
                "last_funding_time_ms": times[-1] if times else None, "event_count": len(times),
                "gaps": [{"from_ms": a, "to_ms": b} for a, b in gaps], "state": state}

    def coverage_report(self, venue: str, symbols: Iterable[str], rate_type: str = SETTLEMENT_RATE) -> dict:
        out = {}
        for symbol in symbols:
            times = self._all_times(venue, symbol, rate_type)
            gaps = self._gaps(times)
            state = self.state(venue, symbol, rate_type)
            out[symbol] = {"events": len(times), "first_funding_time_ms": times[0] if times else None,
                           "last_funding_time_ms": times[-1] if times else None,
                           "observed_gaps": [{"from_ms": a, "to_ms": b} for a, b in gaps],
                           "backfill_completed": bool(state and state["completed_at_ms"]), "state": state}
        return out

    def record_sign_validation(self, venue: str, result: dict) -> None:
        """Persiste la evidencia de Income History que habilita cálculo neto."""
        with self._connection() as conn:
            conn.execute("""INSERT INTO funding_sign_validation
                (venue,validated_at_ms,sample_count,validated,result_json) VALUES (?,?,?,?,?)
                ON CONFLICT(venue) DO UPDATE SET validated_at_ms=excluded.validated_at_ms,
                  sample_count=excluded.sample_count, validated=excluded.validated,
                  result_json=excluded.result_json""",
                (venue, int(time.time() * 1000), int(result.get("checked", 0)),
                 int(bool(result.get("validated"))), json.dumps(result, sort_keys=True)))

    def sign_validation(self, venue: str = BINANCE_USDM) -> dict | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM funding_sign_validation WHERE venue=?", (venue,)).fetchone()
        return dict(row) if row else None

    def sign_validated(self, venue: str = BINANCE_USDM) -> bool:
        row = self.sign_validation(venue)
        return bool(row and row["validated"] and row["sample_count"] > 0)

    def sign_validation_result(self, venue: str = BINANCE_USDM) -> dict | None:
        row = self.sign_validation(venue)
        return json.loads(row["result_json"]) if row else None

    def accrued_funding(self, position: dict, open_ms: int, close_ms: int,
                        venue: str = BINANCE_USDM, rate_type: str = SETTLEMENT_RATE) -> FundingAccrual:
        """Funding realizado entre ``(open_ms, close_ms]``; jamás reemplaza cobertura faltante por cero.

        Binance USDⓈ-M: tasa positiva implica que LONG paga y SHORT cobra.
        Esa convención queda intencionalmente aislada aquí y debe habilitarse para
        auditorías sólo después de ``validate_funding_income.py`` contra Income History.
        """
        symbol = str(position["symbol"])
        coverage = self.coverage(venue, symbol, open_ms, close_ms, rate_type)
        if not coverage["complete"]:
            return FundingAccrual("FUNDING_COVERAGE_INCOMPLETE", None, None, 0, (), tuple(coverage["reasons"]))
        entry = float(position["entry"])
        entry_notional = float(position.get("notional_usdt") or position.get("notional") or
                              (float(position.get("quantity") or position.get("qty") or 1.0) * entry))
        if entry_notional <= 0:
            raise ValueError("position requiere notional_usdt positivo o quantity/entry")
        quantity = float(position.get("quantity") or position.get("qty") or entry_notional / entry)
        short = _side_is_short(position["side"])
        events = self.events(venue, symbol, open_ms, close_ms, rate_type)
        if any(event["mark_price"] is None for event in events):
            return FundingAccrual("FUNDING_COVERAGE_INCOMPLETE", None, None, 0, (), ("MARK_PRICE_UNAVAILABLE",))
        detailed = []
        cashflow = 0.0
        for event in events:
            signed_rate = event["funding_rate"] if short else -event["funding_rate"]
            event_notional = quantity * float(event["mark_price"])
            event_cashflow = event_notional * signed_rate
            cashflow += event_cashflow
            detailed.append({**event, "notional_usdt": event_notional, "cashflow_usdt": event_cashflow})
        return FundingAccrual("FUNDING_COVERAGE_COMPLETE", cashflow, cashflow / entry_notional * 100.0,
                              len(detailed), tuple(detailed))


def validate_income_history(store: FundingStore, rows: Iterable[dict], venue: str = BINANCE_USDM,
                            tolerance_usdt: float = 1e-8) -> dict:
    """Compara muestras exportadas de Income History con el mismo signo/cashflow.

    Cada fila requiere ``symbol, side, entry, open_ms, close_ms, income_usdt`` y
    ``notional_usdt`` (o qty/quantity). No usa API privada ni credenciales.
    """
    checked, mismatches = [], []
    for row in rows:
        accrual = store.accrued_funding(row, int(row["open_ms"]), int(row["close_ms"]), venue)
        actual = float(row["income_usdt"])
        item = {"symbol": row["symbol"], "expected_usdt": accrual.cashflow_usdt, "income_usdt": actual,
                "status": accrual.status}
        checked.append(item)
        if not accrual.complete or abs((accrual.cashflow_usdt or 0.0) - actual) > tolerance_usdt:
            mismatches.append(item)
    return {"checked": len(checked), "matched": len(checked) - len(mismatches), "mismatches": mismatches,
            "validated": bool(checked) and not mismatches}
