from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.config import Config

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, config: Config) -> None:
        self.bot = bot
        self.config = config

    async def send(self, text: str) -> None:
        try:
            async with asyncio.timeout(self.config.telegram_timeout_seconds):
                await self.bot.send_message(self.config.telegram_admin_chat_id, text)
        except Exception:
            logger.exception("Не удалось отправить уведомление администратору")
