from __future__ import annotations

import argparse

from ml_engine.cache.sqlite_cache import SqliteCache, recover_corrupt_sqlite_db
from ml_engine.config import cache_db_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recover", action="store_true")
    args = ap.parse_args()

    db = cache_db_path()
    ok = False
    try:
        ok = bool(SqliteCache(db_path=db).quick_check())
    except Exception:
        ok = False

    if ok:
        print({"ok": True, "recovered": False})
        return 0

    if bool(args.recover):
        recovered = bool(recover_corrupt_sqlite_db(db_path=db))
        print({"ok": False, "recovered": bool(recovered)})
        return 0 if recovered else 2

    print({"ok": False, "recovered": False})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

