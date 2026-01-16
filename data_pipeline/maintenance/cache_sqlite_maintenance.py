from __future__ import annotations

import argparse
from datetime import datetime, timezone

from ml_engine.cache.sqlite_cache import SqliteCache
from ml_engine.config import cache_db_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vacuum", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    args = ap.parse_args()

    cache = SqliteCache(db_path=cache_db_path())
    deleted = cache.delete_expired(now_utc=datetime.now(timezone.utc))
    if bool(args.vacuum):
        cache.vacuum()
    if bool(args.analyze):
        cache.analyze()

    print({"deleted_expired": int(deleted), "vacuum": bool(args.vacuum), "analyze": bool(args.analyze)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

