from pathlib import Path

from app.config import Config
from app.models import ProcessedPost
from app.processor.renderer import build_markdown


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


def test_channel_name_and_collage():
    result = build_markdown(
        ProcessedPost("**Привет**", "updates", ["https://x/a.jpg", "https://x/b.jpg"]),
        config(),
    )
    assert "Источник" in result
    assert "#updates" in result
    assert "<tg-collage>" in result
    assert "a.jpg" in result and "b.jpg" in result



def test_source_is_heading_and_autopost_tag_is_last():
    result = build_markdown(
        ProcessedPost("Строка 1\n\nСтрока 2", "🎉event-news", []),
        config(),
    )
    assert result.startswith("# **Источник официальный DISCORD: #🎉event-news**\n\n")
    assert "Строка 1\n\nСтрока 2" in result
    assert result.endswith("#autopost@lapbase")


def test_autopost_tag_after_media():
    result = build_markdown(
        ProcessedPost("Текст", "updates", ["https://x/a.jpg"]),
        config(),
    )
    assert result.rfind("#autopost@lapbase") > result.rfind("a.jpg")
