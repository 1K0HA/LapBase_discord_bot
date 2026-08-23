from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_publisher_uses_send_message_not_rich_message():
    source = (ROOT / "app/telegram/publisher.py").read_text(encoding="utf-8")
    assert "send_message(" in source
    assert "send_rich_message(" not in source
    assert "InputRichMessage" not in source
    assert "ParseMode.HTML" in source


def test_edit_uses_text_parameter():
    source = (ROOT / "app/telegram/publisher.py").read_text(encoding="utf-8")
    assert "edit_message_text(" in source
    assert "text=html_text" in source
    assert "rich_message=" not in source
