"""Probe auditable availability of Binance Vision daily archives.

This intentionally records HTTP status and never infers a missing dataset from
another dataset.  It supports sparse boundary probes (the default) and an
explicit full daily scan when an exact no-gap coverage claim is required.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE = "https://data.binance.vision/data/futures/um/daily"
# Vision exposes bookDepth; it does not expose the bookTicker archive assumed
# by the original roadmap.  The probe keeps both names to make that fact
# independently reproducible.
DATASETS = ("metrics", "aggTrades", "bookTicker", "bookDepth")


def days_between(start: dt.date, end: dt.date, full: bool) -> list[dt.date]:
    if full:
        return [start + dt.timedelta(days=n) for n in range((end - start).days + 1)]
    middle = start + dt.timedelta(days=(end - start).days // 2)
    return sorted({start, middle, end})


def archive_url(dataset: str, symbol: str, day: dt.date) -> str:
    stamp = day.isoformat()
    # Symbols are exchange-originated strings; URL-escape them rather than
    # assuming ASCII so one malformed/non-ASCII listing cannot abort coverage.
    safe_symbol = quote(symbol, safe="")
    return f"{BASE}/{dataset}/{safe_symbol}/{safe_symbol}-{dataset}-{stamp}.zip"


def status(url: str) -> dict:
    request = Request(url, method="HEAD")
    try:
        with urlopen(request, timeout=30) as response:  # nosec B310: fixed public CDN base
            return {"status": response.status, "content_length": response.headers.get("Content-Length")}
    except HTTPError as exc:
        return {"status": exc.code, "content_length": exc.headers.get("Content-Length") if exc.headers else None}
    except URLError as exc:
        return {"status": "ERROR", "error": str(exc.reason)}


def _atomic_write(path: Path, report: dict) -> None:
    """Persist a resumable checkpoint; a partial scan is useful evidence."""
    report.pop("payload_sha256", None)
    body = json.dumps(report, indent=2, sort_keys=True)
    report["payload_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _load_resume(path: Path, datasets: tuple[str, ...], symbols: list[str], sample_days: list[dt.date], args) -> dict | None:
    if not path.exists():
        return None
    prior = json.loads(path.read_text(encoding="utf-8"))
    expected_days = [day.isoformat() for day in sample_days]
    if (prior.get("requested_range") != [args.start.isoformat(), args.end.isoformat()]
            or prior.get("sample_days") != expected_days
            or set(prior.get("datasets", {})) != set(datasets)):
        raise ValueError("resume report does not match requested datasets/range")
    # Missing symbols are treated as absent work, never as successful coverage.
    for dataset in datasets:
        prior["datasets"].setdefault(dataset, {})
        for symbol in symbols:
            prior["datasets"][dataset].setdefault(symbol, {})
    return prior


def _complete(item: object) -> bool:
    """Only a real HTTP status is a completed probe; transient errors retry."""
    return isinstance(item, dict) and isinstance(item.get("status"), int)


def pending_jobs(report: dict, datasets: tuple[str, ...], symbols: list[str], sample_days: list[dt.date]):
    for dataset in datasets:
        for symbol in symbols:
            existing = report["datasets"][dataset][symbol]
            for day in sample_days:
                if not _complete(existing.get(day.isoformat())):
                    yield dataset, symbol, day


def batches(items, size: int):
    """Yield bounded lists so a full daily scan cannot retain all futures."""
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--start", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--end", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--out", required=True)
    parser.add_argument("--full", action="store_true", help="probe every daily file; expensive but exact")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--datasets", default=",".join(DATASETS),
                        help="comma-separated subset of metrics,aggTrades,bookTicker,bookDepth")
    parser.add_argument("--resume", action="store_true", help="continue an exactly matching checkpoint")
    parser.add_argument("--checkpoint-every", type=int, default=100)
    args = parser.parse_args()
    raw = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    symbols = raw.get("symbols") or raw.get("universe")
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("universe requires symbols or universe")
    sample_days = days_between(args.start, args.end, args.full)
    datasets = tuple(dict.fromkeys(piece.strip() for piece in args.datasets.split(",") if piece.strip()))
    if not datasets or any(dataset not in DATASETS for dataset in datasets):
        parser.error("--datasets must be a non-empty subset of " + ",".join(DATASETS))
    if args.checkpoint_every < 1:
        parser.error("--checkpoint-every must be positive")
    symbols = sorted(set(map(str.upper, symbols)))
    out = Path(args.out)
    report = {
        "schema_version": 1,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Binance Vision daily archive HEAD",
        "mode": "full_daily" if args.full else "boundary_sample_only",
        "requested_range": [args.start.isoformat(), args.end.isoformat()],
        "sample_days": [day.isoformat() for day in sample_days],
        "datasets": {dataset: {symbol: {} for symbol in symbols} for dataset in datasets},
    }
    if args.resume:
        resumed = _load_resume(out, datasets, symbols, sample_days, args)
        if resumed is not None:
            report = resumed
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be in 1..32")
    jobs = pending_jobs(report, datasets, symbols, sample_days)
    # Each task is a HEAD only: parallelism reduces wall-clock latency without
    # retaining response bodies or raw market data.
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # At most 4x workers are in-flight.  This is deliberately not
        # executor.map(), which eagerly consumes a large iterable on older
        # Python versions.
        for batch in batches(jobs, args.workers * 4):
            futures = {pool.submit(status, archive_url(dataset, symbol, day)): (dataset, symbol, day)
                       for dataset, symbol, day in batch}
            for future in as_completed(futures):
                dataset, symbol, day = futures[future]
                report["datasets"][dataset][symbol][day.isoformat()] = future.result()
                completed += 1
                if completed % args.checkpoint_every == 0:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_write(out, report)
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(out, report)
    summary = {
        dataset: sum(
            all(item["status"] == 200 for item in daily.values())
            for daily in symbols_report.values()
        )
        for dataset, symbols_report in report["datasets"].items()
    }
    print(json.dumps({"symbols": len(symbols), "sample_days": len(sample_days), "probed_jobs": completed,
                      "all_sample_days_available": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
