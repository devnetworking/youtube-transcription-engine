"""Extractive summarization (spec sections 11 and 25).

Uses a Luhn-style word-frequency sentence scorer rather than an LLM
call: the tool has no configured LLM dependency, and an extractive
approach has the useful property that every summary sentence is a
sentence someone actually said - it cannot introduce claims that are
not in the transcript, which matters for the "never hallucinate"
mandate in section 6.
"""

from __future__ import annotations

import re
from collections import Counter

from .keywords import get_stopwords
from .text_units import split_into_sentences


def _score_sentences(sentences: list[str], language: str | None = None) -> list[float]:
    stopwords = get_stopwords(language)
    word_freq: Counter = Counter()
    tokenized: list[list[str]] = []
    for sentence in sentences:
        words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+", sentence)]
        tokenized.append(words)
        word_freq.update(w for w in words if w not in stopwords and len(w) > 2)

    if not word_freq:
        return [0.0] * len(sentences)

    max_freq = max(word_freq.values())
    normalized = {w: c / max_freq for w, c in word_freq.items()}

    scores = []
    for words in tokenized:
        if not words:
            scores.append(0.0)
            continue
        score = sum(normalized.get(w, 0.0) for w in words) / len(words)
        scores.append(score)
    return scores


def generate_summary(full_text: str, max_sentences: int = 6, language: str | None = None) -> str:
    sentences = split_into_sentences(full_text)
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    scores = _score_sentences(sentences, language=language)
    ranked_indices = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)
    top_indices = sorted(ranked_indices[:max_sentences])
    return " ".join(sentences[i] for i in top_indices)


def generate_takeaways(full_text: str, max_items: int = 5, language: str | None = None) -> list[str]:
    sentences = split_into_sentences(full_text)
    if not sentences:
        return []
    scores = _score_sentences(sentences, language=language)
    ranked_indices = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)
    top_indices = sorted(ranked_indices[:max_items])
    return [sentences[i] for i in top_indices]
