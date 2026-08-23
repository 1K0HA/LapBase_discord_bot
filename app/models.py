from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SourceMessage:
    discord_message_id: int
    discord_channel_id: int
    channel_name: str
    content: str
    created_at: datetime
    image_urls: list[str] = field(default_factory=list)
    user_mentions: dict[int, str] = field(default_factory=dict)
    role_mentions: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessedPost:
    markdown: str
    channel_name: str
    image_urls: list[str]
