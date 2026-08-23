from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from app.config import Config

logger = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(self, bot: Bot, config: Config) -> None:
        self.bot = bot
        self.config = config

    @staticmethod
    def _validate_html_text(html_text: str) -> None:
        # Detect a mixed old/new deployment early instead of publishing broken formatting.
        if html_text.startswith("**Источник официальный DISCORD:"):
            raise ValueError(
                "Legacy Markdown renderer detected. Replace renderer.py, service.py and publisher.py together."
            )
        if "\\#autopost\\@lapbase" in html_text:
            raise ValueError(
                "Legacy escaped autopost tag detected. Replace renderer.py with the send_message version."
            )

    async def publish(self, html_text: str) -> int:
        self._validate_html_text(html_text)
        message = await self.bot.send_message(
            chat_id=self.config.telegram_channel_id,
            text=html_text,
            parse_mode=ParseMode.HTML,
        )
        return message.message_id

    async def edit(self, telegram_message_id: int, html_text: str) -> int:
        self._validate_html_text(html_text)
        result = await self.bot.edit_message_text(
            chat_id=self.config.telegram_channel_id,
            message_id=telegram_message_id,
            text=html_text,
            parse_mode=ParseMode.HTML,
        )
        if hasattr(result, "message_id"):
            return result.message_id
        return telegram_message_id

    async def delete(self, telegram_message_id: int) -> None:
        await self.bot.delete_message(
            chat_id=self.config.telegram_channel_id,
            message_id=telegram_message_id,
        )
