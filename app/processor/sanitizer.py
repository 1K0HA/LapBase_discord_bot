from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import SourceMessage

CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
INLINE_CODE_RE = re.compile(r"(?<!`)`[^`\n]+`(?!`)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\]\[()]+(?:[ \t]+)?", re.IGNORECASE)
PLAIN_MENTION_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.-]+")
CHANNEL_CONTEXT_LINE_RE = re.compile(
    r"(?m)^[^\r\n]{0,200}?<#\d+>\s*:\s*(?:\r?\n)?",
    re.UNICODE,
)
CHANNEL_MENTION_RE = re.compile(r"<#\d+>")

# Фильтр ограничен явными просьбами об обратной связи и вопросами к аудитории.
# Он не удаляет обычные информационные вопросы без обращения к читателю.
FEEDBACK_LINE_PATTERNS = (
    re.compile(
        r"\b(?:let us know|tell us|share (?:your|with us) "
        r"(?:thoughts?|feedback|opinions?)|comment below|leave a comment|"
        r"join the discussion|sound off)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:what|who) do you think\b|\bhow about you\b|\bwhat about you\b|"
        r"\bwhat(?:'s| is) your\b|\bwho(?:'s| is) your\b|"
        r"\bwhich\b[^\n?]{0,120}\b(?:would|will|do) you\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:дайте нам знать|расскажите нам|сообщите нам|"
        r"поделитесь(?: с нами)? (?:мнением|мыслями|отзывом|отзывами|идеями)|"
        r"напишите (?:нам|в комментариях)|оставьте комментарий|"
        r"оставляйте комментарии|жд[её]м ваших? (?:мнений|мыслей|ответов))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:что вы думаете|как вы думаете|кто,?\s+по вашему мнению|"
        r"ка(?:кой|кая|кое|кие) у вас|что бы вы|кого бы вы|"
        r"а вы[^\n?]{0,120}\?)",
        re.IGNORECASE,
    ),
)


@dataclass(slots=True)
class ProtectedText:
    text: str
    tokens: dict[str, str] = field(default_factory=dict)

    def restore(self, translated: str) -> str:
        for token, value in self.tokens.items():
            if token not in translated:
                raise ValueError(f"Translation lost protected token {token}")
            translated = translated.replace(token, value)
        return translated


def resolve_mentions(source: SourceMessage) -> str:
    text = source.content

    def user_replace(match: re.Match[str]) -> str:
        user_id = int(match.group(1))
        return "@" + source.user_mentions.get(user_id, str(user_id))

    def role_replace(match: re.Match[str]) -> str:
        role_id = int(match.group(1))
        return "@" + source.role_mentions.get(role_id, str(role_id))

    text = USER_MENTION_RE.sub(user_replace, text)
    text = ROLE_MENTION_RE.sub(role_replace, text)
    return text


def _protect_code_for_cleanup(text: str) -> tuple[str, dict[str, str]]:
    """Временно защищает code blocks и inline code от URL/feedback-фильтра."""
    tokens: dict[str, str] = {}
    counter = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = f"LBCLEAN{counter:04d}TOKEN"
        counter += 1
        tokens[token] = match.group(0)
        return token

    for regex in (CODE_BLOCK_RE, INLINE_CODE_RE):
        text = regex.sub(replace, text)
    return text, tokens


def _restore_cleanup_tokens(text: str, tokens: dict[str, str]) -> str:
    for token, value in tokens.items():
        text = text.replace(token, value)
    return text


def _remove_urls_outside_code(text: str) -> str:
    """Удаляет URL вне code, сохраняя полезный label Markdown-ссылки."""
    protected, tokens = _protect_code_for_cleanup(text)
    protected = MARKDOWN_LINK_RE.sub(r"\1", protected)
    protected = URL_RE.sub("", protected)
    return _restore_cleanup_tokens(protected, tokens)


def _is_feedback_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in FEEDBACK_LINE_PATTERNS)


def _remove_feedback_lines(text: str) -> str:
    """Удаляет отдельные строки с просьбой ответить или поделиться мнением."""
    protected, tokens = _protect_code_for_cleanup(text)
    lines = protected.split("\n")
    remove_indexes = {index for index, line in enumerate(lines) if _is_feedback_line(line)}

    # Не оставляем дополнительный пустой абзац между соседними содержательными блоками.
    for index in tuple(remove_indexes):
        if (
            index > 0
            and index + 1 < len(lines)
            and not lines[index - 1].strip()
            and not lines[index + 1].strip()
        ):
            remove_indexes.add(index + 1)

    filtered = "\n".join(
        line for index, line in enumerate(lines) if index not in remove_indexes
    ).strip()
    return _restore_cleanup_tokens(filtered, tokens)


def sanitize(source: SourceMessage) -> str:
    text = resolve_mentions(source)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CHANNEL_CONTEXT_LINE_RE.sub("", text)
    text = CHANNEL_MENTION_RE.sub("", text)
    text = CUSTOM_EMOJI_RE.sub("", text)
    text = re.sub(r"(?<!\w)@everyone\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)@here\b", "", text, flags=re.IGNORECASE)

    # Все URL в обычном тексте удаляются до перевода. URL внутри code сохраняются.
    text = _remove_urls_outside_code(text)
    # Feedback-призывы и вопросы к аудитории не отправляются в Groq.
    text = _remove_feedback_lines(text)

    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def protect_nontranslatable(text: str) -> ProtectedText:
    protected = ProtectedText(text=text)
    counter = 0

    def protect_value(value: str) -> str:
        nonlocal counter
        token = f"LBPROTECTED{counter:04d}TOKEN"
        counter += 1
        protected.tokens[token] = value
        return token

    for regex in (CODE_BLOCK_RE, INLINE_CODE_RE):
        while True:
            match = regex.search(protected.text)
            if not match:
                break
            token = protect_value(match.group(0))
            protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    while True:
        match = PLAIN_MENTION_RE.search(protected.text)
        if not match:
            break
        token = protect_value(match.group(0))
        protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    while True:
        match = re.search(r"\n+", protected.text)
        if not match:
            break
        token = protect_value(match.group(0))
        protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    return protected
