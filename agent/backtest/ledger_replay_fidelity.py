"""Prospective, read-only fidelity report: scan ledger versus a frozen replay.

No network, database, strategy, or ledger writes.  See
LEDGER_REPLAY_FIDELITY_PREREGISTER.md for the frozen thresholds and schema.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SEED = 20260930
BOOTSTRAPS = 10_000
RETURN_TOL_PP = 0.25
MIN_SIGNALS = 300
MIN_MATCHED = 200
MIN_DAYS = 30
MIN_EFFECTIVE_DAYS = 20


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_no}: JSON inválido: {exc.msg}") from exc


def parse_time(value):
    if value is None:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def reason(value):
    text = str(value or "").strip().lower().replace("-", "_")
    if "take" in text or text == "tp" or text.startswith("tp_"):
        return "TP"
    if "stop" in text or text == "sl" or text.startswith("sl_"):
        return "SL"
    if "timeout" in text or "zombie" in text or "duration" in text:
        return "TIMEOUT"
    return text.upper() or None


def bootstrap_day_ci(values_by_day, statistic):
    days = sorted(values_by_day)
    if not days:
        return None
    rng = random.Random(SEED)
    samples = []
    for _ in range(BOOTSTRAPS):
        sample = []
        for day in (rng.choice(days) for _ in days):
            sample.extend(values_by_day[day])
        samples.append(statistic(sample))
    samples.sort()
    return [samples[int(0.025 * (BOOTSTRAPS - 1))], samples[int(0.975 * (BOOTSTRAPS - 1))]]


def mean(values):
    return sum(values) / len(values) if values else float("nan")


def load_ledger(paths):
    accepted, closes, detected_days, malformed = {}, {}, set(), []
    for path in paths:
        for event in read_jsonl(path):
            event_name = event.get("event")
            captured = parse_time(event.get("captured_at_utc"))
            if event_name == "profile_scan" and captured:
                detected_days.add(captured.date().isoformat())
            if event_name == "execution_accepted":
                position = event.get("accepted_position") or {}
                trade_id = position.get("trade_id")
                if trade_id is None:
                    malformed.append({"kind": "accepted_without_trade_id", "event": event})
                    continue
                accepted[str(trade_id)] = event
            elif event_name == "position_close_decision":
                position = event.get("position") or {}
                trade_id = position.get("trade_id")
                if trade_id is None:
                    malformed.append({"kind": "close_without_trade_id", "event": event})
                    continue
                closes[str(trade_id)] = event
    return accepted, closes, detected_days, malformed


def load_replay(path):
    records, fallback = {}, defaultdict(list)
    for row in read_jsonl(path):
        trade_id = row.get("trade_id")
        if trade_id is not None:
            records[str(trade_id)] = row
        opened = parse_time(row.get("opened_at_utc"))
        if opened and row.get("symbol") and row.get("side") is not None:
            fallback[(row["symbol"], str(row["side"]))].append((opened, row))
    return records, fallback


def match_records(accepted, closes, replay, fallback):
    pairs, exclusions = [], []
    for trade_id, close in closes.items():
        acceptance = accepted.get(trade_id)
        position = close.get("position") or {}
        if not acceptance:
            exclusions.append({"trade_id": trade_id, "reason": "close_without_acceptance"})
            continue
        ledger_reason, ledger_return = reason(close.get("rule")), close.get("return_pct")
        if ledger_reason is None or ledger_return is None:
            exclusions.append({"trade_id": trade_id, "reason": "close_missing_rule_or_return"})
            continue
        row, strength = replay.get(trade_id), "strong"
        if row is None:
            opened = parse_time(position.get("opened_at"))
            key = (position.get("symbol"), str(position.get("side")))
            candidates = [x for x in fallback.get(key, []) if opened and abs((x[0] - opened).total_seconds()) <= 300]
            if len(candidates) == 1:
                row, strength = candidates[0][1], "weak"
            else:
                exclusions.append({"trade_id": trade_id, "reason": "replay_missing_or_ambiguous"})
                continue
        replay_reason, replay_return = reason(row.get("close_reason")), row.get("return_pct")
        if replay_reason is None or replay_return is None:
            exclusions.append({"trade_id": trade_id, "reason": "replay_missing_reason_or_return"})
            continue
        closed_at = parse_time(close.get("captured_at_utc"))
        pairs.append({"trade_id": trade_id, "day": closed_at.date().isoformat() if closed_at else "unknown",
                      "strength": strength, "reason_match": replay_reason == ledger_reason,
                      "return_error_pp": float(replay_return) - float(ledger_return),
                      "return_match": abs(float(replay_return) - float(ledger_return)) <= RETURN_TOL_PP,
                      "ledger_reason": ledger_reason, "replay_reason": replay_reason})
    return pairs, exclusions


def report(accepted, detected_days, pairs, exclusions, malformed):
    by_day_reason, by_day_return, by_day_error = defaultdict(list), defaultdict(list), defaultdict(list)
    for pair in pairs:
        by_day_reason[pair["day"]].append(float(pair["reason_match"]))
        by_day_return[pair["day"]].append(float(pair["return_match"]))
        by_day_error[pair["day"]].append(pair["return_error_pp"])
    n, days = len(pairs), len(by_day_reason)
    thresholds = n >= MIN_MATCHED and len(detected_days) >= MIN_DAYS and days >= MIN_EFFECTIVE_DAYS
    reason_rate = mean([p["reason_match"] for p in pairs]) if pairs else float("nan")
    return_rate = mean([p["return_match"] for p in pairs]) if pairs else float("nan")
    error_mean = mean([p["return_error_pp"] for p in pairs]) if pairs else float("nan")
    r_ci = bootstrap_day_ci(by_day_reason, mean) if pairs else None
    ret_ci = bootstrap_day_ci(by_day_return, mean) if pairs else None
    err_ci = bootstrap_day_ci(by_day_error, mean) if pairs else None
    strong_rate = mean([p["strength"] == "strong" for p in pairs]) if pairs else 0.0
    missing_rate = (len(exclusions) + len(malformed)) / max(1, len(accepted))
    reason_ok = thresholds and reason_rate >= .80 and r_ci[0] >= .70
    return_ok = thresholds and return_rate >= .80 and ret_ci[0] >= .70 and err_ci[0] >= -.25 and err_ci[1] <= .25
    overall = "INSUFICIENTE" if not thresholds else ("COINCIDE" if reason_ok and return_ok and strong_rate >= .95 and missing_rate <= .02 else "NO_COINCIDE")
    return {"status": overall, "preregister": "LEDGER_REPLAY_FIDELITY_PREREGISTER.md", "minimum": {"signals": MIN_SIGNALS, "matched_closed": MIN_MATCHED, "calendar_days": MIN_DAYS, "effective_days": MIN_EFFECTIVE_DAYS}, "observed": {"accepted": len(accepted), "detected_days": len(detected_days), "matched_closed": n, "effective_days": days, "strong_match_rate": strong_rate, "missing_or_excluded_rate": missing_rate}, "exit_reason": {"status": "COINCIDE" if reason_ok else ("INSUFICIENTE" if not thresholds else "NO_COINCIDE"), "match_rate": reason_rate, "day_block_ci_95": r_ci}, "fine_return": {"status": "COINCIDE" if return_ok else ("INSUFICIENTE" if not thresholds else "NO_COINCIDE"), "within_0_25pp_rate": return_rate, "day_block_ci_95": ret_ci, "mean_error_pp": error_mean, "mean_error_day_block_ci_95": err_ci}, "reason_matrix": Counter((p["ledger_reason"], p["replay_reason"]) for p in pairs), "exclusions": exclusions, "malformed": malformed}


def markdown(result):
    o, e, r = result["observed"], result["exit_reason"], result["fine_return"]
    return "\n".join(["# Fidelidad real vs replay", "", f"**Veredicto: {result['status']}**", "", "## Cobertura", f"- Señales/días detectados: {o['detected_days']} días (mínimo 30).", f"- Aceptadas: {o['accepted']}; cierres emparejados: {o['matched_closed']} (mínimo 200); días efectivos: {o['effective_days']} (mínimo 20).", f"- Emparejamiento fuerte por trade_id: {o['strong_match_rate']:.1%}; excluidos o malformados: {o['missing_or_excluded_rate']:.1%}.", "", "## Motivo de salida", f"- {e['status']}: coincidencia {e['match_rate']:.1%} ; IC bloques día 95% {e['day_block_ci_95']}.", "", "## Retorno fino", f"- {r['status']}: dentro de ±0,25 pp {r['within_0_25pp_rate']:.1%}; IC bloques día 95% {r['day_block_ci_95']}; error medio {r['mean_error_pp']:.4f} pp; IC {r['mean_error_day_block_ci_95']}.", "", "Este informe es prospectivo y no modifica producción ni estrategias."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", action="append", required=True, type=Path, help="JSONL ledger; repetir para rotaciones")
    parser.add_argument("--replay", required=True, type=Path, help="JSONL normalizado del replay congelado")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    accepted, closes, detected_days, malformed = load_ledger(args.ledger)
    replay, fallback = load_replay(args.replay)
    pairs, exclusions = match_records(accepted, closes, replay, fallback)
    result = report(accepted, detected_days, pairs, exclusions, malformed)
    result["reason_matrix"] = [{"ledger": a, "replay": b, "n": n} for (a, b), n in sorted(result["reason_matrix"].items())]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "informe.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "matched_closed": result["observed"]["matched_closed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
