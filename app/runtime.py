from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.config import Config
from app.discord.client import DiscordSourceClient
from app.processor.service import PostProcessor
from app.queue.worker import QueueWorker, WorkerFailure, WorkerState
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

    @property
    def worker_state(self) -> WorkerState:
        if self.worker is None:
            return WorkerState.STOPPED
        return self.worker.state

    @property
    def worker_last_failure(self) -> WorkerFailure | None:
        if self.worker is None:
            return None
        return self.worker.last_failure

    @property
    def worker_operational(self) -> bool:
        return bool(self.worker and self.worker.is_operational)

    @property
    def core_healthy(self) -> bool:
        return self.discord_connected and self.worker_operational

    def wake_worker(self) -> None:
        if self.worker:
            self.worker.wake()

    def _create_worker(self) -> QueueWorker:
        if self.discord is None:
            raise RuntimeError("Discord-клиент не создан")
        return QueueWorker(
            self.config,
            self.repo,
            self.discord,
            self.processor,
            self.publisher,
            self.notifier,
        )

    async def _ensure_worker(self, mode: str) -> None:
        if self.worker_operational:
            if self.worker is not None:
                if mode == "paused":
                    self.worker.pause()
                else:
                    self.worker.resume()
            return

        if self.worker is not None:
            await self.worker.stop()
        self.worker = self._create_worker()
        await self.worker.start(paused=(mode == "paused"))

    async def _stop_components(self) -> None:
        if self.worker is not None:
            await self.worker.stop()
            self.worker = None

        if self.discord and not self.discord.is_closed():
            await self.discord.close()
        if self.discord_task:
            await asyncio.gather(self.discord_task, return_exceptions=True)

        self.discord = None
        self.discord_task = None

    async def start_core(self, sync: bool = True) -> None:
        async with self._lock:
            mode = await self.repo.get_mode()

            # Полностью здоровое ядро не пересоздаём.
            if self.discord_connected and self.worker_operational:
                if self.worker is not None:
                    if mode == "paused":
                        self.worker.pause()
                    else:
                        self.worker.resume()
                return

            # Discord может быть здоров, даже если QueueWorker уже FAILED.
            if self.discord_connected and self.discord is not None:
                # Воркер в FAILED или отсутствующий воркер уже не обрабатывает запись, поэтому processing
                # можно безопасно вернуть в очередь перед созданием нового воркера.
                await self.repo.recover_processing()
                if sync:
                    await self.discord.sync_history()
                if mode == "stopped":
                    await self.repo.set_mode("running")
                    mode = "running"
                await self._ensure_worker(mode)
                logger.info(
                    "LapBase worker восстановлен без переподключения Discord; mode=%s",
                    mode,
                )
                return

            # Discord недоступен: сначала полностью останавливаем воркер, только затем
            # возвращаем processing-записи в очередь, чтобы исключить race с активной обработкой.
            await self._stop_components()
            await self.repo.recover_processing()
            self.discord = DiscordSourceClient(
                self.config,
                self.repo,
                self.wake_worker,
                self.notifier,
            )
            self.discord_task = asyncio.create_task(
                self.discord.start(self.config.discord_bot_token),
                name="lapbase-discord",
            )

            ready_task = asyncio.create_task(
                self.discord.ready_event.wait(),
                name="lapbase-discord-ready",
            )
            try:
                done, _ = await asyncio.wait(
                    {ready_task, self.discord_task},
                    timeout=self.config.discord_ready_timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if ready_task in done and ready_task.result():
                    pass
                elif self.discord_task in done:
                    exc = self.discord_task.exception()
                    if exc is None:
                        raise RuntimeError("Discord-клиент завершился до состояния ready")
                    raise RuntimeError(
                        f"Ошибка запуска Discord: {type(exc).__name__}: {exc}"
                    ) from exc
                else:
                    if self.discord and not self.discord.is_closed():
                        await self.discord.close()
                    if self.discord_task and not self.discord_task.done():
                        self.discord_task.cancel()
                        await asyncio.gather(self.discord_task, return_exceptions=True)
                    raise RuntimeError(
                        f"Discord не перешёл в ready за "
                        f"{self.config.discord_ready_timeout_seconds} сек. "
                        "Проверь интернет, bot token, MESSAGE CONTENT INTENT и Discord Gateway."
                    )
            finally:
                if not ready_task.done():
                    ready_task.cancel()
                await asyncio.gather(ready_task, return_exceptions=True)

            if sync:
                await self.discord.sync_history()

            mode = await self.repo.get_mode()
            if mode == "stopped":
                # Режим /stop переживает перезапуск процесса; /start меняет его перед start_core.
                await self.repo.set_mode("running")
                mode = "running"

            await self._ensure_worker(mode)
            logger.info("LapBase core started; mode=%s", mode)

    async def stop_core(self) -> None:
        async with self._lock:
            await self._stop_components()
            await self.repo.set_mode("stopped")
            logger.info("LapBase core stopped")

    async def shutdown(self) -> None:
        """Системное завершение без изменения сохранённого административного режима."""
        async with self._lock:
            await self._stop_components()
            logger.info("LapBase runtime shutdown complete")

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
        if not self.core_healthy:
            await self.start_core(sync=True)
        if self.worker:
            self.worker.resume()

    async def restart(self) -> None:
        await self.stop_core()
        await self.repo.set_mode("running")
        await self.start_core(sync=True)

    async def sync_now(self) -> int:
        if not self.discord_connected or not self.discord:
            raise RuntimeError("Ядро Discord остановлено")
        return await self.discord.sync_history()
