from __future__ import annotations

import argparse
import asyncio
import gzip
import json
from datetime import datetime
from pathlib import Path

from app.config import load_config
from app.storage.database import Database


def dt(value):
    return datetime.fromisoformat(value) if value else None


async def restore(path: Path) -> None:
    config = load_config()
    db = Database(config)
    await db.connect()
    await db.migrate()
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("format") != "lapbase-backup-v1":
            raise RuntimeError("Unsupported backup format")

        tables = data["tables"]
        async with db.require_pool().acquire() as conn:
            async with conn.transaction():
                for row in tables.get("posts", []):
                    await conn.execute(
                        """
                        INSERT INTO posts(
                            discord_message_id, discord_channel_id, telegram_message_id, status,
                            pending_action, retry_count, next_retry_at, source_created_at, queued_at,
                            published_at, updated_at, last_error
                        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                        ON CONFLICT(discord_message_id) DO UPDATE SET
                            discord_channel_id=EXCLUDED.discord_channel_id,
                            telegram_message_id=EXCLUDED.telegram_message_id,
                            status=EXCLUDED.status,
                            pending_action=EXCLUDED.pending_action,
                            retry_count=EXCLUDED.retry_count,
                            next_retry_at=EXCLUDED.next_retry_at,
                            source_created_at=EXCLUDED.source_created_at,
                            queued_at=EXCLUDED.queued_at,
                            published_at=EXCLUDED.published_at,
                            updated_at=EXCLUDED.updated_at,
                            last_error=EXCLUDED.last_error
                        """,
                        int(row["discord_message_id"]), int(row["discord_channel_id"]),
                        row.get("telegram_message_id"), row["status"], row["pending_action"],
                        int(row["retry_count"]), dt(row.get("next_retry_at")),
                        dt(row["source_created_at"]), dt(row["queued_at"]),
                        dt(row.get("published_at")), dt(row["updated_at"]), row.get("last_error"),
                    )

                for row in tables.get("system_state", []):
                    await conn.execute(
                        """
                        INSERT INTO system_state(key,value,updated_at) VALUES($1,$2,$3)
                        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                        """,
                        row["key"], row["value"], dt(row["updated_at"]),
                    )

                for row in tables.get("admin_confirmations", []):
                    payload = row.get("payload")
                    if not isinstance(payload, str):
                        payload = json.dumps(payload, ensure_ascii=False)
                    await conn.execute(
                        """
                        INSERT INTO admin_confirmations(admin_user_id, action, payload, created_at)
                        VALUES($1,$2,$3::jsonb,$4)
                        ON CONFLICT(admin_user_id) DO UPDATE SET
                            action=EXCLUDED.action, payload=EXCLUDED.payload, created_at=EXCLUDED.created_at
                        """,
                        int(row["admin_user_id"]), row["action"], payload, dt(row["created_at"]),
                    )
        print(f"Restored: {path}")
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore LapBase portable backup")
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    asyncio.run(restore(args.backup))
