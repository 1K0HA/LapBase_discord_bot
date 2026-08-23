import json
import sys
import types

groq_stub = types.ModuleType("groq")
groq_stub.AsyncGroq = object
sys.modules.setdefault("groq", groq_stub)

from app.processor.translator import (
    _translation_schema,
    _unwrap_accidental_json_array,
)


def test_translation_schema_always_requires_array_for_one_segment():
    schema = _translation_schema(1)["schema"]["properties"]["translated"]
    assert schema["type"] == "array"
    assert schema["minItems"] == 1
    assert schema["maxItems"] == 1


def test_accidental_json_array_string_is_unwrapped():
    assert _unwrap_accidental_json_array('["ыутв ьуыыфпу"]') == "ыутв ьуыыфпу"
    assert _unwrap_accidental_json_array("обычный текст") == "обычный текст"
