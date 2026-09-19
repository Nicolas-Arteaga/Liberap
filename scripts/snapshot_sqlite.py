"""Create a consistent SQLite snapshot without relying on a raw file copy."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: snapshot_sqlite.py SOURCE.db DESTINATION.db", file=sys.stderr)
        return 2
    source, destination = map(Path, sys.argv[1:])
    if not source.is_file():
        print(f"source not found: {source}", file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True) as read_conn:
        with sqlite3.connect(destination) as write_conn:
            read_conn.backup(write_conn)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
