from __future__ import annotations

import asyncio
import logging

from app.config import Config
from app.services.backup import BackupService
from app.storage.repositories import Repository
from app.telegram.notifications import Notifier

logger = logging.getLogger(__name__)


class PeriodicServices:
    def __init__(
        self,
        config: Config,
        repo: Repository,
        backup: BackupService,
        notifier: Notifier,
    ) -> None:
        self.config = config
        self.repo = repo
        self.backup = backup
        self.notifier = notifier
        self.tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self.tasks = [
            asyncio.create_task(self._backup_loop(), name="lapbase-backup-loop"),
            asyncio.create_task(self._cleanup_loop(), name="lapbase-cleanup-loop"),
        ]

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def _backup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.backup_interval_hours * 3600)
            try:
                await self.backup.create_backup()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Scheduled backup failed")
                await self.notifier.send(f"❌ LapBase backup failed: {type(exc).__name__}: {exc}")

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.cleanup_interval_hours * 3600)
            try:
                count = await self.repo.cleanup_temporary(self.config.temp_data_retention_hours)
                logger.info("Supabase temporary cleanup removed %s stats rows", count)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Scheduled cleanup failed")
                await self.notifier.send(f"❌ LapBase cleanup failed: {type(exc).__name__}: {exc}")
