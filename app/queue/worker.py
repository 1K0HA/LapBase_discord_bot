from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

import discord

from app.config import Config
from app.processor.service import PostProcessor
from app.services.retry_policy import classify_retry
from app.storage.repositories import Repository
from app.telegram.notifications import Notifier
from app.telegram.publisher import TelegramPublisher

logger = logging.getLogger(__name__)

INFRASTRUCTURE_RETRIES = 3


class WorkerState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class WorkerFailure:
    error_type: str
    message: str


class QueueWorker:
    def __init__(
        self,
        config: Config,
        repo: Repository,
        discord_client,
        processor: PostProcessor,
        publisher: TelegramPublisher,
        notifier: Notifier,
    ) -> None:
        self.config = config
        self.repo = repo
        self.discord_client = discord_client
        self.processor = processor
        self.publisher = publisher
        self.notifier = notifier
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._resume = asyncio.Event()
        self._resume.set()
        self._stop = asyncio.Event()
        self._state = WorkerState.STOPPED
        self._last_failure: WorkerFailure | None = None

    @property
    def state(self) -> WorkerState:
        return self._state

    @property
    def last_failure(self) -> WorkerFailure | None:
        return self._last_failure

    @property
    def is_operational(self) -> bool:
        return bool(
            self._task
            and not self._task.done()
            and self._state in {WorkerState.RUNNING, WorkerState.PAUSED}
        )

    def wake(self) -> None:
        self._wake.set()

    async def start(self, paused: bool = False) -> None:
        if self.is_operational:
            if paused:
                self.pause()
            else:
                self.resume()
            return

        # Забираем завершившийся task без повторного выброса старой ошибки.
        if self._task is not None and self._task.done():
            await asyncio.gather(self._task, return_exceptions=True)

        self._stop.clear()
        self._last_failure = None
        if paused:
            self._resume.clear()
            self._state = WorkerState.PAUSED
        else:
            self._resume.set()
            self._state = WorkerState.RUNNING
        self._task = asyncio.create_task(self.run(), name="lapbase-queue-worker")

    async def stop(self) -> None:
        """Идемпотентно останавливает worker даже после аварийного завершения task."""
        self._stop.set()
        self._resume.set()
        self._wake.set()

        task = self._task
        if task is None:
            self._state = WorkerState.STOPPED
            return

        if task.done():
            # gather(return_exceptions=True) забирает старое исключение задачи и не ломает завершение.
            await asyncio.gather(task, return_exceptions=True)
        else:
            try:
                await asyncio.wait_for(task, timeout=15)
            except asyncio.CancelledError:
                if task.cancelled():
                    await asyncio.gather(task, return_exceptions=True)
                else:
                    raise
            except asyncio.TimeoutError:
                logger.warning("QueueWorker не остановился за 15 сек.; выполняется cancellation")
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            except Exception:
                # Защита жизненного цикла: stop/restart/shutdown не должны повторно падать из-за ошибки задачи.
                logger.exception("QueueWorker завершился ошибкой во время stop; shutdown продолжается")

        self._task = None
        self._state = WorkerState.STOPPED

    def pause(self) -> None:
        self._resume.clear()
        if self.is_operational:
            self._state = WorkerState.PAUSED

    def resume(self) -> None:
        self._resume.set()
        if self.is_operational:
            self._state = WorkerState.RUNNING
        self.wake()

    async def _wait(self, timeout: float = 5.0) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def _retry_infrastructure(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Ограниченно повторяет только временные инфраструктурные ошибки."""
        for attempt in range(1, INFRASTRUCTURE_RETRIES + 1):
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                decision = classify_retry(exc)
                if not decision.retryable or attempt >= INFRASTRUCTURE_RETRIES:
                    raise
                delay = min(2 ** (attempt - 1), 5)
                logger.warning(
                    "Временная ошибка QueueWorker operation=%s attempt=%s/%s reason=%s; "
                    "повтор через %s сек.",
                    operation_name,
                    attempt,
                    INFRASTRUCTURE_RETRIES,
                    decision.reason,
                    delay,
                )
                await self._wait(delay)
        raise RuntimeError("Недостижимое состояние infrastructure retry")

    async def run(self) -> None:
        try:
            while not self._stop.is_set():
                await self._resume.wait()
                if self._stop.is_set():
                    break

                record = await self._retry_infrastructure(
                    "get_oldest_pending",
                    self.repo.get_oldest_pending,
                )
                if record is None:
                    await self._wait(5)
                    continue

                # Строгий порядок: пока старейший элемент ждёт retry, более новые тоже ждут.
                if record.status == "retrying" and record.next_retry_at:
                    now = datetime.now(timezone.utc)
                    delay = (record.next_retry_at - now).total_seconds()
                    if delay > 0:
                        await self._wait(min(delay, 30))
                        continue

                await self._retry_infrastructure(
                    "mark_processing",
                    lambda: self.repo.mark_processing(record.discord_message_id),
                )
                try:
                    await self._process(record)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._handle_error(record, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = WorkerState.FAILED
            self._last_failure = WorkerFailure(
                error_type=type(exc).__name__,
                message=str(exc)[:1000],
            )
            logger.exception(
                "QueueWorker аварийно завершён; state=FAILED. "
                "Telegram control plane остаётся доступным для /health и /restart."
            )
            await self.notifier.send(
                "❌ LapBase: QueueWorker аварийно завершён.\n"
                "Состояние: FAILED\n"
                f"Ошибка: {type(exc).__name__}: {str(exc)[:700]}\n"
                "Используйте /health для диагностики и /restart для восстановления."
            )
        finally:
            if self._state is not WorkerState.FAILED:
                self._state = WorkerState.STOPPED

    async def _process(self, record) -> None:
        action = record.pending_action
        if action == "delete":
            if record.telegram_message_id is not None:
                await self.publisher.delete(record.telegram_message_id)
            if record.telegram_media_message_ids:
                await self.publisher.delete_legacy_media(
                    record.telegram_media_message_ids,
                    strict=True,
                )
            await self.repo.mark_deleted(record.discord_message_id)
            await self.repo.add_stat(
                "deleted",
                record.discord_message_id,
                record.discord_channel_id,
            )
            logger.info(
                "Deleted Telegram mapping for Discord message %s",
                record.discord_message_id,
            )
            return

        try:
            source = await self.discord_client.fetch_source(
                record.discord_channel_id,
                record.discord_message_id,
            )
        except discord.NotFound:
            # Исходное сообщение исчезло до публикации или редактирования.
            if record.telegram_message_id is not None:
                await self.publisher.delete(record.telegram_message_id)
            if record.telegram_media_message_ids:
                await self.publisher.delete_legacy_media(
                    record.telegram_media_message_ids,
                    strict=True,
                )
            await self.repo.mark_deleted(record.discord_message_id)
            await self.repo.add_stat(
                "deleted",
                record.discord_message_id,
                record.discord_channel_id,
            )
            return

        html_text = await self.processor.render(source)
        if not html_text:
            # После очистки не осталось поддерживаемого содержимого: удаляем прежнюю публикацию.
            if record.telegram_message_id is not None:
                await self.publisher.delete(record.telegram_message_id)
                await self.repo.add_stat(
                    "deleted",
                    record.discord_message_id,
                    record.discord_channel_id,
                )
            if record.telegram_media_message_ids:
                await self.publisher.delete_legacy_media(
                    record.telegram_media_message_ids,
                    strict=True,
                )
            await self.repo.mark_deleted(record.discord_message_id)
            return

        if action in {"edit", "republish"} and record.telegram_message_id is not None:
            tg_id = await self.publisher.edit(
                record.telegram_message_id,
                html_text,
                source.image_urls,
            )
            # После успешного edit удаляем отдельные media-сообщения, оставшиеся от v1.0.26.
            if record.telegram_media_message_ids:
                await self.publisher.delete_legacy_media(
                    record.telegram_media_message_ids,
                    strict=True,
                )
            await self.repo.add_stat(
                "edited",
                record.discord_message_id,
                record.discord_channel_id,
            )
        else:
            tg_id = await self.publisher.publish(html_text, source.image_urls)
            await self.repo.add_stat(
                "published",
                record.discord_message_id,
                record.discord_channel_id,
            )

        await self.repo.mark_published(record.discord_message_id, tg_id)
        logger.info(
            "Published Discord %s -> Telegram %s",
            record.discord_message_id,
            tg_id,
        )

    async def _handle_error(self, record, exc: Exception) -> None:
        decision = classify_retry(exc)
        attempt = record.retry_count + 1
        error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "Ошибка обработки Discord message %s; retryable=%s; reason=%s",
            record.discord_message_id,
            decision.retryable,
            decision.reason,
        )

        if not decision.retryable:
            await self.repo.mark_failed(record.discord_message_id, attempt, error)
            await self.repo.add_stat(
                "failed",
                record.discord_message_id,
                record.discord_channel_id,
            )
            await self.notifier.send(
                "❌ LapBase: постоянная ошибка, retry не выполняется\n"
                f"Discord ID: {record.discord_message_id}\n"
                f"Канал ID: {record.discord_channel_id}\n"
                f"Причина: {decision.reason}\n"
                f"Ошибка: {error[:800]}"
            )
            self.wake()
            return

        await self.repo.add_stat(
            "retry",
            record.discord_message_id,
            record.discord_channel_id,
        )
        if attempt >= self.config.max_retries:
            await self.repo.mark_failed(record.discord_message_id, attempt, error)
            await self.repo.add_stat(
                "failed",
                record.discord_message_id,
                record.discord_channel_id,
            )
            await self.notifier.send(
                "❌ LapBase: пост окончательно не обработан\n"
                f"Discord ID: {record.discord_message_id}\n"
                f"Канал ID: {record.discord_channel_id}\n"
                f"Попыток: {attempt}\n"
                f"Ошибка: {error[:800]}"
            )
            self.wake()
            return

        await self.repo.mark_retry(
            record.discord_message_id,
            attempt,
            self.config.retry_delay_seconds,
            error,
        )
        await self.notifier.send(
            "⚠️ LapBase: временная ошибка, будет повторная попытка\n"
            f"Discord ID: {record.discord_message_id}\n"
            f"Попытка: {attempt}/{self.config.max_retries}\n"
            f"Следующая попытка через {self.config.retry_delay_seconds // 60} мин.\n"
            f"Ошибка: {error[:800]}"
        )
