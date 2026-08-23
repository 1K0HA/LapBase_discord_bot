from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

from app.config import Config
from app.processor.service import PostProcessor
from app.storage.repositories import Repository
from app.telegram.notifications import Notifier
from app.telegram.publisher import TelegramPublisher

logger = logging.getLogger(__name__)


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
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._resume = asyncio.Event()
        self._resume.set()
        self._stop = asyncio.Event()

    def wake(self) -> None:
        self._wake.set()

    async def start(self, paused: bool = False) -> None:
        self._stop.clear()
        if paused:
            self._resume.clear()
        else:
            self._resume.set()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name="lapbase-queue-worker")

    async def stop(self) -> None:
        self._stop.set()
        self._resume.set()
        self._wake.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=15)
            except asyncio.TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()
        self.wake()

    async def _wait(self, timeout: float = 5.0) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def run(self) -> None:
        while not self._stop.is_set():
            await self._resume.wait()
            if self._stop.is_set():
                break

            record = await self.repo.get_oldest_pending()
            if record is None:
                await self._wait(5)
                continue

            # Strict ordering: if the oldest item is waiting for retry, all later items wait too.
            if record.status == "retrying" and record.next_retry_at:
                now = datetime.now(timezone.utc)
                delay = (record.next_retry_at - now).total_seconds()
                if delay > 0:
                    await self._wait(min(delay, 30))
                    continue

            await self.repo.mark_processing(record.discord_message_id)
            try:
                await self._process(record)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._handle_error(record, exc)

    async def _process(self, record) -> None:
        action = record.pending_action
        if action == "delete":
            if record.telegram_message_id is not None:
                await self.publisher.delete(record.telegram_message_id)
            await self.repo.mark_deleted(record.discord_message_id)
            await self.repo.add_stat("deleted", record.discord_message_id, record.discord_channel_id)
            logger.info("Deleted Telegram mapping for Discord message %s", record.discord_message_id)
            return

        try:
            source = await self.discord_client.fetch_source(
                record.discord_channel_id, record.discord_message_id
            )
        except discord.NotFound:
            # Message vanished before it could be published/edited.
            await self.repo.mark_deleted(record.discord_message_id)
            await self.repo.add_stat("deleted", record.discord_message_id, record.discord_channel_id)
            return

        markdown = await self.processor.render(source)
        if not markdown:
            # No text and no supported images: remove a previous publication if one exists.
            if record.telegram_message_id is not None:
                await self.publisher.delete(record.telegram_message_id)
                await self.repo.add_stat("deleted", record.discord_message_id, record.discord_channel_id)
            await self.repo.mark_deleted(record.discord_message_id)
            return

        if action in {"edit", "republish"} and record.telegram_message_id is not None:
            tg_id = await self.publisher.edit(record.telegram_message_id, markdown)
            await self.repo.add_stat("edited", record.discord_message_id, record.discord_channel_id)
        else:
            tg_id = await self.publisher.publish(markdown)
            await self.repo.add_stat("published", record.discord_message_id, record.discord_channel_id)

        await self.repo.mark_published(record.discord_message_id, tg_id)
        logger.info("Published Discord %s -> Telegram %s", record.discord_message_id, tg_id)

    async def _handle_error(self, record, exc: Exception) -> None:
        attempt = record.retry_count + 1
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("Processing failed for Discord message %s", record.discord_message_id)
        await self.repo.add_stat("retry", record.discord_message_id, record.discord_channel_id)

        if attempt >= self.config.max_retries:
            await self.repo.mark_failed(record.discord_message_id, attempt, error)
            await self.repo.add_stat("failed", record.discord_message_id, record.discord_channel_id)
            await self.notifier.send(
                "❌ LapBase: пост окончательно failed\n"
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
            "⚠️ LapBase: ошибка обработки, будет retry\n"
            f"Discord ID: {record.discord_message_id}\n"
            f"Попытка: {attempt}/{self.config.max_retries}\n"
            f"Следующая попытка через {self.config.retry_delay_seconds // 60} мин.\n"
            f"Ошибка: {error[:800]}"
        )
