import pytest

from src.utils.timestamps import format_timestamp, is_ordered, parse_timestamp


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "00:00:00"),
        (59, "00:00:59"),
        (61, "00:01:01"),
        (3661, "01:01:01"),
        (4318, "01:11:58"),
    ],
)
def test_format_timestamp_hhmmss(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_format_timestamp_mmss_style_under_an_hour():
    assert format_timestamp(90, style="mmss") == "01:30"


def test_format_timestamp_negative_clamped_to_zero():
    assert format_timestamp(-5) == "00:00:00"


def test_parse_timestamp_hhmmss():
    assert parse_timestamp("01:02:03") == 3723


def test_parse_timestamp_mmss():
    assert parse_timestamp("02:03") == 123


def test_parse_timestamp_invalid_raises():
    with pytest.raises(ValueError):
        parse_timestamp("not-a-timestamp")


def test_is_ordered_true_for_nondecreasing():
    assert is_ordered([0, 1.5, 1.5, 10])


def test_is_ordered_false_when_out_of_order():
    assert not is_ordered([0, 5, 3])
