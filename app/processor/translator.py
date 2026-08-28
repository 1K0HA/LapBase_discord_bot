from __future__ import annotations

import json
import logging
import re

from groq import AsyncGroq

from app.config import Config
from app.processor.sanitizer import ProtectedText

logger = logging.getLogger(__name__)

def _translation_schema(segment_count: int) -> dict:
    """Возвращает JSON Schema с точным числом переводимых сегментов."""
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


COMPRESSION_SCHEMA = {
    "name": "lapbase_compression",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"translated": {"type": "string"}},
        "required": ["translated"],
        "additionalProperties": False,
    },
}


def _unwrap_accidental_json_array(value: str) -> str:
    """Исправляет защитный случай, когда модель завернула один текст в JSON-массив."""
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return value
    try:
        parsed = json.loads(stripped)
    except Exception:
        return value
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], str):
        return parsed[0]
    return value



def _split_on_linebreak_tokens(protected: ProtectedText) -> tuple[list[str], list[str]]:
    """Делит текст на сегменты, сохраняя точные защищённые последовательности переносов."""
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
        raise ValueError("Нарушена структура защищённых переносов строк")

    return segments, separators



class Translator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = AsyncGroq(
            api_key=config.groq_api_key,
            timeout=float(config.groq_timeout_seconds),
            max_retries=0,
        )

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
                        "The input JSON object contains an ordered array in the field segments. Return exactly the same number of translated strings "
                        "in exactly the same order. Never merge or split array items. "
                        "Preserve Markdown, headings, lists, quotes, bold and spoilers inside each item. "
                        "Every token matching LBPROTECTED####TOKEN is immutable: copy it exactly and never "
                        "translate, alter, remove or reorder it. Return only the requested JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"segments": payload_segments}, ensure_ascii=False),
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

        if not isinstance(translated_payload, list) or len(translated_payload) != len(payload_segments):
            raise ValueError("Groq вернул неверное количество сегментов перевода")

        translated_segments = list(segments)
        for index, translated_segment in zip(nonempty_indexes, translated_payload, strict=True):
            translated_segment = _unwrap_accidental_json_array(translated_segment)
            translated_segments[index] = translated_segment.strip()

        rebuilt: list[str] = []
        for i, segment in enumerate(translated_segments):
            rebuilt.append(segment)
            if i < len(separators):
                rebuilt.append(separators[i])

        # Точные токены переносов восстанавливаются после перевода, поэтому Groq не может слить строки.
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
            response_format={"type": "json_schema", "json_schema": COMPRESSION_SCHEMA},
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        result = json.loads(raw)["translated"].strip()
        if len(result) > max_chars:
            # Жёсткий лимит применяется только после попытки смыслового сжатия моделью.
            result = result[: max_chars - 1].rstrip() + "…"
        return result

    async def health(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False
