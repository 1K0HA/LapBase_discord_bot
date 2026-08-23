from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PostRecord:
    discord_message_id: int
    discord_channel_id: int
    telegram_message_id: int | None
    status: str
    pending_action: str
    retry_count: int
    next_retry_at: datetime | None
    source_created_at: datetime
    queued_at: datetime
    published_at: datetime | None
    updated_at: datetime
    last_error: str | None
