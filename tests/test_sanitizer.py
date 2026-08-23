from datetime import datetime, timezone

from app.models import SourceMessage
from app.processor.sanitizer import protect_nontranslatable, sanitize


def source(text: str) -> SourceMessage:
    return SourceMessage(
        discord_message_id=1,
        discord_channel_id=2,
        channel_name="updates",
        content=text,
        created_at=datetime.now(timezone.utc),
        user_mentions={42: "Alice"},
        role_mentions={77: "News"},
    )


def test_discord_cleanup_and_mentions():
    value = sanitize(
        source("Hi <@42> <@&77> @everyone @here <:x:123> https://discord.gg/test https://example.com")
    )
    assert "@Alice" in value
    assert "@News" in value
    assert "@everyone" not in value
    assert "discord.gg" not in value
    assert "https://example.com" in value


def test_protection_restores_code_and_urls():
    protected = protect_nontranslatable("Read `npm i` at https://example.com and ping @Alice")
    restored = protected.restore(protected.text)
    assert "`npm i`" in restored
    assert '"https://example.com"' in restored
    assert "@Alice" in restored

def test_leading_discord_channel_context_is_removed():
    value = sanitize(
        source(
            "Last Asylum: Plague <#1493675820601053205>:\n"
            "[Supreme Duel] Event Preview 1\n"
            "Body"
        )
    )
    assert value == "[Supreme Duel] Event Preview 1\nBody"


def test_channel_context_line_is_removed_anywhere_in_message():
    value = sanitize(
        source(
            "Title\n"
            "Last Asylum: Plague <#1493675820601053205>:\n"
            "Body"
        )
    )
    assert value == "Title\nBody"


def test_raw_channel_mention_is_removed_everywhere_without_deleting_text():
    value = sanitize(
        source("See channel <#1493675820601053205> for details")
    )
    assert "<#1493675820601053205>" not in value
    assert "See channel" in value
    assert "for details" in value


def test_line_breaks_are_protected_and_restored():
    original = "Title\nLine 2\n\nParagraph 2"
    protected = protect_nontranslatable(original)
    assert "\n" not in protected.text
    assert protected.restore(protected.text) == original



def test_multiple_discord_channel_artifacts_are_removed():
    value = sanitize(
        source(
            "Game A <#111111111111111111>:\n"
            "First paragraph\n\n"
            "Game B <#222222222222222222>:\n"
            "Second paragraph with <#333333333333333333> reference"
        )
    )
    assert "<#" not in value
    assert "Game A" not in value
    assert "Game B" not in value
    assert "First paragraph" in value
    assert "Second paragraph with" in value



def test_sanitize_preserves_multiple_blank_lines():
    value = sanitize(source("A\r\nB\r\n\r\n\r\nC"))
    assert value == "A\nB\n\n\nC"
