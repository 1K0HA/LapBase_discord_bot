from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_publisher_uses_send_message_with_link_preview_options():
    source = (ROOT / "app/telegram/publisher.py").read_text(encoding="utf-8")
    assert "send_message(" in source
    assert "LinkPreviewOptions" in source
    assert "link_preview_options=preview" in source
    assert "send_photo(" not in source
    assert "send_media_group(" not in source
    assert "InputMediaPhoto" not in source
    assert "ParseMode.HTML" in source


def test_edit_updates_same_text_message_and_preview():
    source = (ROOT / "app/telegram/publisher.py").read_text(encoding="utf-8")
    assert "edit_message_text(" in source
    assert "message_id=telegram_message_id" in source
    assert "link_preview_options=preview" in source
    assert "async def replace(" not in source


def test_only_first_image_is_selected_for_preview():
    source = (ROOT / "app/telegram/publisher.py").read_text(encoding="utf-8")
    assert "url=image_urls[0]" in source
    assert "prefer_large_media=True" in source
    assert "show_above_text=False" in source
