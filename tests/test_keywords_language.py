from src.analysis.chapters import infer_chapters
from src.analysis.keywords import extract_keywords
from src.models import TranscriptSegment


def test_extract_keywords_uses_french_stopwords_for_french_language():
    text = "les ressources humaines sont des concepts que qui donc planification talents"
    keywords_fr = extract_keywords(text, top_n=5, language="fr")

    # French function words must not dominate the topic list.
    assert "les" not in keywords_fr
    assert "des" not in keywords_fr
    assert "que" not in keywords_fr
    assert "qui" not in keywords_fr
    assert "ressources" in keywords_fr or "planification" in keywords_fr


def test_extract_keywords_defaults_to_english_stopwords():
    text = "the quick brown fox jumps over the lazy dog technology innovation"
    keywords = extract_keywords(text, top_n=5)
    assert "the" not in keywords
    assert "over" not in keywords


def test_infer_chapters_titles_respect_language():
    segments = [
        TranscriptSegment(
            start=i * 60,
            end=i * 60 + 55,
            text="les ressources humaines sont des concepts que qui donc planification talents",
        )
        for i in range(20)
    ]
    chapters = infer_chapters(segments, language="fr")
    for chapter in chapters:
        assert "Les" not in chapter.title.split(" / ")
        assert "Des" not in chapter.title.split(" / ")
