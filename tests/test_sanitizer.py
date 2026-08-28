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
    assert "https://example.com" not in value


def test_protection_restores_code_and_mentions():
    protected = protect_nontranslatable("Read `npm i` and ping @Alice")
    restored = protected.restore(protected.text)
    assert "`npm i`" in restored
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



def test_all_plain_urls_are_removed_but_markdown_label_is_kept():
    value = sanitize(
        source(
            "Site: https://example.com/page?q=1\n"
            "Docs: [официальная документация](https://example.com/docs)\n"
            "[https://cdn.discordapp.com/a.jpg](https://cdn.discordapp.com/a.jpg)"
        )
    )
    assert "https://" not in value
    assert "официальная документация" in value
    assert "cdn.discordapp.com" not in value


def test_urls_inside_code_are_preserved():
    value = sanitize(
        source(
            "Outside https://example.com\n"
            "`curl https://api.example.com/v1`\n"
            "```text\nhttps://inside.example.com\n```"
        )
    )
    assert "Outside https://example.com" not in value
    assert "`curl https://api.example.com/v1`" in value
    assert "https://inside.example.com" in value


def test_feedback_calls_and_audience_questions_are_removed_before_translation():
    value = sanitize(
        source(
            "[Supreme Duel] Event Preview 2\n\n"
            "Rewards are available for every participant.\n\n"
            "Who do you think will become the first Supreme Duel champion? "
            "And what's your championship slogan?\n\n"
            "Doctors, let us know in <#1493675820601053205>!\n\n"
            "[https://cdn.discordapp.com/attachments/a/L1-EN.jpg]"
            "(https://cdn.discordapp.com/attachments/a/L1-EN.jpg)"
        )
    )
    assert value == (
        "[Supreme Duel] Event Preview 2\n\n"
        "Rewards are available for every participant."
    )


def test_russian_feedback_and_opinion_questions_are_removed():
    value = sanitize(
        source(
            "Полезная строка.\n\n"
            "Кто, по вашему мнению, станет первым чемпионом?\n"
            "И какой у вас слоган чемпионата?\n"
            "Доктора, дайте нам знать в комментариях!"
        )
    )
    assert value == "Полезная строка."


def test_informational_question_is_not_removed():
    value = sanitize(
        source(
            "How does the Rematch phase work?\n"
            "The prediction round opens during Rematch."
        )
    )
    assert value.startswith("How does the Rematch phase work?")
