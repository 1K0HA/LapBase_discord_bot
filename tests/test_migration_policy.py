import pytest

from app.storage.migration_policy import validate_migration_history


def test_migration_history_accepts_linear_prefix():
    validate_migration_history(["001.sql", "002.sql", "003.sql"], ["001.sql", "002.sql"])


def test_migration_history_rejects_unknown_version():
    with pytest.raises(RuntimeError):
        validate_migration_history(["001.sql"], ["999.sql"])


def test_migration_history_rejects_gap():
    with pytest.raises(RuntimeError):
        validate_migration_history(["001.sql", "002.sql", "003.sql"], ["001.sql", "003.sql"])
