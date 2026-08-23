from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord

from app.config import Config
from app.models import SourceMessage
from app.storage.repositories import Repository

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class DiscordSourceClient(discord.Client):
    def __init__(self, config: Config, repo: Repository, wake_worker, notifier=None) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config
        self.repo = repo
        self.wake_worker = wake_worker
        self.notifier = notifier
        self.ready_event = asyncio.Event()

    async def on_ready(self) -> None:
        logger.info("Discord ready as %s (%s)", self.user, getattr(self.user, "id", None))
        self.ready_event.set()

    async def on_disconnect(self) -> None:
        logger.warning("Discord disconnected")
        if self.notifier:
            await self.notifier.send("⚠️ LapBase: Discord disconnected. Ожидаю автоматическое переподключение.")

    async def on_resumed(self) -> None:
        logger.info("Discord session resumed")
        if self.notifier:
            await self.notifier.send("✅ LapBase: Discord connection recovered.")

    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id not in self.config.discord_channel_ids:
            return
        inserted = await self.repo.enqueue_new(message.id, message.channel.id, message.created_at)
        if inserted:
            logger.info("Queued Discord message %s from channel %s", message.id, message.channel.id)
            self.wake_worker()

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.channel_id not in self.config.discord_channel_ids:
            return
        if await self.repo.enqueue_edit(payload.message_id, payload.channel_id):
            logger.info("Queued edit for Discord message %s", payload.message_id)
            self.wake_worker()
            return
        # Rare race: an edit can arrive before the create event was persisted.
        try:
            channel = await self.get_text_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if await self.repo.enqueue_new(message.id, payload.channel_id, message.created_at):
                self.wake_worker()
        except Exception:
            logger.exception("Could not recover unknown edited message %s", payload.message_id)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.channel_id not in self.config.discord_channel_ids:
            return
        if await self.repo.enqueue_delete(payload.message_id, payload.channel_id):
            logger.info("Queued delete for Discord message %s", payload.message_id)
            self.wake_worker()

    async def get_text_channel(self, channel_id: int):
        channel = self.get_channel(channel_id)
        if channel is None:
            channel = await self.fetch_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise RuntimeError(f"Discord channel {channel_id} is not a text channel/thread")
        return channel

    async def fetch_source(self, channel_id: int, message_id: int) -> SourceMessage:
        channel = await self.get_text_channel(channel_id)
        message = await channel.fetch_message(message_id)

        image_urls: list[str] = []
        for att in message.attachments:
            content_type = (att.content_type or "").lower()
            suffix = ("." + att.filename.rsplit(".", 1)[-1].lower()) if "." in att.filename else ""
            if content_type == "image/gif" or suffix == ".gif":
                continue
            if content_type.startswith("image/") or suffix in IMAGE_EXTENSIONS:
                image_urls.append(att.url)

        user_mentions = {
            user.id: getattr(user, "display_name", None) or user.name for user in message.mentions
        }
        role_mentions = {role.id: role.name for role in message.role_mentions}

        return SourceMessage(
            discord_message_id=message.id,
            discord_channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", str(message.channel.id)),
            content=message.content or "",
            created_at=message.created_at,
            image_urls=image_urls,
            user_mentions=user_mentions,
            role_mentions=role_mentions,
        )

    async def sync_history(self) -> int:
        after = datetime.now(timezone.utc) - timedelta(hours=self.config.sync_hours)
        collected: list[tuple[datetime, int, int]] = []
        for channel_id in self.config.discord_channel_ids:
            try:
                channel = await self.get_text_channel(channel_id)
                async for message in channel.history(after=after, oldest_first=True, limit=None):
                    collected.append((message.created_at, message.id, channel.id))
            except Exception:
                logger.exception("Failed to sync Discord channel %s", channel_id)

        collected.sort(key=lambda item: (item[0], item[1]))
        inserted_count = 0
        for created_at, message_id, channel_id in collected:
            if await self.repo.enqueue_new(message_id, channel_id, created_at):
                inserted_count += 1
        if inserted_count:
            self.wake_worker()
        logger.info("Discord sync complete; queued %s missing messages", inserted_count)
        return inserted_count
