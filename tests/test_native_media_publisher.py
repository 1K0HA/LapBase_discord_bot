from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


# publisher.py должен тестироваться без реального сетевого SDK.
aiogram = sys.modules.setdefault("aiogram", types.ModuleType("aiogram"))
if not hasattr(aiogram, "Bot"):
    aiogram.Bot = object

enums = sys.modules.setdefault("aiogram.enums", types.ModuleType("aiogram.enums"))
if not hasattr(enums, "ParseMode"):
    class _ParseMode:
        HTML = "HTML"
    enums.ParseMode = _ParseMode

aiogram_types = sys.modules.setdefault("aiogram.types", types.ModuleType("aiogram.types"))
if not hasattr(aiogram_types, "InputMediaPhoto"):
    class InputMediaPhoto:
        def __init__(self, media):
            self.media = media
    aiogram_types.InputMediaPhoto = InputMediaPhoto

from app.telegram.publisher import TelegramPublisher


class Message:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeBot:
    def __init__(self) -> None:
        self.next_id = 100
        self.calls: list[tuple] = []
        self.fail_text = False

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    async def send_photo(self, *, chat_id, photo):
        self.calls.append(("photo", chat_id, photo))
        return Message(self._id())

    async def send_media_group(self, *, chat_id, media):
        urls = [item.media for item in media]
        self.calls.append(("media_group", chat_id, urls))
        return [Message(self._id()) for _ in urls]

    async def send_message(self, *, chat_id, text, parse_mode):
        self.calls.append(("text", chat_id, text, parse_mode))
        if self.fail_text:
            raise TimeoutError("text timeout")
        return Message(self._id())

    async def delete_message(self, *, chat_id, message_id):
        self.calls.append(("delete", chat_id, message_id))
        return True


def config():
    return SimpleNamespace(
        telegram_channel_id=-1001,
        telegram_timeout_seconds=3,
    )


@pytest.mark.asyncio
async def test_one_image_is_native_photo_then_full_text():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    publication = await publisher.publish("<b>Текст</b>", ["https://cdn/a.jpg"])

    assert [call[0] for call in bot.calls] == ["photo", "text"]
    assert publication.media_message_ids == [101]
    assert publication.text_message_id == 102
    assert "https://cdn/a.jpg" not in bot.calls[1][2]


@pytest.mark.asyncio
async def test_multiple_images_are_media_group_then_text():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    publication = await publisher.publish(
        "Полный текст",
        ["https://cdn/a.jpg", "https://cdn/b.jpg", "https://cdn/c.jpg"],
    )

    assert [call[0] for call in bot.calls] == ["media_group", "text"]
    assert bot.calls[0][2] == [
        "https://cdn/a.jpg",
        "https://cdn/b.jpg",
        "https://cdn/c.jpg",
    ]
    assert publication.media_message_ids == [101, 102, 103]
    assert publication.text_message_id == 104


@pytest.mark.asyncio
async def test_text_failure_removes_created_media_best_effort():
    bot = FakeBot()
    bot.fail_text = True
    publisher = TelegramPublisher(bot, config())

    with pytest.raises(TimeoutError):
        await publisher.publish("Текст", ["https://cdn/a.jpg"])

    assert [call[0] for call in bot.calls] == ["photo", "text", "delete"]
    assert bot.calls[-1][2] == 101


@pytest.mark.asyncio
async def test_replace_creates_new_bundle_before_removing_old_bundle():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    publication = await publisher.replace(
        old_text_message_id=50,
        old_media_message_ids=[40, 41],
        html_text="Новый текст",
        image_urls=["https://cdn/new.jpg"],
    )

    assert publication.media_message_ids == [101]
    assert publication.text_message_id == 102
    assert [call[0] for call in bot.calls] == [
        "photo",
        "text",
        "delete",
        "delete",
        "delete",
    ]
    assert [call[2] for call in bot.calls[2:]] == [40, 41, 50]


@pytest.mark.asyncio
async def test_delete_publication_deletes_media_and_text():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, config())

    await publisher.delete_publication(60, [51, 52])

    assert [call[2] for call in bot.calls] == [51, 52, 60]
