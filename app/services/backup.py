from __future__ import annotations

import asyncio
import gzip
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Config
from app.storage.database import Database

logger = logging.getLogger(__name__)


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Unsupported backup value: {type(value).__name__}")


class BackupService:
    """Portable logical backup of LapBase-owned persistent tables.

    Original/translated post text and images are not stored by LapBase, so they cannot leak into this backup.
    """

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db
        self.config.backups_dir.mkdir(parents=True, exist_ok=True)

    async def create_backup(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output = self.config.backups_dir / f"lapbase_{timestamp}.json.gz"

        async with self.db.require_pool().acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                posts = [dict(r) for r in await conn.fetch("SELECT * FROM posts ORDER BY discord_message_id")]
                system_state = [dict(r) for r in await conn.fetch("SELECT * FROM system_state ORDER BY key")]
                confirmations = [
                    dict(r)
                    for r in await conn.fetch(
                        "SELECT admin_user_id, action, payload, created_at FROM admin_confirmations ORDER BY admin_user_id"
                    )
                ]
                migrations = [
                    dict(r)
                    for r in await conn.fetch(
                        "SELECT version, applied_at FROM schema_migrations ORDER BY version"
                    )
                ]

        payload = {
            "format": "lapbase-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tables": {
                "posts": posts,
                "system_state": system_state,
                "admin_confirmations": confirmations,
                "schema_migrations": migrations,
            },
        }

        def write() -> None:
            with gzip.open(output, "wt", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, default=_json_default, separators=(",", ":"))

        await asyncio.to_thread(write)
        self.prune()
        logger.info("Created portable LapBase backup %s", output.name)
        return output

    def prune(self) -> None:
        backups = sorted(
            self.config.backups_dir.glob("lapbase_*.json.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in backups[self.config.backup_keep_count :]:
            path.unlink(missing_ok=True)
