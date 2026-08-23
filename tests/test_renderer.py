from pathlib import Path

from app.config import Config
from app.models import ProcessedPost
from app.processor.renderer import (
    TELEGRAM_MESSAGE_MAX_CHARS,
    build_message_html,
    text_budget,
)


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


def test_send_message_layout_and_line_breaks():
    result = build_message_html(
        ProcessedPost("Строка 1\n\nСтрока 2", "🎉event-news", []),
        config(),
    )
    assert result.startswith("<b>Источник официальный DISCORD: #🎉event-news</b>\n\n")
    assert "Строка 1\n\nСтрока 2" in result
    assert result.endswith("#autopost@lapbase")


def test_discord_markdown_is_converted_to_telegram_html():
    result = build_message_html(
        ProcessedPost("**Жирный**\n`код`\n||спойлер||", "updates", []),
        config(),
    )
    assert "<b>Жирный</b>" in result
    assert "<code>код</code>" in result
    assert "<tg-spoiler>спойлер</tg-spoiler>" in result


def test_html_characters_are_escaped():
    result = build_message_html(
        ProcessedPost("5 < 10 & 10 > 5", "updates", []),
        config(),
    )
    assert "5 &lt; 10 &amp; 10 &gt; 5" in result


def test_images_are_kept_as_urls_with_send_message():
    result = build_message_html(
        ProcessedPost("Текст", "updates", ["https://x/a.jpg", "https://x/b.jpg"]),
        config(),
    )
    assert "https://x/a.jpg" in result
    assert "https://x/b.jpg" in result
    assert "<tg-collage>" not in result
    assert result.endswith("#autopost@lapbase")


def test_send_message_budget_uses_4096_limit():
    budget = text_budget("updates", [], config())
    assert 500 <= budget < TELEGRAM_MESSAGE_MAX_CHARS
