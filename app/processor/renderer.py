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
    """Преобразует сохраняемое подмножество Discord Markdown в безопасный Telegram HTML.

    Неизвестная разметка остаётся видимым текстом, чтобы не создавать некорректные
    Telegram entities. Переносы строк не изменяются.
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

    # Используем только консервативное подмножество Discord/Markdown, поддерживаемое Telegram HTML.
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<u>\1</u>", escaped)
    escaped = re.sub(r"~~(.+?)~~", r"<s>\1</s>", escaped)
    escaped = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", escaped)

    # Простые маркеры курсива не должны пересекать границы строк.
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", escaped)

    # Строки цитат сохраняем как Telegram blockquote.
    lines = escaped.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("&gt; "):
            lines[i] = f"<blockquote>{line[5:]}</blockquote>"
    escaped = "\n".join(lines)

    for token, value in placeholders.items():
        escaped = escaped.replace(token, value)

    return escaped


def build_message_html(post: ProcessedPost, config: Config) -> str:
    pieces: list[str] = []

    if config.show_source_channel and (post.markdown.strip() or post.image_urls):
        source = html.escape(f"Источник официальный DISCORD: #{post.channel_name}")
        pieces.append(f"<b>{source}</b>")

    if post.markdown.strip():
        pieces.append(_markdown_to_telegram_html(post.markdown.strip()))

    # send_message не прикрепляет media. По согласованному поведению URL вложений
    # в текст автопоста не добавляются.
    pieces.append(AUTOPOST_TAG)
    return "\n\n".join(pieces).strip()


def build_markdown(post: ProcessedPost, config: Config) -> str:
    """Совместимый alias: результат всегда Telegram HTML, а не Markdown."""
    return build_message_html(post, config)


def text_budget(channel_name: str, image_urls: list[str], config: Config) -> int:
    # Telegram sendMessage допускает 4096 отображаемых символов после разбора entities.
    overhead = len(AUTOPOST_TAG) + 4
    if config.show_source_channel:
        overhead += len("Источник официальный DISCORD: #") + len(channel_name) + 2
    # URL изображений больше не включаются в send_message и не расходуют text budget.

    # Оставляем небольшой резерв для разделителей и форматирования.
    return max(500, TELEGRAM_MESSAGE_MAX_CHARS - overhead - 64)
