from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

from app.config import Config
from app.storage.migration_policy import validate_migration_history

logger = logging.getLogger(__name__)


class Database:
    """Управляет пулом Supabase PostgreSQL и версионированными миграциями."""

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
            # Supavisor может работать без prepared statement cache; direct connection тоже поддерживается.
            statement_cache_size=0,
            command_timeout=self.config.db_command_timeout_seconds,
        )
        logger.info("Подключение к Supabase PostgreSQL установлено")

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Соединение с БД ещё не установлено")
        return self.pool

    async def health(self) -> bool:
        try:
            value = await self.require_pool().fetchval("SELECT 1")
            return value == 1
        except Exception:
            logger.debug("Health-check БД завершился ошибкой", exc_info=True)
            return False

    async def verify_table_columns(
        self,
        table_name: str,
        required_columns: tuple[str, ...],
    ) -> None:
        """Проверяет обязательный контракт схемы до запуска рабочих компонентов."""
        rows = await self.require_pool().fetch(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = $1
            """,
            table_name,
        )
        actual = {str(row["column_name"]) for row in rows}
        required = set(required_columns)
        missing = sorted(required - actual)
        if missing:
            raise RuntimeError(
                f"Схема БД несовместима: таблица {table_name} не содержит "
                f"обязательные поля: {', '.join(missing)}"
            )

        extra = sorted(actual - required)
        if extra:
            logger.info(
                "Schema contract %s: обязательные поля присутствуют; extra columns разрешены: %s",
                table_name,
                ", ".join(extra),
            )
        else:
            logger.info("Schema contract %s: OK", table_name)

    @staticmethod
    def _migration_files(migrations_dir: Path) -> list[Path]:
        files = sorted(migrations_dir.glob("*.sql"))
        if not files:
            raise RuntimeError("Не найдено ни одной SQL-миграции")
        names = [path.name for path in files]
        if len(names) != len(set(names)):
            raise RuntimeError("Обнаружены дублирующиеся имена миграций")
        return files

    async def migrate(self) -> None:
        """Применяет только линейное продолжение известной локальной истории миграций."""
        pool = self.require_pool()
        migrations_dir = self.config.root_dir / "migrations"
        files = self._migration_files(migrations_dir)
        local_versions = [path.name for path in files]

        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            applied_rows = await conn.fetch(
                "SELECT version FROM schema_migrations ORDER BY applied_at, version"
            )
            applied_versions = [str(row["version"]) for row in applied_rows]

            validate_migration_history(local_versions, applied_versions)

            for path in files[len(applied_versions) :]:
                sql = path.read_text(encoding="utf-8")
                logger.info("Применение миграции %s", path.name)
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES($1)", path.name
                    )
