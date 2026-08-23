import sys
import types
from pathlib import Path

# aiogram is not required for the static publisher guard test in this build environment.
aiogram = types.ModuleType("aiogram")
aiogram.Bot = object
sys.modules.setdefault("aiogram", aiogram)

enums = types.ModuleType("aiogram.enums")
class _ParseMode:
    HTML = "HTML"
enums.ParseMode = _ParseMode
sys.modules.setdefault("aiogram.enums", enums)

from app.config import Config
from app.models import ProcessedPost
from app.processor.renderer import build_message_html
from app.telegram.publisher import TelegramPublisher


def config() -> Config:
    return Config(
        discord_bot_token="x",
        discord_channel_ids=frozenset({1}),
        telegram_bot_token="x",
        telegram_channel_id=-1001,
        telegram_admin_user_id=335707167,
        telegram_admin_chat_id=335707167,
        lapbase_app_url=None,
        groq_api_key="x",
        groq_model="openai/gpt-oss-120b",
        groq_reasoning_effort="low",
        supabase_db_url="postgresql://x",
        supabase_backup_db_url="postgresql://x",
        db_pool_min_size=1,
        db_pool_max_size=2,
        db_ssl=True,
        sync_hours=24,
        retry_delay_seconds=300,
        max_retries=5,
        log_retention_days=3,
        backup_interval_hours=24,
        backup_keep_count=3,
        cleanup_interval_hours=48,
        temp_data_retention_hours=48,
        show_source_channel=True,
        root_dir=Path("."),
    )


def test_exact_send_message_format_has_no_legacy_markdown_or_escapes():
    result = build_message_html(
        ProcessedPost("ыутв ьуыыфпу", "🔊official-post", []),
        config(),
    )
    assert result == (
        "<b>Источник официальный DISCORD: #🔊official-post</b>\n\n"
        "ыутв ьуыыфпу\n\n"
        "#autopost@lapbase"
    )
    assert "**Источник" not in result
    assert "\\#autopost" not in result
    assert '["' not in result


def test_publisher_rejects_mixed_legacy_renderer_output():
    bad = "**Источник официальный DISCORD: #x**\n\ntext\n\n\\#autopost\\@lapbase"
    try:
        TelegramPublisher._validate_html_text(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("legacy mixed deployment was not rejected")
