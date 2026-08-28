from __future__ import annotations

import sys
import types

import pytest

# Локальная среда статических тестов может не содержать asyncpg; сеть/БД здесь не нужны.
asyncpg_stub = types.ModuleType("asyncpg")
asyncpg_stub.Pool = object
sys.modules.setdefault("asyncpg", asyncpg_stub)

from app.storage.database import Database
from app.storage.models import POST_RECORD_COLUMNS
from app.storage.repositories import _record


def _post_row() -> dict:
    return {
        "discord_message_id": 1,
        "discord_channel_id": 2,
        "telegram_message_id": 3,
        "telegram_media_message_ids": [],
        "status": "published",
        "pending_action": "publish",
        "retry_count": 0,
        "next_retry_at": None,
        "source_created_at": None,
        "queued_at": None,
        "published_at": None,
        "updated_at": None,
        "last_error": None,
    }


def test_future_additive_column_does_not_break_post_record():
    row = _post_row()
    row["future_additive_column"] = "allowed"

    record = _record(row)

    assert record is not None
    assert record.discord_message_id == 1
    assert not hasattr(record, "future_additive_column")


def test_repository_contract_does_not_use_select_star():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "app/storage/repositories.py"
    ).read_text(encoding="utf-8")
    assert "SELECT * FROM posts" not in source
    assert "POST_RECORD_SELECT" in source


class FakePool:
    def __init__(self, columns: list[str]) -> None:
        self.columns = columns

    async def fetch(self, _query, _table_name):
        return [{"column_name": name} for name in self.columns]


@pytest.mark.asyncio
async def test_schema_check_allows_extra_columns():
    db = object.__new__(Database)
    db.pool = FakePool([*POST_RECORD_COLUMNS, "future_additive_column"])

    await db.verify_table_columns("posts", POST_RECORD_COLUMNS)


@pytest.mark.asyncio
async def test_schema_check_fails_fast_on_missing_required_column():
    db = object.__new__(Database)
    db.pool = FakePool(
        [name for name in POST_RECORD_COLUMNS if name != "discord_message_id"]
    )

    with pytest.raises(RuntimeError, match="discord_message_id"):
        await db.verify_table_columns("posts", POST_RECORD_COLUMNS)
