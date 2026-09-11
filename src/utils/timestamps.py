"""Timestamp formatting/parsing helpers (spec section 9)."""

from __future__ import annotations


def format_timestamp(seconds: float, style: str = "hhmmss") -> str:
    """Format a second offset as HH:MM:SS (default) or MM:SS."""
    if seconds is None or seconds < 0:
        seconds = 0
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if style == "mmss" and hours == 0:
        return f"{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_timestamp(value: str) -> float:
    """Parse an HH:MM:SS or MM:SS string into a second offset."""
    parts = value.strip().split(":")
    if not all(p.isdigit() or (p.startswith("-") and p[1:].isdigit()) for p in parts):
        raise ValueError(f"Invalid timestamp: {value!r}")

    parts_i = [int(p) for p in parts]
    if len(parts_i) == 3:
        hours, minutes, secs = parts_i
    elif len(parts_i) == 2:
        hours = 0
        minutes, secs = parts_i
    elif len(parts_i) == 1:
        hours, minutes = 0, 0
        secs = parts_i[0]
    else:
        raise ValueError(f"Invalid timestamp: {value!r}")

    return hours * 3600 + minutes * 60 + secs


def is_ordered(timestamps: list[float]) -> bool:
    """Return True if timestamps are non-decreasing."""
    return all(a <= b for a, b in zip(timestamps, timestamps[1:]))
