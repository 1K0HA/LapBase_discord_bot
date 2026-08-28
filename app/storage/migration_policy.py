from __future__ import annotations


def validate_migration_history(local_versions: list[str], applied_versions: list[str]) -> None:
    """Проверяет, что БД содержит только линейный префикс локальной истории миграций."""
    unknown = [version for version in applied_versions if version not in local_versions]
    if unknown:
        raise RuntimeError(
            "БД содержит миграции, отсутствующие в этой версии проекта: " + ", ".join(unknown)
        )

    expected_prefix = local_versions[: len(applied_versions)]
    if applied_versions != expected_prefix:
        raise RuntimeError(
            "История миграций БД не является ожидаемым префиксом локальной истории. "
            "Автоматическое исправление запрещено."
        )
