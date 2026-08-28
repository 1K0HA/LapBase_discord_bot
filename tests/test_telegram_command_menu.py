from __future__ import annotations

from pathlib import Path


EXPECTED_COMMANDS = [
    "start",
    "stop",
    "restart",
    "pause",
    "resume",
    "status",
    "health",
    "stats",
    "queue",
    "failed",
    "retry",
    "delete",
    "republish",
    "sync",
    "logs",
    "backup",
    "cleardb",
    "post",
    "cancel",
    "help",
]


def test_admin_command_specs_contain_all_supported_commands():
    source = (
        Path(__file__).resolve().parents[1] / "app/telegram/admin.py"
    ).read_text(encoding="utf-8")

    for command in EXPECTED_COMMANDS:
        assert f'("{command}",' in source

    specs_block = source.split("ADMIN_COMMAND_SPECS", 1)[1].split(
        "ADMIN_HELP", 1
    )[0]
    assert specs_block.count('("') == len(EXPECTED_COMMANDS)


def test_help_and_telegram_menu_share_one_command_source():
    source = (
        Path(__file__).resolve().parents[1] / "app/telegram/admin.py"
    ).read_text(encoding="utf-8")

    assert "for command, usage, description in ADMIN_COMMAND_SPECS" in source
    assert "for command, _usage, description in ADMIN_COMMAND_SPECS" in source


def test_admin_menu_uses_admin_chat_id_but_auth_remains_user_id():
    root = Path(__file__).resolve().parents[1]
    admin = (root / "app/telegram/admin.py").read_text(encoding="utf-8")
    assert "BotCommandScopeChat(chat_id=config.telegram_admin_chat_id)" in admin
    assert "MainAdminFilter(config.telegram_admin_user_id)" in admin
    assert "admin.message.filter(MainAdminFilter(config.telegram_admin_user_id))" in admin



def test_menu_does_not_advertise_nonexistent_commands():
    import re

    root = Path(__file__).resolve().parents[1]
    admin = (root / "app/telegram/admin.py").read_text(encoding="utf-8")
    wizard = (root / "app/telegram/post_wizard.py").read_text(encoding="utf-8")

    implemented = set(re.findall(r'Command\("([a-z0-9_]+)"\)', admin + wizard))
    implemented.add("start")  # /start реализован через CommandStart.

    assert set(EXPECTED_COMMANDS) == implemented
