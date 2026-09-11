"""Shared sentence-splitting used by summary/keyword/research analysis.

YouTube auto-generated captions frequently carry no punctuation at all
(this is common, not an edge case, especially outside English). A naive
`split on [.!?]` then returns the *entire* transcript as one "sentence",
which silently turns every downstream consumer (summary, takeaways,
key-term context) into a copy of the full transcript. This splitter
falls back to fixed-size word chunking whenever punctuation-based
splitting fails to produce reasonably sized pieces, so no single
"sentence" can ever run away with the whole text.
"""

from __future__ import annotations

import re

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_MAX_SENTENCE_CHARS = 240
_FALLBACK_CHUNK_WORDS = 20


def split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    rough_pieces = [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]

    sentences: list[str] = []
    for piece in rough_pieces:
        if len(piece) <= _MAX_SENTENCE_CHARS:
            sentences.append(piece)
        else:
            sentences.extend(_chunk_by_words(piece))
    return sentences


def _chunk_by_words(text: str, chunk_size: int = _FALLBACK_CHUNK_WORDS) -> list[str]:
    words = text.split()
    return [
        " ".join(words[i : i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]
