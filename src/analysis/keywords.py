"""Lightweight keyword/key-term extraction.

Deliberately heuristic (stopword-filtered frequency counting) rather
than a call to an external LLM: the recommended stack (spec section 16)
has no LLM client, so "intelligent organization" here means classical,
fully local text analysis that runs the same way every time.
"""

from __future__ import annotations

import re
from collections import Counter

from .text_units import split_into_sentences

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "in", "on",
    "at", "to", "for", "with", "by", "from", "as", "is", "are", "was", "were",
    "be", "been", "being", "it", "its", "this", "that", "these", "those", "i",
    "you", "he", "she", "we", "they", "them", "his", "her", "their", "our",
    "your", "my", "me", "us", "do", "does", "did", "have", "has", "had",
    "not", "no", "yes", "can", "could", "will", "would", "should", "may",
    "might", "must", "there", "here", "what", "which", "who", "whom", "when",
    "where", "why", "how", "all", "any", "each", "some", "just", "like",
    "very", "really", "also", "about", "into", "than", "up", "out", "over",
    "under", "again", "one", "two", "get", "got", "going", "go", "know",
    "think", "thing", "things", "okay", "ok", "well", "right", "actually",
    "basically", "kind", "sort", "lot", "much", "many",
}

FRENCH_STOPWORDS = {
    "les", "des", "que", "qui", "qu'on", "qu'il", "qu'elle", "est", "sont",
    "dans", "donc", "pour", "avec", "sans", "sur", "sous", "par", "vers",
    "chez", "cette", "cet", "ces", "ceux", "celle", "celles", "celui",
    "leur", "leurs", "nous", "vous", "ils", "elle", "elles", "lui",
    "mon", "ton", "son", "mes", "tes", "ses", "notre", "votre", "nos", "vos",
    "une", "un", "du", "de", "la", "le", "au", "aux", "et", "ou", "mais",
    "donc", "car", "ni", "or", "comme", "quand", "alors", "aussi", "très",
    "plus", "moins", "trop", "peu", "bien", "tout", "toute", "tous", "toutes",
    "être", "avoir", "fait", "faire", "fois", "dit", "va", "vais", "vas",
    "peut", "peux", "pouvoir", "faut", "falloir", "veux", "veut", "vouloir",
    "ici", "là", "où", "dont", "on", "ne", "pas", "plus", "encore", "déjà",
    "toujours", "jamais", "puis", "puisque", "parce", "donc", "ça", "cela",
    "voilà", "voici", "entre", "pendant", "après", "avant", "donc", "ainsi",
    "c'est", "c'était", "s'est", "n'est", "n'était", "qu'est", "quoi",
    "quelque", "quelques", "chose",
}

STOPWORDS_BY_LANGUAGE = {
    "en": STOPWORDS,
    "fr": FRENCH_STOPWORDS,
}

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'-]{1,}")


def get_stopwords(language: str | None) -> set[str]:
    key = (language or "en").lower()[:2]
    return STOPWORDS_BY_LANGUAGE.get(key, STOPWORDS)


def extract_keywords(text: str, top_n: int = 15, language: str | None = None) -> list[str]:
    stopwords = get_stopwords(language)
    words = [w.lower() for w in _WORD_RE.findall(text)]
    counts = Counter(w for w in words if w not in stopwords and len(w) > 2)
    return [word for word, _ in counts.most_common(top_n)]


def extract_key_terms_with_context(full_text: str, top_n: int = 12, language: str | None = None) -> dict[str, str]:
    """Return {term: one representative sentence it appears in}."""
    sentences = split_into_sentences(full_text)
    keywords = extract_keywords(full_text, top_n=top_n, language=language)

    terms: dict[str, str] = {}
    for keyword in keywords:
        for sentence in sentences:
            if keyword in sentence.lower():
                terms[keyword] = sentence.strip()
                break
    return terms
