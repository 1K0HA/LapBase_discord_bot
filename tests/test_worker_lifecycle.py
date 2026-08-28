from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

# Для lifecycle-теста внешние SDK не нужны: подменяем только импортные контракты.
discord_stub = types.ModuleType("discord")
discord_stub.NotFound = type("NotFound", (Exception,), {})
sys.modules.setdefault("discord", discord_stub)

processor_stub = types.ModuleType("app.processor.service")
processor_stub.PostProcessor = object
sys.modules.setdefault("app.processor.service", processor_stub)

repo_stub = types.ModuleType("app.storage.repositories")
repo_stub.Repository = object
sys.modules.setdefault("app.storage.repositories", repo_stub)

notifier_stub = types.ModuleType("app.telegram.notifications")
notifier_stub.Notifier = object
sys.modules.setdefault("app.telegram.notifications", notifier_stub)

publisher_stub = types.ModuleType("app.telegram.publisher")
publisher_stub.TelegramPublisher = object
sys.modules.setdefault("app.telegram.publisher", publisher_stub)

from app.queue.worker import QueueWorker, WorkerState


class LogicBrokenRepo:
    async def get_oldest_pending(self):
        raise TypeError(
            "PostRecord.__init__() got an unexpected keyword argument "
            "'future_additive_column'"
        )


class NoopNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def config():
    return SimpleNamespace(
        max_retries=5,
        retry_delay_seconds=300,
    )


@pytest.mark.asyncio
async def test_logic_error_moves_worker_to_failed_and_keeps_failure_visible():
    notifier = NoopNotifier()
    worker = QueueWorker(
        config(),
        LogicBrokenRepo(),
        discord_client=object(),
        processor=object(),
        publisher=object(),
        notifier=notifier,
    )

    await worker.start()
    for _ in range(50):
        if worker.state is WorkerState.FAILED:
            break
        await asyncio.sleep(0)

    assert worker.state is WorkerState.FAILED
    assert worker.last_failure is not None
    assert worker.last_failure.error_type == "TypeError"
    assert "future_additive_column" in worker.last_failure.message
    assert notifier.messages
    assert "/restart" in notifier.messages[-1]

    # Regression для traceback пользователя: stop не должен повторно выбрасывать task exception.
    await worker.stop()
    assert worker.state is WorkerState.STOPPED


@pytest.mark.asyncio
async def test_stop_consumes_already_failed_task_exception():
    worker = QueueWorker(
        config(),
        LogicBrokenRepo(),
        discord_client=object(),
        processor=object(),
        publisher=object(),
        notifier=NoopNotifier(),
    )

    async def crash():
        raise TypeError("old worker task crash")

    task = asyncio.create_task(crash())
    await asyncio.sleep(0)
    worker._task = task  # regression setup: task уже завершена с exception
    worker._state = WorkerState.FAILED

    await worker.stop()

    assert worker.state is WorkerState.STOPPED



@pytest.mark.asyncio
async def test_stop_accepts_already_cancelled_worker_task():
    worker = QueueWorker(
        config(),
        LogicBrokenRepo(),
        discord_client=object(),
        processor=object(),
        publisher=object(),
        notifier=NoopNotifier(),
    )

    async def waiting():
        await asyncio.sleep(60)

    task = asyncio.create_task(waiting())
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    worker._task = task
    worker._state = WorkerState.RUNNING

    await worker.stop()

    assert worker.state is WorkerState.STOPPED
