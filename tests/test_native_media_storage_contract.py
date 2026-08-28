from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_additive_media_ids_migration_exists():
    sql = (ROOT / "migrations/004_telegram_media_messages.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS telegram_media_message_ids" in sql
    assert "BIGINT[]" in sql
    assert "NOT NULL" in sql
    assert "DEFAULT '{}'::BIGINT[]" in sql
    assert "DROP" not in sql.upper()


def test_repository_persists_text_and_media_mapping():
    source = (ROOT / "app/storage/repositories.py").read_text(encoding="utf-8")
    assert "telegram_media_message_ids=$3::BIGINT[]" in source
    assert "telegram_media_message_ids," in source
    assert "cardinality(telegram_media_message_ids)=0" in source


def test_restore_supports_new_and_old_backup_rows():
    source = (ROOT / "scripts/restore_backup.py").read_text(encoding="utf-8")
    assert "telegram_media_message_ids" in source
    assert 'row.get("telegram_media_message_ids", [])' in source


def test_worker_uses_bundle_for_publish_replace_and_delete():
    source = (ROOT / "app/queue/worker.py").read_text(encoding="utf-8")
    assert "publisher.publish(html_text, source.image_urls)" in source
    assert "publisher.replace(" in source
    assert "publisher.delete_publication(" in source
    assert "publication.text_message_id" in source
    assert "publication.media_message_ids" in source
