from __future__ import annotations

from app.config import Config
from app.models import ProcessedPost, SourceMessage
from app.processor.renderer import build_message_html, text_budget
from app.processor.sanitizer import protect_nontranslatable, sanitize
from app.processor.translator import Translator


class PostProcessor:
    def __init__(self, config: Config, translator: Translator) -> None:
        self.config = config
        self.translator = translator

    async def process(self, source: SourceMessage) -> ProcessedPost:
        clean = sanitize(source)
        translated = ""
        if clean:
            translated = await self.translator.translate(protect_nontranslatable(clean))
            budget = text_budget(source.channel_name, source.image_urls, self.config)
            if len(translated) > budget:
                translated = await self.translator.compress(translated, budget)
        return ProcessedPost(
            markdown=translated,
            channel_name=source.channel_name,
            image_urls=source.image_urls,
        )

    async def render(self, source: SourceMessage) -> str:
        return build_message_html(await self.process(source), self.config)
