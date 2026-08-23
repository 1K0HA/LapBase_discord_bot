from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.logging_setup import configure_logging
from app.processor.service import PostProcessor
from app.processor.translator import Translator
from app.runtime import RuntimeManager
from app.services.backup import BackupService
from app.services.periodic import PeriodicServices
from app.storage.database import Database
from app.storage.repositories import Repository
from app.telegram.admin import create_admin_router, setup_bot_commands
from app.telegram.notifications import Notifier
from app.telegram.post_wizard import create_post_router
from app.telegram.publisher import TelegramPublisher

logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    configure_logging(config)
    logger.info("Starting LapBase v1.0.5")

    db = Database(config)
    bot: Bot | None = None
    periodic: PeriodicServices | None = None
    runtime: RuntimeManager | None = None

    try:
        await db.connect()
        await db.migrate()
        repo = Repository(db)

        bot = Bot(token=config.telegram_bot_token)
        dp = Dispatcher()

        translator = Translator(config)
        processor = PostProcessor(config, translator)
        publisher = TelegramPublisher(bot, config)
        notifier = Notifier(bot, config)
        backup_service = BackupService(config, db)
        periodic = PeriodicServices(config, repo, backup_service, notifier)
        runtime = RuntimeManager(config, repo, bot, processor, publisher, notifier)

        dp.include_router(create_admin_router(config))
        dp.include_router(create_post_router(config))

        await setup_bot_commands(bot, config)
        periodic.start()

        # Admin /stop persists only for the core while Telegram control plane remains available.
        mode = await repo.get_mode()
        if mode != "stopped":
            await runtime.start_core(sync=True)

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            runtime=runtime,
            repo=repo,
            db=db,
            translator=translator,
            backup_service=backup_service,
        )
    finally:
        logger.info("Shutting down LapBase")
        if periodic is not None:
            await periodic.stop()
        # Do not persist 'stopped' on OS shutdown; only /stop should do that.
        if runtime is not None:
            if runtime.worker:
                await runtime.worker.stop()
            if runtime.discord and not runtime.discord.is_closed():
                await runtime.discord.close()
            if runtime.discord_task:
                await asyncio.gather(runtime.discord_task, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
