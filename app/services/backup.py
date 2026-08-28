from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import Config

if TYPE_CHECKING:
    from app.storage.database import Database

logger = logging.getLogger(__name__)
BACKUP_FORMAT = "lapbase-backup-v1"
REQUIRED_TABLES = {
    "posts",
    "stats_events",
    "system_state",
    "admin_confirmations",
    "schema_migrations",
}


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Неподдерживаемое значение backup: {type(value).__name__}")


class BackupService:
    """Создаёт проверяемую логическую копию всех persistent-таблиц LapBase."""

    def __init__(self, config: Config, db: "Database") -> None:
        self.config = config
        self.db = db
        self.config.backups_dir.mkdir(parents=True, exist_ok=True)

    async def create_backup(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        output = self.config.backups_dir / f"lapbase_{timestamp}.json.gz"
        temporary = output.with_suffix(output.suffix + ".tmp")

        async with self.db.require_pool().acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                posts = [dict(r) for r in await conn.fetch("SELECT * FROM posts ORDER BY discord_message_id")]
                stats_events = [dict(r) for r in await conn.fetch("SELECT * FROM stats_events ORDER BY id")]
                system_state = [dict(r) for r in await conn.fetch("SELECT * FROM system_state ORDER BY key")]
                confirmations = [
                    dict(r)
                    for r in await conn.fetch(
                        "SELECT admin_user_id, action, payload, created_at "
                        "FROM admin_confirmations ORDER BY admin_user_id"
                    )
                ]
                migrations = [
                    dict(r)
                    for r in await conn.fetch(
                        "SELECT version, applied_at FROM schema_migrations ORDER BY version"
                    )
                ]

        payload = {
            "format": BACKUP_FORMAT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tables": {
                "posts": posts,
                "stats_events": stats_events,
                "system_state": system_state,
                "admin_confirmations": confirmations,
                "schema_migrations": migrations,
            },
        }

        def write_and_replace() -> None:
            try:
                with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                    json.dump(
                        payload,
                        handle,
                        ensure_ascii=False,
                        default=_json_default,
                        separators=(",", ":"),
                    )
                self.verify_backup(temporary)
                os.replace(temporary, output)
                self.verify_backup(output)
            finally:
                temporary.unlink(missing_ok=True)

        await asyncio.to_thread(write_and_replace)
        self.prune()
        logger.info("Создан и проверен backup LapBase: %s", output.name)
        return output

    @staticmethod
    def verify_backup(path: Path) -> None:
        """Проверяет gzip/JSON, формат и наличие всех обязательных таблиц."""
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("format") != BACKUP_FORMAT:
            raise RuntimeError(f"Неподдерживаемый формат backup: {payload.get('format')!r}")
        tables = payload.get("tables")
        if not isinstance(tables, dict):
            raise RuntimeError("Backup не содержит корректный объект tables")
        missing = REQUIRED_TABLES - set(tables)
        if missing:
            raise RuntimeError("Backup не содержит таблицы: " + ", ".join(sorted(missing)))
        for name in REQUIRED_TABLES:
            if not isinstance(tables[name], list):
                raise RuntimeError(f"Backup table {name} имеет неверный тип")

    def prune(self) -> None:
        """Удаляет только старые LapBase backup-файлы внутри project-owned каталога."""
        root = self.config.backups_dir.resolve()
        backups = sorted(
            root.glob("lapbase_*.json.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in backups[self.config.backup_keep_count :]:
            resolved = path.resolve()
            if resolved.parent != root:
                raise RuntimeError(f"Отказ от удаления backup вне ожидаемого каталога: {resolved}")
            resolved.unlink(missing_ok=True)
