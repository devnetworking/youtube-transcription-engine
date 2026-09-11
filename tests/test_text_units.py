from src.analysis.keywords import extract_key_terms_with_context
from src.analysis.summary import generate_summary, generate_takeaways
from src.analysis.text_units import split_into_sentences


def test_split_into_sentences_uses_punctuation_when_present():
    text = "First sentence. Second sentence! Third one?"
    assert split_into_sentences(text) == ["First sentence.", "Second sentence!", "Third one?"]


def test_split_into_sentences_falls_back_when_no_punctuation():
    # Regression test: YouTube auto-captions often carry no punctuation
    # at all. A naive `.split('.')`-style splitter treats the whole
    # transcript as one "sentence", which then gets duplicated into
    # every downstream summary/key-term/takeaway field.
    words = ["mot"] * 500
    text = " ".join(words)

    sentences = split_into_sentences(text)

    assert len(sentences) > 1
    assert all(len(s) < 300 for s in sentences)
    # No information should be lost: every word still appears once.
    assert sum(len(s.split()) for s in sentences) == 500


def test_key_terms_context_bounded_for_unpunctuated_transcript():
    words = (["bonjour"] * 5 + ["ressources", "humaines", "planification"]) * 40
    text = " ".join(words)

    terms = extract_key_terms_with_context(text, top_n=3)

    for context in terms.values():
        assert len(context) < 300


def test_summary_bounded_for_unpunctuated_transcript():
    words = (["bonjour"] * 5 + ["ressources", "humaines", "planification"]) * 100
    text = " ".join(words)

    summary = generate_summary(text)
    takeaways = generate_takeaways(text)

    assert len(summary) < 2000
    assert all(len(t) < 300 for t in takeaways)
