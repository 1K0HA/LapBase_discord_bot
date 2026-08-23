from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.config import Config
from app.discord.client import DiscordSourceClient
from app.processor.service import PostProcessor
from app.queue.worker import QueueWorker
from app.storage.repositories import Repository
from app.telegram.notifications import Notifier
from app.telegram.publisher import TelegramPublisher

logger = logging.getLogger(__name__)


class RuntimeManager:
    def __init__(
        self,
        config: Config,
        repo: Repository,
        bot: Bot,
        processor: PostProcessor,
        publisher: TelegramPublisher,
        notifier: Notifier,
    ) -> None:
        self.config = config
        self.repo = repo
        self.bot = bot
        self.processor = processor
        self.publisher = publisher
        self.notifier = notifier
        self.discord: DiscordSourceClient | None = None
        self.discord_task: asyncio.Task | None = None
        self.worker: QueueWorker | None = None
        self._lock = asyncio.Lock()

    @property
    def discord_connected(self) -> bool:
        return bool(self.discord and self.discord.is_ready() and not self.discord.is_closed())

    def wake_worker(self) -> None:
        if self.worker:
            self.worker.wake()

    async def start_core(self, sync: bool = True) -> None:
        async with self._lock:
            mode = await self.repo.get_mode()
            if self.discord_connected:
                if mode == "paused" and self.worker:
                    self.worker.pause()
                return

            await self.repo.recover_processing()
            if self.discord is not None:
                try:
                    if not self.discord.is_closed():
                        await self.discord.close()
                finally:
                    if self.discord_task:
                        await asyncio.gather(self.discord_task, return_exceptions=True)
                self.discord = None
                self.discord_task = None
            self.discord = DiscordSourceClient(self.config, self.repo, self.wake_worker, self.notifier)
            self.worker = QueueWorker(
                self.config,
                self.repo,
                self.discord,
                self.processor,
                self.publisher,
                self.notifier,
            )
            self.discord_task = asyncio.create_task(
                self.discord.start(self.config.discord_bot_token), name="lapbase-discord"
            )

            ready_task = asyncio.create_task(
                self.discord.ready_event.wait(), name="lapbase-discord-ready"
            )
            try:
                done, _ = await asyncio.wait(
                    {ready_task, self.discord_task},
                    timeout=30,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if ready_task in done and ready_task.result():
                    pass
                elif self.discord_task in done:
                    exc = self.discord_task.exception()
                    if exc is None:
                        raise RuntimeError("Discord client stopped before becoming ready")
                    raise RuntimeError(
                        f"Discord startup failed: {type(exc).__name__}: {exc}"
                    ) from exc
                else:
                    if self.discord and not self.discord.is_closed():
                        await self.discord.close()
                    if self.discord_task and not self.discord_task.done():
                        self.discord_task.cancel()
                        await asyncio.gather(self.discord_task, return_exceptions=True)
                    raise RuntimeError(
                        "Discord did not become ready within 30 seconds. "
                        "Check internet access, bot token, and Discord Gateway availability."
                    )
            finally:
                if not ready_task.done():
                    ready_task.cancel()
                await asyncio.gather(ready_task, return_exceptions=True)

            if sync:
                await self.discord.sync_history()
            mode = await self.repo.get_mode()
            if mode == "stopped":
                # Explicit /stop survives process restarts. /start changes it before calling start_core.
                await self.repo.set_mode("running")
                mode = "running"
            await self.worker.start(paused=(mode == "paused"))
            logger.info("LapBase core started; mode=%s", mode)

    async def stop_core(self) -> None:
        async with self._lock:
            if self.worker:
                await self.worker.stop()
                self.worker = None
            if self.discord and not self.discord.is_closed():
                await self.discord.close()
            if self.discord_task:
                await asyncio.gather(self.discord_task, return_exceptions=True)
            self.discord = None
            self.discord_task = None
            await self.repo.set_mode("stopped")
            logger.info("LapBase core stopped")

    async def start_from_admin(self) -> None:
        await self.repo.set_mode("running")
        await self.start_core(sync=True)
        if self.worker:
            self.worker.resume()

    async def pause(self) -> None:
        await self.repo.set_mode("paused")
        if self.worker:
            self.worker.pause()

    async def resume(self) -> None:
        await self.repo.set_mode("running")
        if not self.discord_connected:
            await self.start_core(sync=True)
        if self.worker:
            self.worker.resume()

    async def restart(self) -> None:
        await self.stop_core()
        await self.repo.set_mode("running")
        await self.start_core(sync=True)

    async def sync_now(self) -> int:
        if not self.discord_connected or not self.discord:
            raise RuntimeError("Discord core is stopped")
        return await self.discord.sync_history()
