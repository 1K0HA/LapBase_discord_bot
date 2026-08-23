from __future__ import annotations

import html
import re

from app.config import Config
from app.models import ProcessedPost

TELEGRAM_MESSAGE_MAX_CHARS = 4096
AUTOPOST_TAG = "#autopost@lapbase"

_CODE_BLOCK_RE = re.compile(r"```(?:[^\n`]*)\n?([\s\S]*?)```")
_INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")


def _markdown_to_telegram_html(text: str) -> str:
    """Convert the small Discord Markdown subset LapBase preserves into Telegram HTML.

    Unknown Markdown is left visible instead of risking an invalid Telegram entity.
    Line breaks are never changed.
    """
    placeholders: dict[str, str] = {}
    counter = 0

    def stash(value: str) -> str:
        nonlocal counter
        token = f"LBHTML{counter:04d}TOKEN"
        counter += 1
        placeholders[token] = value
        return token

    def code_block(match: re.Match[str]) -> str:
        return stash(f"<pre><code>{html.escape(match.group(1))}</code></pre>")

    def inline_code(match: re.Match[str]) -> str:
        return stash(f"<code>{html.escape(match.group(1))}</code>")

    protected = _CODE_BLOCK_RE.sub(code_block, text)
    protected = _INLINE_CODE_RE.sub(inline_code, protected)
    escaped = html.escape(protected)

    # Conservative Discord/Markdown formatting supported by Telegram HTML.
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<u>\1</u>", escaped)
    escaped = re.sub(r"~~(.+?)~~", r"<s>\1</s>", escaped)
    escaped = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", escaped)

    # Simple italic markers. Do not cross line boundaries.
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", escaped)

    # Preserve quote lines as Telegram blockquotes.
    lines = escaped.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("&gt; "):
            lines[i] = f"<blockquote>{line[5:]}</blockquote>"
    escaped = "\n".join(lines)

    for token, value in placeholders.items():
        escaped = escaped.replace(token, value)

    return escaped


def _image_links(image_urls: list[str]) -> str:
    if not image_urls:
        return ""
    return "\n".join(html.escape(url, quote=False) for url in image_urls[:50])


def build_message_html(post: ProcessedPost, config: Config) -> str:
    pieces: list[str] = []

    if config.show_source_channel and (post.markdown.strip() or post.image_urls):
        source = html.escape(f"Источник официальный DISCORD: #{post.channel_name}")
        pieces.append(f"<b>{source}</b>")

    if post.markdown.strip():
        pieces.append(_markdown_to_telegram_html(post.markdown.strip()))

    # send_message cannot attach Telegram media. Keep Discord image URLs in the
    # same Telegram message so no source attachment is silently lost.
    image_links = _image_links(post.image_urls)
    if image_links:
        pieces.append(image_links)

    pieces.append(AUTOPOST_TAG)
    return "\n\n".join(pieces).strip()


def build_markdown(post: ProcessedPost, config: Config) -> str:
    """Compatibility alias. Output is Telegram HTML, never Markdown."""
    return build_message_html(post, config)


def text_budget(channel_name: str, image_urls: list[str], config: Config) -> int:
    # Telegram sendMessage allows 4096 displayed characters after entity parsing.
    overhead = len(AUTOPOST_TAG) + 4
    if config.show_source_channel:
        overhead += len("Источник официальный DISCORD: #") + len(channel_name) + 2
    if image_urls:
        overhead += sum(len(url) + 1 for url in image_urls[:50]) + 2

    # Leave a small reserve for separators and formatting.
    return max(500, TELEGRAM_MESSAGE_MAX_CHARS - overhead - 64)
