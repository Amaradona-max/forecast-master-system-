from __future__ import annotations

import gzip
import os
import time
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml_engine.config import monitoring_dir, monitoring_retain_days_compressed, monitoring_retain_days_uncompressed, monitoring_rotate_max_bytes


def _utc_today() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _compress_file(src: Path) -> Path | None:
    if not src.exists() or src.suffix == ".gz":
        return None
    dst = Path(str(src) + ".gz")
    if dst.exists():
        return dst
    with src.open("rb") as f_in, gzip.open(dst, "wb") as f_out:
        while True:
            chunk = f_in.read(1024 * 1024)
            if not chunk:
                break
            f_out.write(chunk)
    with contextlib.suppress(Exception):
        src.unlink()
    return dst


def _should_rollover(p: Path, *, max_bytes: int, today: datetime) -> bool:
    try:
        st = p.stat()
    except Exception:
        return False
    if st.st_size > max_bytes:
        return True
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return mtime < today


def _rollover(p: Path, *, today: datetime) -> Path | None:
    try:
        st = p.stat()
    except Exception:
        return None
    day = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y%m%d")
    base = p.with_name(f"{p.stem}.{day}{p.suffix}")
    cand = base
    for i in range(1, 1000):
        if not cand.exists():
            break
        cand = p.with_name(f"{p.stem}.{day}.{i:03d}{p.suffix}")
    try:
        p.rename(cand)
        p.touch()
        os.utime(p, (time.time(), time.time()))
        return cand
    except Exception:
        return None


def main() -> int:
    md = monitoring_dir()
    md.mkdir(parents=True, exist_ok=True)
    max_b = int(monitoring_rotate_max_bytes())
    keep_uncompressed_days = int(monitoring_retain_days_uncompressed())
    keep_compressed_days = int(monitoring_retain_days_compressed())

    today = _utc_today()
    cutoff_uncompressed = today - timedelta(days=keep_uncompressed_days)
    cutoff_compressed = today - timedelta(days=keep_compressed_days)

    for p in sorted(md.glob("*.jsonl")):
        if _should_rollover(p, max_bytes=max_b, today=today):
            rolled = _rollover(p, today=today)
            if rolled is not None:
                with contextlib.suppress(Exception):
                    rolled.touch()

    for p in sorted(md.glob("*.jsonl")):
        try:
            st = p.stat()
        except Exception:
            continue
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if mtime <= cutoff_uncompressed:
            _compress_file(p)

    for p in sorted(md.glob("*.jsonl.gz")):
        try:
            st = p.stat()
        except Exception:
            continue
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if mtime <= cutoff_compressed:
            with contextlib.suppress(Exception):
                p.unlink()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
