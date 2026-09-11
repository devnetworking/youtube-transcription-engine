from src.analysis.quality import compute_quality
from src.models import QualityLevel, TranscriptionResult, TranscriptionSource, TranscriptSegment


def _result(source, uncertain_count=0, total=10, **kwargs):
    segments = [TranscriptSegment(start=i, end=i + 1, text="word", uncertain=(i < uncertain_count)) for i in range(total)]
    return TranscriptionResult(segments=segments, source=source, **kwargs)


def test_manual_captions_low_uncertainty_is_high_quality():
    result = _result(TranscriptionSource.MANUAL_CAPTIONS, uncertain_count=0)
    assert compute_quality(result) == QualityLevel.HIGH


def test_auto_captions_high_uncertainty_is_low_quality():
    result = _result(TranscriptionSource.AUTO_CAPTIONS, uncertain_count=5, total=10)
    assert compute_quality(result) == QualityLevel.LOW


def test_whisper_low_confidence_language_is_low_quality():
    result = _result(TranscriptionSource.WHISPER, uncertain_count=0, model="small", low_confidence_language=True)
    assert compute_quality(result) == QualityLevel.LOW


def test_whisper_large_model_low_uncertainty_is_high_quality():
    result = _result(TranscriptionSource.WHISPER, uncertain_count=0, model="large-v3")
    assert compute_quality(result) == QualityLevel.HIGH
