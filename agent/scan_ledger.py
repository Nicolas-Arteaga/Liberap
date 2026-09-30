"""Append-only diagnostic ledger for scan cycles.

Disabled by default.  It intentionally receives snapshots only; it never
returns a decision and every I/O failure is contained here.
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import threading
import atexit
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ScanLedger")


class ScanLedger:
    def __init__(self, enabled: bool = False, path: str = "data/scan_ledger.jsonl", batch_size: int = 50,
                 flush_interval_seconds: float = 15.0, max_bytes: int = 50 * 1024 * 1024):
        self.enabled = bool(enabled)
        self.path = Path(path)
        self.batch_size = max(1, int(batch_size))
        self.flush_interval_seconds = max(1.0, float(flush_interval_seconds))
        self.max_bytes = max(1024, int(max_bytes))
        self._buffer: list[dict] = []
        self._lock = threading.RLock()
        self._last_flush = time.monotonic()
        atexit.register(self.flush)

    @staticmethod
    def _candidate(candidate: dict) -> dict:
        """Whitelist diagnostic fields: never mutate or serialize full runtime objects."""
        return {
            "symbol": candidate.get("symbol"),
            "source": candidate.get("source"),
            "side": candidate.get("side"),
            "score": candidate.get("confluence_score", candidate.get("score")),
            "nexus": candidate.get("nexus_confidence"),
            "price_at_signal": candidate.get("price_at_signal"),
            "detected_at": candidate.get("scored_at", candidate.get("detected_at")),
            "reason": candidate.get("reason"),
        }

    @staticmethod
    def _latency_ms(candidate: dict, captured_at: datetime) -> float | None:
        """Best-effort observation; never feeds an execution decision."""
        raw = candidate.get("scored_at", candidate.get("detected_at"))
        if not raw:
            return None
        try:
            detected = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if detected.tzinfo is None:
                detected = detected.replace(tzinfo=timezone.utc)
            return round((captured_at - detected.astimezone(timezone.utc)).total_seconds() * 1000, 3)
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _parameter_hash(profile: dict) -> str:
        raw = str(profile.get("patternParamsJson", "")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def record_profile_scan(self, profile: dict, candidates: list[dict], rejected: list[dict],
                            active_count: int, max_positions: int, ranked: list[dict]) -> None:
        if not self.enabled:
            return
        try:
            event = {
                "schema_version": 1,
                "event": "profile_scan",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "profile_id": profile.get("id"),
                "profile_name": profile.get("name"),
                "parameter_hash": self._parameter_hash(profile),
                "active_positions": active_count,
                "max_positions": max_positions,
                "candidates": [self._candidate(x) for x in candidates],
                "rejected": [self._candidate(x) for x in rejected],
                "ranked_symbols": [x.get("symbol") for x in ranked],
            }
            self._append(event)
        except Exception as exc:  # Diagnostic I/O must never interrupt trading.
            logger.warning("[SCAN-LEDGER] record skipped: %s", exc)

    def record_attempt(self, profile: dict, candidate: dict, rank: int, executed: bool) -> None:
        if not self.enabled:
            return
        try:
            captured_at = datetime.now(timezone.utc)
            self._append({
                "schema_version": 1,
                "event": "execution_attempt",
                "captured_at_utc": captured_at.isoformat(),
                "profile_id": profile.get("id"),
                "profile_name": profile.get("name"),
                "rank": rank,
                "executed": bool(executed),
                "detection_to_execution_ms": self._latency_ms(candidate, captured_at),
                "candidate": self._candidate(candidate),
            }, immediate=True)
        except Exception as exc:  # Diagnostic I/O must never interrupt trading.
            logger.warning("[SCAN-LEDGER] attempt skipped: %s", exc)

    def record_rejection(self, profile: dict, candidate: dict, reason: str, details: dict | None = None) -> None:
        """Capture the exact deterministic return-False path; never affects it."""
        if not self.enabled:
            return
        try:
            self._append({
                "schema_version": 1,
                "event": "execution_rejection",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "profile_id": profile.get("id") if profile else None,
                "profile_name": profile.get("name") if profile else "Legacy",
                "reason": str(reason),
                "details": details or {},
                "candidate": self._candidate(candidate),
            }, immediate=True)
        except Exception as exc:
            logger.warning("[SCAN-LEDGER] rejection skipped: %s", exc)

    def record_position_review(self, position: dict, observed_price: float, age_hours: float,
                               return_pct: float | None, decision_rule: str) -> None:
        if not self.enabled:
            return
        try:
            self._append({
                "schema_version": 1,
                "event": "position_review",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "decision_rule": decision_rule,
                "observed_price": observed_price,
                "age_hours": round(float(age_hours), 6),
                "return_pct": return_pct,
                "position": self._position(position),
            }, immediate=True)
        except Exception as exc:
            logger.warning("[SCAN-LEDGER] position review skipped: %s", exc)

    def record_position_close(self, position: dict, observed_price: float, age_hours: float,
                              return_pct: float | None, rule: str) -> None:
        if not self.enabled:
            return
        try:
            self._append({
                "schema_version": 1,
                "event": "position_close_decision",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "rule": rule,
                "observed_price": observed_price,
                "age_hours": round(float(age_hours), 6),
                "return_pct": return_pct,
                "position": self._position(position),
            }, immediate=True)
        except Exception as exc:
            logger.warning("[SCAN-LEDGER] close decision skipped: %s", exc)

    @staticmethod
    def _position(position: dict) -> dict:
        """Only effective decision parameters, not the whole mutable runtime position."""
        fields = ("trade_id", "symbol", "opened_at", "side", "entry_price", "tp_price", "sl_price",
                  "original_sl_price", "margin", "leverage", "strategy_profile_id", "strategy_name",
                  "source", "max_profit_price", "breakeven_locked", "trail_level_applied")
        return {field: position.get(field) for field in fields}

    def record_acceptance(self, profile: dict | None, candidate: dict, position_details: dict,
                          trade_id: object | None) -> None:
        """Record only the effective accepted order parameters after a successful open."""
        if not self.enabled:
            return
        try:
            captured_at = datetime.now(timezone.utc)
            fields = ("entry_price", "tp_price", "sl_price", "margin", "leverage", "quantity")
            accepted = {field: position_details.get(field) for field in fields}
            accepted["trade_id"] = trade_id
            self._append({
                "schema_version": 1,
                "event": "execution_accepted",
                "captured_at_utc": captured_at.isoformat(),
                "profile_id": profile.get("id") if profile else None,
                "profile_name": profile.get("name") if profile else "Legacy",
                "detection_to_execution_ms": self._latency_ms(candidate, captured_at),
                "candidate": self._candidate(candidate),
                "accepted_position": accepted,
            }, immediate=True)
        except Exception as exc:
            logger.warning("[SCAN-LEDGER] acceptance skipped: %s", exc)

    def _append(self, event: dict, immediate: bool = False) -> None:
        with self._lock:
            self._buffer.append(event)
            if immediate or len(self._buffer) >= self.batch_size or time.monotonic() - self._last_flush >= self.flush_interval_seconds:
                self.flush()

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        rotated = self.path.with_name(self.path.name + "." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        try:
            self.path.replace(rotated)
        except OSError as exc:
            logger.warning("[SCAN-LEDGER] rotation skipped: %s", exc)

    def flush(self) -> None:
        if not self.enabled:
            return
        try:
            with self._lock:
                if not self._buffer:
                    return
                pending, self._buffer = self._buffer, []
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed()
            with self.path.open("a", encoding="utf-8") as handle:
                for event in pending:
                    handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._last_flush = time.monotonic()
        except Exception as exc:  # Put nothing back: diagnostics are best-effort only.
            logger.warning("[SCAN-LEDGER] flush skipped: %s", exc)
