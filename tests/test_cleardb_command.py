from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cleardb_is_admin_command_and_requires_confirmation():
    source = (ROOT / "app/telegram/admin.py").read_text(encoding="utf-8")
    assert 'Command("cleardb")' in source
    assert '"cleardb",' in source
    assert 'elif action == "cleardb":' in source
    assert 'BotCommand(command="cleardb"' in source


def test_cleardb_removes_all_lapbase_data_tables():
    source = (ROOT / "app/storage/repositories.py").read_text(encoding="utf-8")
    method = source.split("async def clear_database", 1)[1].split("async def get_mode", 1)[0]
    assert "DELETE FROM posts" in method
    assert "DELETE FROM stats_events" in method
    assert "DELETE FROM admin_confirmations" in method
    assert "DELETE FROM system_state" in method
