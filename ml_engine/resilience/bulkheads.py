from __future__ import annotations

import asyncio
import contextvars
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar


T = TypeVar("T")


IO_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="io")
CPU_POOL = ThreadPoolExecutor(max_workers=(os.cpu_count() or 4), thread_name_prefix="cpu")


async def run_io(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(IO_POOL, lambda: ctx.run(fn, *args, **kwargs))


async def run_cpu(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(CPU_POOL, lambda: ctx.run(fn, *args, **kwargs))

