from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


aiogram = sys.modules.setdefault("aiogram", types.ModuleType("aiogram"))
if not hasattr(aiogram, "Bot"):
    aiogram.Bot = object

enums = sys.modules.setdefault("aiogram.enums", types.ModuleType("aiogram.enums"))
if not hasattr(enums, "ParseMode"):
    class _ParseMode:
        HTML = "HTML"
    enums.ParseMode = _ParseMode

aiogram_types = sys.modules.setdefault("aiogram.types", types.ModuleType("aiogram.types"))
if not hasattr(aiogram_types, "LinkPreviewOptions"):
    class LinkPreviewOptions:
        def __init__(
            self,
            *,
            is_disabled=None,
            url=None,
            prefer_small_media=None,
            prefer_large_media=None,
            show_above_text=None,
        ):
            self.is_disabled = is_disabled
            self.url = url
            self.prefer_small_media = prefer_small_media
            self.prefer_large_media = prefer_large_media
            self.show_above_text = show_above_text

    aiogram_types.LinkPreviewOptions = LinkPreviewOptions

from app.telegram.publisher import TelegramPublisher


class Message:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send_message(
        self,
        *,
        chat_id,
        text,
        parse_mode,
        link_preview_options,
    ):
        self.calls.append(("send", chat_id, text, parse_mode, link_preview_options))
        return Message(101)

    async def edit_message_text(
        self,
        *,
        chat_id,
        message_id,
        text,
        parse_mode,
        link_preview_options,
    ):
        self.calls.append(
            ("edit", chat_id, message_id, text, parse_mode, link_preview_options)
        )
        return Message(message_id)

    async def delete_message(self, *, chat_id, message_id):
        self.calls.append(("delete", chat_id, message_id))
        return True


def config():
    return SimpleNamespace(
        telegram_channel_id=-1001,
        telegram_timeout_seconds=3,
    )


@pytest.mark.asyncio
async def test_without_image_is_plain_send_message():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    message_id = await publisher.publish("<b>Текст</b>", [])

    assert message_id == 101
    call = bot.calls[0]
    assert call[0] == "send"
    assert call[2] == "<b>Текст</b>"
    assert call[4] is None


@pytest.mark.asyncio
async def test_first_image_is_hidden_link_preview_url():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())
    first = "https://cdn.discordapp.com/first.jpg?x=1&y=2"
    second = "https://cdn.discordapp.com/second.jpg"

    await publisher.publish("Полный текст без URL", [first, second])

    call = bot.calls[0]
    preview = call[4]
    assert call[2] == "Полный текст без URL"
    assert first not in call[2]
    assert second not in call[2]
    assert preview.url == first
    assert preview.prefer_large_media is True
    assert preview.show_above_text is False


@pytest.mark.asyncio
async def test_edit_updates_preview_url():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())
    image = "https://cdn.discordapp.com/new.jpg"

    message_id = await publisher.edit(77, "Новый текст", [image])

    assert message_id == 77
    call = bot.calls[0]
    assert call[0] == "edit"
    assert call[2] == 77
    preview = call[5]
    assert preview.url == image
    assert preview.prefer_large_media is True
    assert preview.show_above_text is False


@pytest.mark.asyncio
async def test_edit_without_image_explicitly_disables_old_preview():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    await publisher.edit(77, "Текст без картинки", [])

    preview = bot.calls[0][5]
    assert preview.is_disabled is True
    assert preview.url is None


@pytest.mark.asyncio
async def test_delete_is_one_message_mapping():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    await publisher.delete(90)

    assert bot.calls == [("delete", -1001, 90)]


@pytest.mark.asyncio
async def test_legacy_native_media_can_be_cleaned_during_transition():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    await publisher.delete_legacy_media([40, 41], strict=True)

    assert bot.calls == [
        ("delete", -1001, 40),
        ("delete", -1001, 41),
    ]
