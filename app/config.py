from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

MAIN_ADMIN_ID = 335707167


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true/false")


def _channel_ids() -> frozenset[int]:
    raw = _required("DISCORD_CHANNEL_IDS")
    result: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError as exc:
            raise RuntimeError(f"Invalid Discord channel ID: {part!r}") from exc
    if not result:
        raise RuntimeError("DISCORD_CHANNEL_IDS contains no channel IDs")
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class Config:
    discord_bot_token: str
    discord_channel_ids: frozenset[int]
    telegram_bot_token: str
    telegram_channel_id: int
    telegram_admin_user_id: int
    telegram_admin_chat_id: int
    lapbase_app_url: str | None
    groq_api_key: str
    groq_model: str
    groq_reasoning_effort: str
    supabase_db_url: str
    supabase_backup_db_url: str
    db_pool_min_size: int
    db_pool_max_size: int
    db_ssl: bool
    sync_hours: int
    retry_delay_seconds: int
    max_retries: int
    log_retention_days: int
    backup_interval_hours: int
    backup_keep_count: int
    cleanup_interval_hours: int
    temp_data_retention_hours: int
    show_source_channel: bool
    root_dir: Path = ROOT_DIR

    @property
    def logs_dir(self) -> Path:
        return self.root_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.root_dir / "backups"


def load_config() -> Config:
    admin_id = _int("TELEGRAM_ADMIN_USER_ID", MAIN_ADMIN_ID)
    if admin_id <= 0:
        raise RuntimeError("TELEGRAM_ADMIN_USER_ID must be positive")

    tg_channel = _int("TELEGRAM_CHANNEL_ID", 0)
    if tg_channel == 0:
        raise RuntimeError("TELEGRAM_CHANNEL_ID is required")

    db_url = _required("SUPABASE_DB_URL")
    return Config(
        discord_bot_token=_required("DISCORD_BOT_TOKEN"),
        discord_channel_ids=_channel_ids(),
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_channel_id=tg_channel,
        telegram_admin_user_id=admin_id,
        telegram_admin_chat_id=_int("TELEGRAM_ADMIN_CHAT_ID", admin_id),
        lapbase_app_url=os.getenv("LAPBASE_APP_URL", "").strip() or None,
        groq_api_key=_required("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
        groq_reasoning_effort=os.getenv("GROQ_REASONING_EFFORT", "low").strip(),
        supabase_db_url=db_url,
        supabase_backup_db_url=os.getenv("SUPABASE_BACKUP_DB_URL", "").strip() or db_url,
        db_pool_min_size=_int("DB_POOL_MIN_SIZE", 1),
        db_pool_max_size=_int("DB_POOL_MAX_SIZE", 5),
        db_ssl=_bool("DB_SSL", True),
        sync_hours=_int("SYNC_HOURS", 24),
        retry_delay_seconds=_int("RETRY_DELAY_SECONDS", 300),
        max_retries=_int("MAX_RETRIES", 5),
        log_retention_days=_int("LOG_RETENTION_DAYS", 3),
        backup_interval_hours=_int("BACKUP_INTERVAL_HOURS", 24),
        backup_keep_count=_int("BACKUP_KEEP_COUNT", 3),
        cleanup_interval_hours=_int("CLEANUP_INTERVAL_HOURS", 48),
        temp_data_retention_hours=_int("TEMP_DATA_RETENTION_HOURS", 48),
        show_source_channel=_bool("SHOW_SOURCE_CHANNEL", True),
    )
