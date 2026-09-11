"""Additional, purely-extractive analysis (spec sections 25 and 26, and the
"Mentioned Resources" / "Questions or Research Leads" Markdown sections).

Every value returned here is either a literal substring of the
transcript (a URL, a matched sentence) or a template built from
transcript-derived keywords. Nothing is invented about the video's
content - this keeps analysis intelligent without risking the
hallucination the spec explicitly forbids.
"""

from __future__ import annotations

import re

from .text_units import split_into_sentences

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s,)\]]+", re.IGNORECASE)

_RESEARCH_TRIGGERS_EN = {
    "research_question": ("we ask", "the question is", "we investigate", "we explore whether"),
    "hypotheses": ("we hypothesize", "our hypothesis", "we expect that", "we predict that"),
    "methodology": ("we use", "we used", "our method", "our approach", "methodology", "we trained", "we propose"),
    "datasets": ("dataset", "data set", "corpus", "benchmark"),
    "algorithms": ("algorithm", "model architecture", "neural network", "we implement"),
    "metrics": ("accuracy", "precision", "recall", "f1", "metric", "performance of"),
    "limitations": ("limitation", "a caveat", "does not generalize", "future work is needed"),
    "future_work": ("future work", "in future work", "we plan to", "next steps"),
    "citations": ("et al", "published in", "according to the paper"),
}

_RESEARCH_TRIGGERS_FR = {
    "research_question": ("on se demande", "la question est", "nous étudions", "on cherche à savoir"),
    "hypotheses": ("notre hypothèse", "on suppose que", "on s'attend à ce que"),
    "methodology": ("notre méthode", "notre approche", "méthodologie", "on a utilisé", "nous proposons"),
    "datasets": ("jeu de données", "base de données", "échantillon de", "corpus"),
    "algorithms": ("algorithme", "modèle", "réseau de neurones"),
    "metrics": ("précision", "taux de", "performance de", "indicateur"),
    "limitations": ("limite", "limitation", "ne se généralise pas"),
    "future_work": ("travaux futurs", "prochaine étape", "on prévoit de"),
    "citations": ("selon l'étude", "publié dans", "et al"),
}

_RESEARCH_TRIGGERS_BY_LANGUAGE = {
    "en": _RESEARCH_TRIGGERS_EN,
    "fr": _RESEARCH_TRIGGERS_FR,
}


def extract_resources(full_text: str) -> dict[str, list[str]]:
    urls = sorted(set(_URL_RE.findall(full_text)))
    resources: dict[str, list[str]] = {}
    if urls:
        resources["Websites"] = urls
    return resources


def generate_questions(key_topics: list[str], max_questions: int = 5) -> list[str]:
    templates = [
        "What are the practical implications of {topic}, as discussed in this video?",
        "How does {topic} compare with alternative approaches not covered here?",
        "What evidence or data supports the claims made about {topic}?",
    ]
    questions = []
    for i, topic in enumerate(key_topics[:max_questions]):
        template = templates[i % len(templates)]
        questions.append(template.format(topic=topic))
    return questions


def research_mode_analysis(full_text: str, language: str | None = None) -> dict[str, list[str]]:
    sentences = split_into_sentences(full_text)
    triggers_by_category = _RESEARCH_TRIGGERS_BY_LANGUAGE.get((language or "en").lower()[:2], _RESEARCH_TRIGGERS_EN)

    results: dict[str, list[str]] = {}
    for category, triggers in triggers_by_category.items():
        matches = [s for s in sentences if any(t in s.lower() for t in triggers)]
        if matches:
            results[category] = matches[:5]
    return results
