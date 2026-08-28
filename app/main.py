from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.instance_lock import (
    INSTANCE_ALREADY_RUNNING_EXIT_CODE,
    InstanceAlreadyRunningError,
    InstanceLock,
)
from app.logging_setup import configure_logging
from app.processor.service import PostProcessor
from app.processor.translator import Translator
from app.runtime import RuntimeManager
from app.services.backup import BackupService
from app.services.periodic import PeriodicServices
from app.storage.database import Database
from app.storage.models import POST_RECORD_COLUMNS
from app.storage.repositories import Repository
from app.telegram.admin import create_admin_router, setup_bot_commands
from app.telegram.notifications import Notifier
from app.telegram.post_wizard import create_post_router
from app.telegram.publisher import TelegramPublisher
from app.version import get_version

logger = logging.getLogger(__name__)


async def main() -> None:
    """Запускает Telegram control plane и рабочее ядро LapBase."""
    config = load_config()
    configure_logging(config)
    version = get_version()
    logger.info("Запуск LapBase v%s", version)

    instance_lock = InstanceLock(
        config.root_dir / ".1kds" / "state" / "lapbase.lock",
        version,
    )
    try:
        instance_lock.acquire()
    except InstanceAlreadyRunningError:
        logger.error(
            "LapBase уже запущен. Второй экземпляр заблокирован до подключения к БД и миграций."
        )
        raise SystemExit(INSTANCE_ALREADY_RUNNING_EXIT_CODE) from None

    db = Database(config)
    bot: Bot | None = None
    periodic: PeriodicServices | None = None
    runtime: RuntimeManager | None = None

    try:
        await db.connect()
        await db.migrate()
        await db.verify_table_columns("posts", POST_RECORD_COLUMNS)
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

        # /stop останавливает только рабочее ядро; Telegram control plane остаётся доступным.
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
        logger.info("Завершение LapBase")
        if periodic is not None:
            try:
                await periodic.stop()
            except Exception:
                logger.exception("Ошибка при остановке periodic services")

        if runtime is not None:
            try:
                await runtime.shutdown()
            except Exception:
                logger.exception("Ошибка при остановке runtime")

        if bot is not None:
            try:
                await bot.session.close()
            except Exception:
                logger.exception("Ошибка при закрытии Telegram session")

        try:
            await db.close()
        except Exception:
            logger.exception("Ошибка при закрытии БД")
        finally:
            instance_lock.release()


if __name__ == "__main__":
    asyncio.run(main())
