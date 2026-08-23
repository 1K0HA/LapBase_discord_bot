from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.storage.database import Database
from app.storage.models import PostRecord

PENDING_STATUSES = ("queued", "processing", "retrying")


def _record(row) -> PostRecord | None:
    if row is None:
        return None
    return PostRecord(**dict(row))


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @property
    def pool(self):
        return self.db.require_pool()

    async def enqueue_new(
        self,
        message_id: int,
        channel_id: int,
        created_at: datetime,
    ) -> bool:
        row = await self.pool.fetchrow(
            """
            INSERT INTO posts(
                discord_message_id, discord_channel_id, status, pending_action,
                retry_count, source_created_at, queued_at
            ) VALUES($1,$2,'queued','publish',0,$3,$3)
            ON CONFLICT (discord_message_id) DO NOTHING
            RETURNING discord_message_id
            """,
            message_id,
            channel_id,
            created_at,
        )
        if row:
            await self.add_stat("received", message_id, channel_id)
            return True
        return False

    async def enqueue_edit(self, message_id: int, channel_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE posts
               SET status='queued', pending_action='edit', retry_count=0,
                   next_retry_at=NULL,
                   queued_at=CASE WHEN status IN ('queued','processing','retrying') THEN queued_at ELSE now() END,
                   updated_at=now(), last_error=NULL
             WHERE discord_message_id=$1 AND discord_channel_id=$2
             RETURNING discord_message_id
            """,
            message_id,
            channel_id,
        )
        if row:
            await self.add_stat("edit_received", message_id, channel_id)
            return True
        return False

    async def enqueue_delete(self, message_id: int, channel_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE posts
               SET status='queued', pending_action='delete', retry_count=0,
                   next_retry_at=NULL,
                   queued_at=CASE WHEN status IN ('queued','processing','retrying') THEN queued_at ELSE now() END,
                   updated_at=now(), last_error=NULL
             WHERE discord_message_id=$1 AND discord_channel_id=$2
             RETURNING discord_message_id
            """,
            message_id,
            channel_id,
        )
        return bool(row)

    async def enqueue_retry(self, message_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE posts
               SET status='queued', pending_action=CASE WHEN telegram_message_id IS NULL THEN 'publish' ELSE 'edit' END,
                   retry_count=0, next_retry_at=NULL, queued_at=now(), updated_at=now(), last_error=NULL
             WHERE discord_message_id=$1 AND status='failed'
             RETURNING discord_message_id
            """,
            message_id,
        )
        return bool(row)

    async def enqueue_republish(self, message_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE posts
               SET status='queued', pending_action='republish', retry_count=0,
                   telegram_message_id=CASE WHEN status='deleted' THEN NULL ELSE telegram_message_id END,
                   next_retry_at=NULL, queued_at=now(), updated_at=now(), last_error=NULL
             WHERE discord_message_id=$1
             RETURNING discord_message_id
            """,
            message_id,
        )
        return bool(row)

    async def enqueue_manual_delete(self, message_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE posts
               SET status='queued', pending_action='delete', retry_count=0,
                   next_retry_at=NULL, queued_at=now(), updated_at=now(), last_error=NULL
             WHERE discord_message_id=$1
             RETURNING discord_message_id
            """,
            message_id,
        )
        return bool(row)

    async def get_post(self, message_id: int) -> PostRecord | None:
        return _record(await self.pool.fetchrow("SELECT * FROM posts WHERE discord_message_id=$1", message_id))

    async def get_oldest_pending(self) -> PostRecord | None:
        return _record(
            await self.pool.fetchrow(
                """
                SELECT * FROM posts
                 WHERE status = ANY($1::text[])
                 ORDER BY queued_at ASC, discord_message_id ASC
                 LIMIT 1
                """,
                list(PENDING_STATUSES),
            )
        )

    async def mark_processing(self, message_id: int) -> None:
        await self.pool.execute(
            "UPDATE posts SET status='processing', updated_at=now() WHERE discord_message_id=$1",
            message_id,
        )

    async def mark_published(self, message_id: int, telegram_message_id: int) -> None:
        await self.pool.execute(
            """
            UPDATE posts SET status='published', pending_action='publish', telegram_message_id=$2,
                retry_count=0, next_retry_at=NULL, published_at=COALESCE(published_at, now()),
                updated_at=now(), last_error=NULL
            WHERE discord_message_id=$1
            """,
            message_id,
            telegram_message_id,
        )

    async def mark_deleted(self, message_id: int) -> None:
        await self.pool.execute(
            """
            UPDATE posts SET status='deleted', pending_action='delete', next_retry_at=NULL,
                updated_at=now(), last_error=NULL
            WHERE discord_message_id=$1
            """,
            message_id,
        )

    async def mark_retry(self, message_id: int, retry_count: int, delay_seconds: int, error: str) -> None:
        await self.pool.execute(
            """
            UPDATE posts SET status='retrying', retry_count=$2,
                next_retry_at=now() + ($3 * interval '1 second'), updated_at=now(), last_error=$4
            WHERE discord_message_id=$1
            """,
            message_id,
            retry_count,
            delay_seconds,
            error[:2000],
        )

    async def mark_failed(self, message_id: int, retry_count: int, error: str) -> None:
        await self.pool.execute(
            """
            UPDATE posts SET status='failed', retry_count=$2, next_retry_at=NULL,
                updated_at=now(), last_error=$3
            WHERE discord_message_id=$1
            """,
            message_id,
            retry_count,
            error[:2000],
        )

    async def recover_processing(self) -> int:
        result = await self.pool.execute(
            "UPDATE posts SET status='queued', updated_at=now() WHERE status='processing'"
        )
        return int(result.split()[-1])

    async def queue_counts(self) -> dict[str, int]:
        rows = await self.pool.fetch(
            "SELECT status, count(*)::int AS count FROM posts GROUP BY status"
        )
        return {r["status"]: r["count"] for r in rows}

    async def failed(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
            SELECT discord_message_id, discord_channel_id, retry_count, last_error, updated_at
              FROM posts WHERE status='failed' ORDER BY updated_at DESC LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def add_stat(self, event_type: str, message_id: int | None = None, channel_id: int | None = None) -> None:
        await self.pool.execute(
            "INSERT INTO stats_events(event_type, discord_message_id, discord_channel_id) VALUES($1,$2,$3)",
            event_type,
            message_id,
            channel_id,
        )

    async def stats_24h(self) -> dict[str, int]:
        rows = await self.pool.fetch(
            """
            SELECT event_type, count(*)::int AS count
              FROM stats_events
             WHERE created_at >= now() - interval '24 hours'
             GROUP BY event_type
            """
        )
        return {r["event_type"]: r["count"] for r in rows}

    async def cleanup_temporary(self, retention_hours: int) -> int:
        result = await self.pool.execute(
            "DELETE FROM stats_events WHERE created_at < now() - ($1 * interval '1 hour')",
            retention_hours,
        )
        return int(result.split()[-1])

    async def clear_database(self) -> dict[str, int]:
        """Clear all LapBase data while preserving the database schema."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                posts_result = await conn.execute("DELETE FROM posts")
                stats_result = await conn.execute("DELETE FROM stats_events")
                confirmations_result = await conn.execute("DELETE FROM admin_confirmations")
                state_result = await conn.execute("DELETE FROM system_state")

        return {
            "posts": int(posts_result.split()[-1]),
            "stats_events": int(stats_result.split()[-1]),
            "admin_confirmations": int(confirmations_result.split()[-1]),
            "system_state": int(state_result.split()[-1]),
        }

    async def get_mode(self) -> str:
        value = await self.pool.fetchval("SELECT value FROM system_state WHERE key='mode'")
        return value or "running"

    async def set_mode(self, mode: str) -> None:
        await self.pool.execute(
            """
            INSERT INTO system_state(key,value) VALUES('mode',$1)
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
            """,
            mode,
        )

    async def last_success(self) -> dict[str, Any] | None:
        row = await self.pool.fetchrow(
            """
            SELECT discord_message_id, discord_channel_id, telegram_message_id, published_at
              FROM posts WHERE status='published' AND published_at IS NOT NULL
             ORDER BY published_at DESC LIMIT 1
            """
        )
        return dict(row) if row else None

    async def set_confirmation(self, admin_id: int, action: str, payload: dict[str, Any]) -> None:
        await self.pool.execute(
            """
            INSERT INTO admin_confirmations(admin_user_id, action, payload)
            VALUES($1,$2,$3::jsonb)
            ON CONFLICT(admin_user_id) DO UPDATE
              SET action=EXCLUDED.action, payload=EXCLUDED.payload, created_at=now()
            """,
            admin_id,
            action,
            json.dumps(payload),
        )

    async def get_confirmation(self, admin_id: int) -> dict[str, Any] | None:
        row = await self.pool.fetchrow(
            "SELECT action, payload, created_at FROM admin_confirmations WHERE admin_user_id=$1",
            admin_id,
        )
        if not row:
            return None
        data = dict(row)
        if isinstance(data.get("payload"), str):
            data["payload"] = json.loads(data["payload"])
        return data

    async def clear_confirmation(self, admin_id: int) -> None:
        await self.pool.execute("DELETE FROM admin_confirmations WHERE admin_user_id=$1", admin_id)
