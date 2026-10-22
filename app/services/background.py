"""Tracking for fire-and-forget background tasks.

``asyncio.create_task`` only keeps a weak reference to the task, so a task
whose result nobody holds can be garbage-collected mid-run. This module keeps
a strong reference until each task finishes and lets the app wait for (or
cancel) in-flight reviews on shutdown.
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()

# How long shutdown waits for running reviews before cancelling them.
SHUTDOWN_GRACE_SECONDS = 20.0


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    """Start a background task and keep it alive until it completes."""
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if task.cancelled():
        logger.warning(f"Background task {task.get_name()} was cancelled")
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"Background task {task.get_name()} crashed: {exc!r}")


def pending_count() -> int:
    """Number of background tasks still running."""
    return len(_tasks)


async def shutdown_background_tasks(timeout: float = SHUTDOWN_GRACE_SECONDS) -> None:
    """Wait for running tasks, cancelling any still running after ``timeout``."""
    if not _tasks:
        return
    logger.info(f"Waiting for {len(_tasks)} background task(s) to finish...")
    done, pending = await asyncio.wait(set(_tasks), timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning(f"Cancelled {len(pending)} background task(s) at shutdown")
