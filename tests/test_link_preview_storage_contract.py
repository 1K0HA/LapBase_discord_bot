from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_migration_004_is_kept_and_not_reversed():
    sql = (ROOT / "migrations/004_telegram_media_messages.sql").read_text(encoding="utf-8")
    assert "telegram_media_message_ids" in sql
    assert "DROP" not in sql.upper()


def test_repository_primary_mapping_is_single_text_message_id():
    source = (ROOT / "app/storage/repositories.py").read_text(encoding="utf-8")
    assert "async def mark_published(self, message_id: int, telegram_message_id: int)" in source
    assert "telegram_message_id=$2" in source
    assert "telegram_media_message_ids='{}'::BIGINT[]" in source
    assert "cardinality(telegram_media_message_ids)=0" not in source


def test_restore_remains_backward_compatible_with_v1026_backup():
    source = (ROOT / "scripts/restore_backup.py").read_text(encoding="utf-8")
    assert "telegram_media_message_ids" in source
    assert 'row.get("telegram_media_message_ids", [])' in source


def test_worker_uses_one_message_for_new_runtime_behavior():
    source = (ROOT / "app/queue/worker.py").read_text(encoding="utf-8")
    assert "publisher.publish(html_text, source.image_urls)" in source
    assert "publisher.edit(" in source
    assert "publication.text_message_id" not in source
    assert "publication.media_message_ids" not in source
    assert "mark_published(record.discord_message_id, tg_id)" in source


def test_legacy_media_field_is_only_transition_cleanup_not_new_mapping():
    worker = (ROOT / "app/queue/worker.py").read_text(encoding="utf-8")
    repository = (ROOT / "app/storage/repositories.py").read_text(encoding="utf-8")
    assert "delete_legacy_media" in worker
    assert "telegram_media_message_ids='{}'::BIGINT[]" in repository
