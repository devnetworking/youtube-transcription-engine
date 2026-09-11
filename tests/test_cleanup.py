from src.models import TranscriptSegment
from src.transcription.cleanup import clean_segments


def _seg(start, text, **kwargs):
    return TranscriptSegment(start=start, end=start + 2, text=text, **kwargs)


def test_removes_exact_duplicate_consecutive_segments():
    segments = [
        _seg(0, "hello and welcome"),
        _seg(2, "hello and welcome"),
        _seg(4, "to the show"),
    ]
    cleaned = clean_segments(segments)
    assert [s.text for s in cleaned] == ["hello and welcome", "to the show"]


def test_trims_rolling_caption_overlap():
    segments = [
        _seg(0, "and then we deploy the"),
        _seg(2, "the model to production"),
    ]
    cleaned = clean_segments(segments)
    assert [s.text for s in cleaned] == ["and then we deploy the", "model to production"]


def test_normalizes_spacing_and_punctuation():
    segments = [_seg(0, "hello   world  ,  how are you ??")]
    cleaned = clean_segments(segments)
    assert cleaned[0].text == "hello world, how are you?"


def test_preserves_genuine_mid_sentence_repetition():
    # A speaker saying "very very good" is content, not a pipeline artifact,
    # and must not be silently rewritten (spec section 6 fidelity rules).
    segments = [_seg(0, "it was very very good")]
    cleaned = clean_segments(segments)
    assert cleaned[0].text == "it was very very good"


def test_filler_word_removal_is_opt_in():
    segments = [_seg(0, "um so basically it works")]

    default_cleaned = clean_segments(segments)
    assert "um" in default_cleaned[0].text

    stripped = clean_segments(segments, remove_filler_words=True)
    assert "um" not in stripped[0].text.split()
