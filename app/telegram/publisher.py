from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InputRichMessage

from app.config import Config

logger = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(self, bot: Bot, config: Config) -> None:
        self.bot = bot
        self.config = config

    def rich(self, markdown: str) -> InputRichMessage:
        return InputRichMessage(markdown=markdown, skip_entity_detection=True)

    async def publish(self, markdown: str) -> int:
        message = await self.bot.send_rich_message(
            chat_id=self.config.telegram_channel_id,
            rich_message=self.rich(markdown),
        )
        return message.message_id

    async def edit(self, telegram_message_id: int, markdown: str) -> int:
        result = await self.bot.edit_message_text(
            chat_id=self.config.telegram_channel_id,
            message_id=telegram_message_id,
            rich_message=self.rich(markdown),
        )
        if hasattr(result, "message_id"):
            return result.message_id
        return telegram_message_id

    async def delete(self, telegram_message_id: int) -> None:
        await self.bot.delete_message(
            chat_id=self.config.telegram_channel_id,
            message_id=telegram_message_id,
        )
