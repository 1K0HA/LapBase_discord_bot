import sys
import types

groq_stub = types.ModuleType("groq")
groq_stub.AsyncGroq = object
sys.modules.setdefault("groq", groq_stub)

from app.processor.sanitizer import protect_nontranslatable
from app.processor.translator import _split_on_linebreak_tokens


def test_split_preserves_exact_newline_runs():
    original = "Title\nLine\n\nParagraph\n\n\nEnd"
    protected = protect_nontranslatable(original)
    segments, separators = _split_on_linebreak_tokens(protected)

    assert len(segments) == 4
    assert [protected.tokens[token] for token in separators] == ["\n", "\n\n", "\n\n\n"]

    rebuilt = []
    for i, segment in enumerate(segments):
        rebuilt.append(segment)
        if i < len(separators):
            rebuilt.append(separators[i])

    assert protected.restore("".join(rebuilt)) == original
