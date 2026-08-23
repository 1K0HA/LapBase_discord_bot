from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import SourceMessage

DISCORD_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:discord\.gg|discord(?:app)?\.com)/[^\s<>()]+",
    re.IGNORECASE,
)
CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
INLINE_CODE_RE = re.compile(r"(?<!`)`[^`\n]+`(?!`)")
URL_RE = re.compile(r"https?://[^\s<>\]\[()]+", re.IGNORECASE)
PLAIN_MENTION_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.-]+")
CHANNEL_CONTEXT_LINE_RE = re.compile(
    r"(?m)^[^\r\n]{0,200}?<#\d+>\s*:\s*(?:\r?\n)?",
    re.UNICODE,
)
CHANNEL_MENTION_RE = re.compile(r"<#\d+>")


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


def sanitize(source: SourceMessage) -> str:
    text = resolve_mentions(source)
    # Normalize OS-specific endings while preserving the number of line breaks.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove Discord routing/source labels on any line, for example:
    # "Last Asylum: Plague <#1493675820601053205>:"
    # This is metadata added by Discord/feed routing, not publication content.
    text = CHANNEL_CONTEXT_LINE_RE.sub("", text)

    # Remove any remaining raw Discord channel mention tokens everywhere.
    # Surrounding normal text is kept intact.
    text = CHANNEL_MENTION_RE.sub("", text)
    text = DISCORD_URL_RE.sub("", text)
    text = CUSTOM_EMOJI_RE.sub("", text)
    text = re.sub(r"(?<!\w)@everyone\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)@here\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def protect_nontranslatable(text: str) -> ProtectedText:
    protected = ProtectedText(text=text)
    counter = 0

    def protect_value(value: str, transform=lambda s: s) -> str:
        nonlocal counter
        token = f"LBPROTECTED{counter:04d}TOKEN"
        counter += 1
        protected.tokens[token] = transform(value)
        return token

    # Protect code first so URLs/mentions inside code aren't separately touched.
    for regex in (CODE_BLOCK_RE, INLINE_CODE_RE):
        while True:
            match = regex.search(protected.text)
            if not match:
                break
            token = protect_value(match.group(0))
            protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    # Keep non-Discord URLs verbatim, displayed directly in quotation marks.
    while True:
        match = URL_RE.search(protected.text)
        if not match:
            break
        token = protect_value(match.group(0), lambda url: f'"{url}"')
        protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    # Preserve plain user/role mention labels exactly.
    while True:
        match = PLAIN_MENTION_RE.search(protected.text)
        if not match:
            break
        token = protect_value(match.group(0))
        protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    # Preserve the original line/paragraph structure so translation cannot
    # collapse headings and emoji-prefixed lines into a single paragraph.
    while True:
        match = re.search(r"\n+", protected.text)
        if not match:
            break
        token = protect_value(match.group(0))
        protected.text = protected.text[: match.start()] + token + protected.text[match.end() :]

    return protected
