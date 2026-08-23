from __future__ import annotations

import json
import logging
import re

from groq import AsyncGroq

from app.config import Config
from app.processor.sanitizer import ProtectedText

logger = logging.getLogger(__name__)

def _translation_schema(segment_count: int = 1) -> dict:
    if segment_count <= 1:
        return {
            "name": "lapbase_translation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"translated": {"type": "string"}},
                "required": ["translated"],
                "additionalProperties": False,
            },
        }

    return {
        "name": "lapbase_translation_segments",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "translated": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": segment_count,
                    "maxItems": segment_count,
                }
            },
            "required": ["translated"],
            "additionalProperties": False,
        },
    }


def _split_on_linebreak_tokens(protected: ProtectedText) -> tuple[list[str], list[str]]:
    """Split text into chunks while preserving exact protected newline runs."""
    newline_tokens = {
        token: value
        for token, value in protected.tokens.items()
        if value and "\n" in value and value.strip("\n") == ""
    }
    if not newline_tokens:
        return [protected.text], []

    pattern = re.compile(
        "(" + "|".join(
            re.escape(token)
            for token in sorted(newline_tokens, key=len, reverse=True)
        ) + ")"
    )
    parts = pattern.split(protected.text)
    segments: list[str] = []
    separators: list[str] = []

    for part in parts:
        if part in newline_tokens:
            separators.append(part)
        else:
            segments.append(part)

    if len(segments) != len(separators) + 1:
        raise ValueError("Invalid protected line-break structure")

    return segments, separators



class Translator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = AsyncGroq(api_key=config.groq_api_key)

    async def translate(self, protected: ProtectedText) -> str:
        if not protected.text.strip():
            return protected.restore(protected.text)

        segments, separators = _split_on_linebreak_tokens(protected)
        nonempty_indexes = [i for i, segment in enumerate(segments) if segment.strip()]
        payload_segments = [segments[i] for i in nonempty_indexes]

        if not payload_segments:
            return protected.restore(protected.text)

        response = await self.client.chat.completions.create(
            model=self.config.groq_model,
            reasoning_effort=self.config.groq_reasoning_effort,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Translate each supplied Discord news text segment from English to natural Russian. "
                        "Correct Russian grammar and style, but never add, remove, reinterpret, or invent facts. "
                        "The input is an ordered JSON array. Return exactly the same number of translated strings "
                        "in exactly the same order. Never merge or split array items. "
                        "Preserve Markdown, headings, lists, quotes, bold and spoilers inside each item. "
                        "Every token matching LBPROTECTED####TOKEN is immutable: copy it exactly and never "
                        "translate, alter, remove or reorder it. Return only the requested JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload_segments, ensure_ascii=False),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": _translation_schema(len(payload_segments)),
            },
            temperature=0,
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        translated_payload = data["translated"]

        if len(payload_segments) == 1 and isinstance(translated_payload, str):
            translated_payload = [translated_payload]

        if not isinstance(translated_payload, list) or len(translated_payload) != len(payload_segments):
            raise ValueError("Translation returned an invalid segment count")

        translated_segments = list(segments)
        for index, translated_segment in zip(nonempty_indexes, translated_payload, strict=True):
            translated_segments[index] = translated_segment.strip()

        rebuilt: list[str] = []
        for i, segment in enumerate(translated_segments):
            rebuilt.append(segment)
            if i < len(separators):
                rebuilt.append(separators[i])

        # Exact newline tokens are restored after translation, so Groq cannot merge lines.
        return protected.restore("".join(rebuilt)).strip()

    async def compress(self, markdown: str, max_chars: int) -> str:
        if len(markdown) <= max_chars:
            return markdown
        response = await self.client.chat.completions.create(
            model=self.config.groq_model,
            reasoning_effort=self.config.groq_reasoning_effort,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Shorten the Russian Telegram post to at most {max_chars} characters. "
                        "Preserve all facts, URLs, code, names, warnings, paragraph boundaries and line breaks. "
                        "Do not invent information. Return only JSON."
                    ),
                },
                {"role": "user", "content": markdown},
            ],
            response_format={"type": "json_schema", "json_schema": TRANSLATION_SCHEMA},
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        result = json.loads(raw)["translated"].strip()
        if len(result) > max_chars:
            # Defensive hard cap only after the model has already compressed it.
            result = result[: max_chars - 1].rstrip() + "…"
        return result

    async def health(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False
