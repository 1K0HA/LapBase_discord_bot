from __future__ import annotations

from pathlib import Path

import pytest

from app.instance_lock import InstanceAlreadyRunningError, InstanceLock


def test_second_instance_is_blocked_and_stale_file_is_harmless(tmp_path):
    path = tmp_path / "lapbase.lock"
    first = InstanceLock(path, "1.0.28")
    second = InstanceLock(path, "1.0.28")

    first.acquire()
    try:
        with pytest.raises(InstanceAlreadyRunningError):
            second.acquire()
        text = path.read_text(encoding="utf-8")
        assert "version=1.0.28" in text
        assert "pid=" in text
    finally:
        first.release()

    # Lock-файл остаётся как metadata, но после release новый процесс может получить lock.
    second.acquire()
    second.release()


def test_instance_lock_happens_before_db_connection_and_migrations():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/main.py").read_text(encoding="utf-8")

    lock_pos = source.index("instance_lock.acquire()")
    connect_pos = source.index("await db.connect()")
    migrate_pos = source.index("await db.migrate()")
    schema_pos = source.index('await db.verify_table_columns("posts", POST_RECORD_COLUMNS)')

    assert lock_pos < connect_pos < migrate_pos < schema_pos
