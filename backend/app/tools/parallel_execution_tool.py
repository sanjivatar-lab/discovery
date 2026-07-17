"""ParallelExecutionTool — the two parallelism primitives the rest of the
system builds on:

- `run_cpu_bound`: dispatches picklable, module-level worker functions onto a
  shared ProcessPoolExecutor for genuinely CPU-bound work (tree-sitter
  parsing). Safe under Windows' `spawn` start method because workers are
  plain top-level functions, not closures/lambdas/bound methods.
- `run_bounded`: runs a list of coroutines with an asyncio.Semaphore to cap
  concurrency (backpressure) for IO/LLM-bound subagent work, isolating
  per-item failures so one bad item doesn't sink the whole batch.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Awaitable, Callable, List, Sequence, TypeVar

from app.core.config import settings

T = TypeVar("T")
R = TypeVar("R")

_PROCESS_POOL: ProcessPoolExecutor | None = None


def get_process_pool() -> ProcessPoolExecutor:
    global _PROCESS_POOL
    if _PROCESS_POOL is None:
        _PROCESS_POOL = ProcessPoolExecutor(max_workers=settings.max_process_workers)
    return _PROCESS_POOL


def shutdown_process_pool() -> None:
    global _PROCESS_POOL
    if _PROCESS_POOL is not None:
        _PROCESS_POOL.shutdown(wait=True, cancel_futures=True)
        _PROCESS_POOL = None


async def run_cpu_bound(fn: Callable[[T], R], items: Sequence[T]) -> List[R | Exception]:
    """Run `fn(item)` for each item on the shared process pool concurrently."""
    loop = asyncio.get_running_loop()
    pool = get_process_pool()
    futures = [loop.run_in_executor(pool, fn, item) for item in items]
    results: List[R | Exception] = []
    for fut in futures:
        try:
            results.append(await fut)
        except Exception as exc:  # noqa: BLE001 - isolate per-item failures
            results.append(exc)
    return results


async def run_bounded(
    coro_fns: Sequence[Callable[[], Awaitable[R]]],
    max_concurrency: int | None = None,
) -> List[R | Exception]:
    """Run a batch of zero-arg async callables with bounded concurrency."""
    semaphore = asyncio.Semaphore(max_concurrency or settings.max_concurrent_subagents)

    async def _guarded(coro_fn: Callable[[], Awaitable[R]]) -> R | Exception:
        async with semaphore:
            try:
                return await coro_fn()
            except Exception as exc:  # noqa: BLE001 - isolate per-item failures
                return exc

    return await asyncio.gather(*(_guarded(fn) for fn in coro_fns))
