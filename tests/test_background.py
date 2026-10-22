"""Background task registry: tasks stay referenced and are drained on shutdown."""

import asyncio
import gc

from app.services import background


async def test_spawned_task_survives_garbage_collection():
    done = asyncio.Event()

    async def work():
        await asyncio.sleep(0.01)
        done.set()

    background.spawn(work(), name="gc-test")  # no reference kept by the caller
    gc.collect()
    await asyncio.wait_for(done.wait(), timeout=1)
    await asyncio.sleep(0)
    assert background.pending_count() == 0


async def test_crashing_task_is_logged_not_raised(caplog):
    async def boom():
        raise RuntimeError("kaboom")

    task = background.spawn(boom(), name="boom")
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert "kaboom" in caplog.text


async def test_shutdown_waits_then_cancels_stragglers():
    finished = []

    async def quick():
        await asyncio.sleep(0.01)
        finished.append("quick")

    async def stuck():
        await asyncio.sleep(60)

    background.spawn(quick(), name="quick")
    slow = background.spawn(stuck(), name="stuck")
    await background.shutdown_background_tasks(timeout=0.2)

    assert finished == ["quick"]
    assert slow.cancelled()
    assert background.pending_count() == 0
