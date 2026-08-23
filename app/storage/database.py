from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

from app.config import Config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        ssl = "require" if self.config.db_ssl else None
        self.pool = await asyncpg.create_pool(
            dsn=self.config.supabase_db_url,
            min_size=self.config.db_pool_min_size,
            max_size=self.config.db_pool_max_size,
            ssl=ssl,
            # Safe with Supavisor modes and fine for direct connections.
            statement_cache_size=0,
            command_timeout=60,
        )
        logger.info("Connected to Supabase PostgreSQL")

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Database is not connected")
        return self.pool

    async def health(self) -> bool:
        try:
            value = await self.require_pool().fetchval("SELECT 1")
            return value == 1
        except Exception:
            return False

    async def migrate(self) -> None:
        pool = self.require_pool()
        migrations_dir = self.config.root_dir / "migrations"
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
            for path in sorted(migrations_dir.glob("*.sql")):
                if path.name in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                logger.info("Applying migration %s", path.name)
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES($1)", path.name
                    )
