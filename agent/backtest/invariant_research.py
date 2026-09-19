"""VIRE: isolated, market-neutral relationship research.

This module has no dependency on strategy profiles, the live agent, or ABP.
It reads historical OHLCV only and persists an append-only research ledger.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import Iterable

import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "binance_vision_clean.db")
# In Docker the historical OHLCV lives in the named /app/data volume while the
# collector-owned research DB is deliberately mounted separately read-only.
LIVE_RESEARCH_DB_PATH = os.environ.get(
    "VIRE_LIVE_RESEARCH_DB",
    os.path.join(os.path.dirname(__file__), "..", "data", "klines.db"),
)
BASE_TABLE = "klines_5m"
BASE_INTERVAL = "5m"


@dataclass(frozen=True)
class ResearchConfig:
    start_date: str
    end_date: str
    symbols: tuple[str, ...]
    max_pairs: int = 80
    min_bars: int = 600
    min_oos_trades: int = 8
    fee_bps_per_leg: float = 4.0
    slippage_bps_per_leg: float = 2.0
    perturbation_bps_per_leg: float = 3.0
    capital_per_trade: float = 150.0


@dataclass(frozen=True)
class ExitPolicy:
    entry_z: float
    exit_z: float
    stop_z: float
    max_bars: int

    @property
    def key(self) -> str:
        return f"z{self.entry_z:g}-x{self.exit_z:g}-s{self.stop_z:g}-t{self.max_bars}"


DEFAULT_POLICIES = (
    ExitPolicy(1.8, 0.50, 3.5, 144),
    ExitPolicy(2.2, 0.50, 3.5, 144),
    ExitPolicy(2.2, 0.25, 3.2, 96),
    ExitPolicy(2.6, 0.50, 3.8, 192),
)


def _ms(date_text: str) -> int:
    return int(datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def init_research_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invariant_research_runs (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config_json TEXT NOT NULL,
          result_json TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invariant_research_candidates (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, symbol_a TEXT NOT NULL,
          symbol_b TEXT NOT NULL, status TEXT NOT NULL, candidate_json TEXT NOT NULL
        )""")
    # This registry belongs to VIRE only.  It deliberately does not create or
    # modify an execution StrategyProfile: research hypotheses and live
    # strategies are different entities with different safety contracts.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invariant_research_strategies (
          strategy_id TEXT PRIMARY KEY, name TEXT NOT NULL, family TEXT NOT NULL,
          version TEXT NOT NULL, thesis TEXT NOT NULL, first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL, latest_status TEXT NOT NULL,
          latest_candidate_json TEXT NOT NULL
        )""")
    conn.commit()


def load_prices(conn: sqlite3.Connection, symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
    rows = conn.execute(
        f"SELECT open_time, close FROM {BASE_TABLE} WHERE symbol=? AND interval=? "
        "AND open_time>=? AND open_time<? ORDER BY open_time",
        (symbol, BASE_INTERVAL, start_ms, end_ms),
    ).fetchall()
    return {int(t): float(close) for t, close in rows if close and float(close) > 0}


def available_symbols(conn: sqlite3.Connection, limit: int = 40) -> list[str]:
    """Research universe from its own causal OHLCV table, never legacy engine tables."""
    rows = conn.execute(
        f"SELECT symbol, COUNT(*) AS n FROM {BASE_TABLE} WHERE interval=? "
        "GROUP BY symbol ORDER BY n DESC, symbol ASC LIMIT ?", (BASE_INTERVAL, limit)
    ).fetchall()
    return [str(symbol) for symbol, _ in rows]


def _table_coverage(conn: sqlite3.Connection, table: str, time_column: str) -> dict:
    """Small, auditable coverage record; missing sources are never inferred."""
    try:
        rows, symbols, first, last = conn.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT symbol), MIN({time_column}), MAX({time_column}) FROM {table}"
        ).fetchone()
    except sqlite3.Error as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": bool(rows), "rows": int(rows), "symbols": int(symbols),
            "first_ms": int(first) if first else None, "last_ms": int(last) if last else None}


def data_coverage(conn: sqlite3.Connection, live_db_path: str = LIVE_RESEARCH_DB_PATH) -> dict:
    """Report exactly which feature sources can support historical validation.

    The price relationship model must not silently claim OI, funding or
    liquidation validation just because a collector exists.  This catalog is
    returned with each run and is intended for the UI/audit ledger.
    """
    price_base = _table_coverage(conn, BASE_TABLE, "open_time")
    funding = _table_coverage(conn, "funding_hist", "calc_time")
    oi = _table_coverage(conn, "oi_metrics", "open_time")
    try:
        live = sqlite3.connect(f"file:{live_db_path}?mode=ro", uri=True)
        liquidation = _table_coverage(live, "liquidations_research", "timestamp")
        live.close()
    except sqlite3.Error as exc:
        liquidation = {"available": False, "reason": str(exc)}

    # These are deliberately conservative: a source only becomes suitable for
    # a historical module once it covers a meaningful portion of the universe.
    return {
        "price": {**price_base, "symbols": len(available_symbols(conn, 10000)), "role": "active"},
        "funding": {**funding, "role": "available_not_yet_modelled",
                    "universe_sufficient": funding.get("symbols", 0) >= 100},
        "open_interest": {**oi, "role": "available_not_yet_modelled",
                          "universe_sufficient": oi.get("symbols", 0) >= 100},
        "liquidations": {**liquidation, "role": "not_historically_eligible",
                          "universe_sufficient": liquidation.get("symbols", 0) >= 100},
    }


def _aligned_log_prices(a: dict[int, float], b: dict[int, float], min_bars: int):
    """Return synchronized prices only.

    Fitting a hedge ratio here would leak validation/OOS observations into the
    candidate definition.  The fit deliberately happens in `_evaluate_pair`
    using the train segment alone.
    """
    timestamps = sorted(set(a).intersection(b))
    if len(timestamps) < min_bars:
        return None
    x = np.log(np.array([a[t] for t in timestamps], dtype=float))
    y = np.log(np.array([b[t] for t in timestamps], dtype=float))
    return timestamps, x, y


def _train_relationship(x_train: np.ndarray, y_train: np.ndarray):
    """Fit and diagnose the relationship using train observations only."""
    beta, intercept = np.polyfit(x_train, y_train, 1)
    residual = y_train - (beta * x_train + intercept)
    lag, now = residual[:-1], residual[1:]
    denom = float(np.dot(lag, lag))
    phi = float(np.dot(lag, now) / denom) if denom else 1.0
    if not (0.0 < phi < 0.995):
        return None
    half_life = -math.log(2) / math.log(phi)
    if not (3 <= half_life <= 240):
        return None
    return float(beta), float(intercept), float(phi), float(half_life)


def _simulate(x: np.ndarray, y: np.ndarray, residual: np.ndarray, beta: float,
              policy: ExitPolicy, cost_bps_per_leg: float, capital: float,
              timestamps: np.ndarray | None = None) -> dict:
    # Rolling statistics are shifted one bar so no signal sees its own close.
    lookback = 288
    if len(residual) <= lookback + 2:
        return {"pnl": 0.0, "trades": [], "cost": 0.0}
    position = 0
    entry_x = entry_y = 0.0
    entry_z = 0.0
    opened_at = 0
    best_open_return = worst_open_return = 0.0
    trades = []
    total_cost = 0.0
    two_leg_roundtrip_cost = capital * (cost_bps_per_leg / 10000.0) * 4.0
    for i in range(lookback, len(residual)):
        hist = residual[i - lookback:i]
        std = float(np.std(hist))
        if std <= 1e-12:
            continue
        z = float((residual[i] - np.mean(hist)) / std)
        if position == 0:
            if z >= policy.entry_z:
                position, entry_x, entry_y, entry_z, opened_at = -1, x[i], y[i], z, i
                best_open_return = worst_open_return = 0.0
            elif z <= -policy.entry_z:
                position, entry_x, entry_y, entry_z, opened_at = 1, x[i], y[i], z, i
                best_open_return = worst_open_return = 0.0
            continue
        open_return = position * ((y[i] - entry_y) - beta * (x[i] - entry_x))
        best_open_return = max(best_open_return, float(open_return))
        worst_open_return = min(worst_open_return, float(open_return))
        exit_now = (position == -1 and z <= policy.exit_z) or (position == 1 and z >= -policy.exit_z)
        stop_now = abs(z) >= policy.stop_z
        time_now = i - opened_at >= policy.max_bars
        if not (exit_now or stop_now or time_now):
            continue
        # long spread = long B / short beta*A; short is its exact inverse.
        gross_return = open_return
        pnl = capital * gross_return - two_leg_roundtrip_cost
        total_cost += two_leg_roundtrip_cost
        trades.append({
            "entry_time_ms": int(timestamps[opened_at]) if timestamps is not None else None,
            "exit_time_ms": int(timestamps[i]) if timestamps is not None else None,
            "side": "long_spread" if position == 1 else "short_spread",
            "gross_pnl": round(float(capital * gross_return), 8),
            "cost": round(float(two_leg_roundtrip_cost), 8),
            "pnl": round(float(pnl), 8), "bars": i - opened_at,
            "mfe": round(float(capital * best_open_return), 8),
            "mae": round(float(capital * worst_open_return), 8),
            "entry_z": round(entry_z, 4), "exit_z": round(z, 4),
            "reason": "mean" if exit_now else ("stop" if stop_now else "time"),
        })
        position = 0
    return {"pnl": round(sum(t["pnl"] for t in trades), 8), "trades": trades, "cost": round(total_cost, 8)}


def _metrics(sim: dict) -> dict:
    pnls = [t["pnl"] for t in sim["trades"]]
    count = len(pnls)
    total = float(sum(pnls))
    best_share = max(pnls) / total if total > 0 and pnls else 1.0
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    curve, peak, max_drawdown = 0.0, 0.0, 0.0
    for pnl in pnls:
        curve += pnl; peak = max(peak, curve); max_drawdown = min(max_drawdown, curve - peak)
    return {"net_pnl": round(total, 4), "trades": count,
            "win_rate": round(100 * sum(p > 0 for p in pnls) / count, 2) if count else 0.0,
            "best_trade_share": round(best_share, 4), "cost": sim["cost"],
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
            "max_drawdown": round(max_drawdown, 4),
            "avg_trade": round(total / count, 4) if count else 0.0}


def _trade_diagnostics(sim: dict) -> dict:
    """Explain outcomes mechanically, without claiming causal factors we did not model.

    Each trade stores exit mechanics, adverse/favourable excursion and full
    costs.  This makes it possible to inspect *why the simulated rule* won or
    lost rather than showing a single aggregate PnL.
    """
    trades = sim["trades"]
    by_exit: dict[str, dict] = {}
    for trade in trades:
        bucket = by_exit.setdefault(trade["reason"], {"trades": 0, "net_pnl": 0.0, "wins": 0, "losses": 0})
        bucket["trades"] += 1; bucket["net_pnl"] += trade["pnl"]
        bucket["wins"] += int(trade["pnl"] > 0); bucket["losses"] += int(trade["pnl"] <= 0)
    return {
        "attribution_scope": "mechanical_exit_and_excursion_only",
        "by_exit": [{"reason": key, "trades": value["trades"], "net_pnl": round(value["net_pnl"], 4),
                     "wins": value["wins"], "losses": value["losses"]} for key, value in sorted(by_exit.items())],
        "trades": trades,
    }


def _feature_snapshot(conn: sqlite3.Connection, symbols: tuple[str, ...], start_ms: int, end_ms: int) -> dict:
    """Fetch feature availability once per run, not once per relationship."""
    if not symbols:
        return {"funding": {}, "open_interest": {}}
    marks = ",".join("?" for _ in symbols)
    params = (*symbols, start_ms, end_ms)
    try:
        funding_rows = conn.execute(
            f"SELECT symbol, COUNT(*), AVG(funding_rate) FROM funding_hist WHERE symbol IN ({marks}) "
            "AND calc_time>=? AND calc_time<? GROUP BY symbol", params).fetchall()
    except sqlite3.Error:
        funding_rows = []
    try:
        oi_rows = conn.execute(
            f"SELECT symbol, COUNT(*), MIN(sum_oi_value), MAX(sum_oi_value) FROM oi_metrics WHERE symbol IN ({marks}) "
            "AND open_time>=? AND open_time<? GROUP BY symbol", params).fetchall()
    except sqlite3.Error:
        oi_rows = []
    return {
        "funding": {str(s): {"observations": int(n), "mean_rate": round(float(r or 0), 10)} for s, n, r in funding_rows},
        "open_interest": {str(s): {"observations": int(n), "change": round(float(last or 0) - float(first or 0), 4)} for s, n, first, last in oi_rows},
    }


def _feature_context(symbol_a: str, symbol_b: str, snapshot: dict) -> dict:
    """Audit the causal feature availability for a relationship.

    These records are context only in the price-only vertical.  They make the
    missing decision module visible instead of quietly treating absent OI or
    funding as neutral signals.
    """
    funding = {s: snapshot["funding"][s] for s in (symbol_a, symbol_b) if s in snapshot["funding"]}
    oi = {s: snapshot["open_interest"][s] for s in (symbol_a, symbol_b) if s in snapshot["open_interest"]}
    return {"role": "audit_only_not_signal", "funding": funding, "open_interest": oi,
            "complete_for_pair": len(funding) == 2 and len(oi) == 2}


def _split(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = int(len(arr) * 0.50)
    b = int(len(arr) * 0.75)
    return arr[:a], arr[a:b], arr[b:]


def _evaluate_pair(symbol_a: str, symbol_b: str, prices_a: dict, prices_b: dict,
                   config: ResearchConfig, feature_context: dict | None = None) -> dict | None:
    aligned = _aligned_log_prices(prices_a, prices_b, config.min_bars)
    if not aligned:
        return None
    ts, x, y = aligned
    x_train, x_val, x_oos = _split(x)
    y_train, y_val, y_oos = _split(y)
    ts_train, ts_val, ts_oos = _split(np.array(ts, dtype=np.int64))
    fit = _train_relationship(x_train, y_train)
    if not fit:
        return None
    beta, intercept, phi, half_life = fit
    # A fixed train-only hedge ratio/intercept is applied forward.  No fitted
    # parameter may see validation or OOS prices.
    r_train = y_train - (beta * x_train + intercept)
    r_val = y_val - (beta * x_val + intercept)
    r_oos = y_oos - (beta * x_oos + intercept)
    # Every result pays both explicit fees and executable slippage.  The
    # perturbation pass adds a further adverse fill assumption on top.
    base_cost_bps = config.fee_bps_per_leg + config.slippage_bps_per_leg
    train_scores = []
    for policy in DEFAULT_POLICIES:
        sim = _simulate(x_train, y_train, r_train, beta, policy, base_cost_bps, config.capital_per_trade, ts_train)
        train_scores.append((_metrics(sim), policy))
    best_train, policy = max(train_scores, key=lambda item: item[0]["net_pnl"])
    validation_sim = _simulate(x_val, y_val, r_val, beta, policy, base_cost_bps, config.capital_per_trade, ts_val)
    validation = _metrics(validation_sim)
    oos_sim = _simulate(x_oos, y_oos, r_oos, beta, policy, base_cost_bps, config.capital_per_trade, ts_oos)
    oos = _metrics(oos_sim)
    stressed = _metrics(_simulate(x_oos, y_oos, r_oos, beta, policy,
                                  base_cost_bps + config.perturbation_bps_per_leg,
                                  config.capital_per_trade, ts_oos))
    neighbours = []
    for neighbour in DEFAULT_POLICIES:
        neighbours.append(_metrics(_simulate(x_oos, y_oos, r_oos, beta, neighbour,
                                             base_cost_bps, config.capital_per_trade, ts_oos))["net_pnl"])
    status = "PAPER_READY" if (
        validation["net_pnl"] > 0 and oos["net_pnl"] > 0 and stressed["net_pnl"] > 0
        and oos["trades"] >= config.min_oos_trades and oos["best_trade_share"] <= 0.45
        and sum(v > 0 for v in neighbours) >= max(2, len(neighbours) // 2)
    ) else "REJECTED"
    strategy_payload = {
        "family": "pair_mean_reversion",
        "symbols": [symbol_a, symbol_b],
        "policy": asdict(policy),
        "feature_role": (feature_context or {}).get("role", "unavailable"),
        "cost_model": {"fee_bps_per_leg": config.fee_bps_per_leg,
                       "slippage_bps_per_leg": config.slippage_bps_per_leg,
                       "stress_bps_per_leg": config.perturbation_bps_per_leg},
    }
    version = hashlib.sha256(json.dumps(strategy_payload, sort_keys=True).encode()).hexdigest()[:12]
    strategy = {
        "id": f"vire:pair-mean-reversion:{symbol_a}:{symbol_b}:{policy.key}",
        "name": f"VIRE Pair Reversion — {symbol_a}/{symbol_b} ({policy.key})",
        "family": "pair_mean_reversion",
        "version": version,
        "thesis": "El spread logarítmico entre dos activos cointegrados revierte tras una desviación extrema; se valida fuera de muestra con costos y estrés.",
        "entry": {"long_spread_when_z_lte": -policy.entry_z, "short_spread_when_z_gte": policy.entry_z},
        "exit": {"mean_reversion_z": policy.exit_z, "stop_z": policy.stop_z, "max_bars": policy.max_bars},
        "signal_sources": ["price"],
        "feature_scope": (feature_context or {}).get("role", "unavailable"),
    }
    return {
        "symbol_a": symbol_a, "symbol_b": symbol_b, "status": status,
        "strategy": strategy,
        "relationship": {"hedge_ratio": round(beta, 6), "ar1_phi": round(phi, 6),
                           "half_life_bars": round(half_life, 2), "aligned_bars": len(ts)},
        "policy": asdict(policy), "train": best_train, "validation": validation,
        "oos": oos, "stressed_oos": stressed,
        "trade_diagnostics": {"validation": _trade_diagnostics(validation_sim), "oos": _trade_diagnostics(oos_sim)},
        "feature_context": feature_context or {"role": "unavailable"},
        "parameter_neighbourhood_positive": sum(v > 0 for v in neighbours),
        "parameter_neighbourhood_total": len(neighbours),
        "rejection_reasons": [] if status == "PAPER_READY" else _reasons(validation, oos, stressed, config, neighbours),
    }


def _upsert_strategy_registry(conn: sqlite3.Connection, candidate: dict, seen_at: str) -> None:
    strategy = candidate["strategy"]
    conn.execute("""
        INSERT INTO invariant_research_strategies
          (strategy_id,name,family,version,thesis,first_seen,last_seen,latest_status,latest_candidate_json)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(strategy_id) DO UPDATE SET
          name=excluded.name, family=excluded.family, version=excluded.version,
          thesis=excluded.thesis, last_seen=excluded.last_seen,
          latest_status=excluded.latest_status, latest_candidate_json=excluded.latest_candidate_json
    """, (strategy["id"], strategy["name"], strategy["family"], strategy["version"], strategy["thesis"],
          seen_at, seen_at, candidate["status"], json.dumps(candidate)))


def _reasons(validation: dict, oos: dict, stressed: dict, config: ResearchConfig, neighbours: list[float]) -> list[str]:
    reasons = []
    if validation["net_pnl"] <= 0: reasons.append("validation_not_positive_after_costs")
    if oos["net_pnl"] <= 0: reasons.append("oos_not_positive_after_costs")
    if stressed["net_pnl"] <= 0: reasons.append("fails_slippage_perturbation")
    if oos["trades"] < config.min_oos_trades: reasons.append("insufficient_oos_trades")
    if oos["best_trade_share"] > 0.45: reasons.append("single_trade_concentration")
    if sum(v > 0 for v in neighbours) < max(2, len(neighbours) // 2): reasons.append("parameter_fragility")
    return reasons


def _train_correlation_scores(symbols: tuple[str, ...], prices: dict[str, dict[int, float]]) -> dict[tuple[str, str], float]:
    """Cheap discovery screen fitted strictly on the TRAIN half.

    It is only a ranker: the hedge ratio, half-life and every simulated metric
    are still fitted/evaluated later with their own causal split.
    """
    common = set.intersection(*(set(prices[s]) for s in symbols)) if symbols else set()
    timestamps = sorted(common)
    if len(timestamps) < 600:
        return {}
    train_end = max(3, int((len(timestamps) - 1) * .50))
    returns = np.array([np.diff(np.log([prices[s][t] for t in timestamps]))[:train_end] for s in symbols])
    corr = np.nan_to_num(np.corrcoef(returns), nan=0.0)
    return {tuple(sorted((symbols[i], symbols[j]))): float(abs(corr[i, j]))
            for i in range(len(symbols)) for j in range(i + 1, len(symbols))}


def _coverage_first_pairs(symbols: tuple[str, ...], eligible_pairs: list[tuple[str, str]], limit: int,
                          scores: dict[tuple[str, str], float] | None = None) -> list[tuple[str, str]]:
    """Choose a reproducible pair set without concentrating on large caps.

    A ring is traversed before a second neighbour distance is considered, so a
    400-relationship run gives every eligible symbol one relationship before
    any symbol receives its second.  Eligibility remains based on available
    historical bars; no synthetic/missing data is padded.
    """
    if limit <= 0 or not eligible_pairs:
        return []
    eligible = {tuple(sorted(pair)) for pair in eligible_pairs}
    scores = scores or {}
    ordered = list(symbols)
    selected: list[tuple[str, str]] = []
    chosen: set[tuple[str, str]] = set()
    # First give every symbol its strongest train-only neighbour.  This retains
    # universe coverage while spending the simulation budget on plausible
    # relationships rather than arbitrary ring neighbours.
    for symbol in ordered:
        options = [p for p in eligible if symbol in p and p not in chosen]
        if not options:
            continue
        pair = max(options, key=lambda p: (scores.get(p, 0.0), p))
        chosen.add(pair); selected.append(pair)
        if len(selected) >= limit:
            return selected
    for pair in sorted(eligible - chosen, key=lambda p: (scores.get(p, 0.0), p), reverse=True):
        selected.append(pair)
        if len(selected) >= limit:
            return selected
    return selected


def run_research(conn: sqlite3.Connection, config: ResearchConfig) -> dict:
    init_research_db(conn)
    start_ms, end_ms = _ms(config.start_date), _ms(config.end_date)
    prices = {s: load_prices(conn, s, start_ms, end_ms) for s in config.symbols}
    feature_snapshot = _feature_snapshot(conn, config.symbols, start_ms, end_ms)
    # Screen every symbol in the configured universe before selecting the
    # expensive simulations.  The coverage-first ring prevents the old
    # lexicographic bias and makes a 400-relationship run cover the entire
    # 400-symbol universe whenever the data is eligible.
    all_pairs = list(combinations(config.symbols, 2))
    eligible_pairs = [p for p in all_pairs if min(len(prices[p[0]]), len(prices[p[1]])) >= config.min_bars]
    pair_scores = _train_correlation_scores(config.symbols, prices)
    pairs = _coverage_first_pairs(config.symbols, eligible_pairs, config.max_pairs, pair_scores)
    candidates = []
    for a, b in pairs[:config.max_pairs]:
        candidate = _evaluate_pair(a, b, prices[a], prices[b], config,
                                   _feature_context(a, b, feature_snapshot))
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda c: (c["status"] == "PAPER_READY", c["oos"]["net_pnl"]), reverse=True)
    run_id = str(uuid.uuid4())
    coverage = data_coverage(conn)
    result = {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": "pair_relationship_price_only_v1", "config": asdict(config), "candidates": candidates,
              "data_coverage": coverage,
              "promotion_policy": {
                  "paper_ready_allowed": False,
                  "reason": "price_relationship_only; funding_oi_liquidation modules require independent historical validation"
              },
              "summary": {"universe_symbols": len(config.symbols),
                          "pair_space": len(all_pairs), "eligible_pair_space": len(eligible_pairs),
                          "pairs_screened": len(pairs),
                          "universe_symbols_represented": len({symbol for pair in pairs for symbol in pair}),
                          "relationships_eligible": len(candidates),
                          "structural_passes": sum(c["status"] == "PAPER_READY" for c in candidates),
                          "paper_ready": 0}}
    conn.execute("INSERT INTO invariant_research_runs VALUES (?,?,?,?)",
                 (run_id, result["created_at"], json.dumps(asdict(config)), json.dumps(result)))
    conn.executemany("INSERT INTO invariant_research_candidates VALUES (?,?,?,?,?,?)", [
        (str(uuid.uuid4()), run_id, c["symbol_a"], c["symbol_b"], c["status"], json.dumps(c)) for c in candidates
    ])
    for candidate in candidates:
        _upsert_strategy_registry(conn, candidate, result["created_at"])
    conn.commit()
    return result


def list_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    init_research_db(conn)
    rows = conn.execute("SELECT id, created_at, result_json FROM invariant_research_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"run_id": r[0], "created_at": r[1], "summary": json.loads(r[2]).get("summary", {})} for r in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    init_research_db(conn)
    row = conn.execute("SELECT result_json FROM invariant_research_runs WHERE id=?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None


def list_strategies(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    init_research_db(conn)
    rows = conn.execute("""
        SELECT strategy_id,name,family,version,thesis,first_seen,last_seen,latest_status,latest_candidate_json
        FROM invariant_research_strategies ORDER BY last_seen DESC LIMIT ?
    """, (limit,)).fetchall()
    return [{"strategy_id": r[0], "name": r[1], "family": r[2], "version": r[3], "thesis": r[4],
             "first_seen": r[5], "last_seen": r[6], "status": r[7], "candidate": json.loads(r[8])} for r in rows]
