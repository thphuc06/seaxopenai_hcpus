"""Seed the configured database; --reset explicitly replaces demo state."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config, db, seed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="replace existing demo rows with fixture state")
    parser.add_argument("--db", type=Path, help="explicit database path (otherwise DB_PATH)")
    args = parser.parse_args(argv)
    path = args.db.resolve() if args.db else config.settings.db_path
    previous = os.environ.get("DB_PATH")
    try:
        # Ingest indexing hooks also read settings; keep them on this database.
        os.environ["DB_PATH"] = str(path)
        config.reload_settings()
        db.init_db()
        if args.reset:
            seed.reset()
            print(f"Reset and seeded: {path}")
        else:
            seeded = seed.seed_if_empty()
            print(f"{'Seeded' if seeded else 'Already populated'}: {path}")
    finally:
        if previous is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = previous
        config.reload_settings()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
