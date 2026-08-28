from __future__ import annotations

import asyncio
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
        # Рано обнаруживаем смешанную установку старого renderer и нового publisher.
        if html_text.startswith("**Источник официальный DISCORD:"):
            raise ValueError(
                "Обнаружен старый Markdown renderer. Замени renderer.py, service.py и publisher.py вместе."
            )
        if "\\#autopost\\@lapbase" in html_text:
            raise ValueError(
                "Обнаружен старый экранированный autopost-tag. Замени renderer.py версией для send_message."
            )

    @staticmethod
    def _link_preview_options(
        image_urls: list[str],
        *,
        disable_when_empty: bool = False,
    ):
        """Создаёт preview только из первой Discord-картинки, не добавляя URL в текст."""
        from aiogram.types import LinkPreviewOptions

        if image_urls:
            return LinkPreviewOptions(
                url=image_urls[0],
                prefer_large_media=True,
                show_above_text=False,
            )
        if disable_when_empty:
            # При edit явно отключаем старый preview, если картинка была удалена в Discord.
            return LinkPreviewOptions(is_disabled=True)
        return None

    @staticmethod
    def _already_deleted(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "message to delete not found" in text
            or "message not found" in text
            or "message identifier is not specified" in text
        )

    async def _delete_ids(self, message_ids: list[int], *, strict: bool) -> None:
        first_error: Exception | None = None
        for message_id in message_ids:
            try:
                async with asyncio.timeout(self.config.telegram_timeout_seconds):
                    await self.bot.delete_message(
                        chat_id=self.config.telegram_channel_id,
                        message_id=message_id,
                    )
            except Exception as exc:
                if self._already_deleted(exc):
                    logger.info("Telegram message %s уже отсутствует", message_id)
                    continue
                logger.warning(
                    "Не удалось удалить Telegram message %s",
                    message_id,
                    exc_info=True,
                )
                if first_error is None:
                    first_error = exc

        if strict and first_error is not None:
            raise first_error

    async def publish(self, html_text: str, image_urls: list[str]) -> int:
        """Публикует один Telegram message; первая картинка задаётся как link preview."""
        self._validate_html_text(html_text)
        preview = self._link_preview_options(image_urls)
        async with asyncio.timeout(self.config.telegram_timeout_seconds):
            message = await self.bot.send_message(
                chat_id=self.config.telegram_channel_id,
                text=html_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=preview,
            )
        return int(message.message_id)

    async def edit(
        self,
        telegram_message_id: int,
        html_text: str,
        image_urls: list[str],
    ) -> int:
        """Обновляет текст и preview в существующем Telegram message."""
        self._validate_html_text(html_text)
        preview = self._link_preview_options(
            image_urls,
            disable_when_empty=True,
        )
        async with asyncio.timeout(self.config.telegram_timeout_seconds):
            result = await self.bot.edit_message_text(
                chat_id=self.config.telegram_channel_id,
                message_id=telegram_message_id,
                text=html_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=preview,
            )
        if hasattr(result, "message_id"):
            return int(result.message_id)
        return telegram_message_id

    async def delete(self, telegram_message_id: int) -> None:
        """Удаляет одно основное Telegram message; повторный delete считается идемпотентным."""
        await self._delete_ids([telegram_message_id], strict=True)

    async def delete_legacy_media(
        self,
        media_message_ids: list[int],
        *,
        strict: bool,
    ) -> None:
        """Удаляет media bundle, оставшийся после краткого периода native-media v1.0.26."""
        if media_message_ids:
            await self._delete_ids(media_message_ids, strict=strict)
