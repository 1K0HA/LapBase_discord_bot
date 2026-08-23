from __future__ import annotations

from app.config import Config
from app.models import ProcessedPost

RICH_MESSAGE_MAX_CHARS = 32768
AUTOPOST_TAG = "#autopost@lapbase"


def _escape_media_url(url: str) -> str:
    # Rich Markdown media URL: keep URL, only guard characters that terminate markdown target early.
    return url.replace(" ", "%20")


def media_markdown(image_urls: list[str]) -> str:
    urls = image_urls[:50]
    if not urls:
        return ""
    blocks = [f"![]({_escape_media_url(url)})" for url in urls]
    if len(blocks) == 1:
        return blocks[0]
    return "<tg-collage>\n\n" + "\n".join(blocks) + "\n\n</tg-collage>"


def build_markdown(post: ProcessedPost, config: Config) -> str:
    pieces: list[str] = []
    if config.show_source_channel and (post.markdown.strip() or post.image_urls):
        pieces.append(f"# **Источник официальный DISCORD: #{post.channel_name}**")
    if post.markdown.strip():
        pieces.append(post.markdown.strip())
    media = media_markdown(post.image_urls)
    if media:
        pieces.append(media)

    pieces.append(AUTOPOST_TAG)
    return "\n\n".join(pieces).strip()


def text_budget(channel_name: str, image_urls: list[str], config: Config) -> int:
    overhead = len(media_markdown(image_urls)) + len(AUTOPOST_TAG) + 260
    if config.show_source_channel:
        overhead += len(channel_name) + 40
    return max(1000, RICH_MESSAGE_MAX_CHARS - overhead)
