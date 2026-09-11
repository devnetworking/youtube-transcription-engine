"""Plain-text exporter (spec section 12): no Markdown syntax, no tables,
raw cleaned transcript prioritized over analysis.
"""

from __future__ import annotations

from ..models import VideoMetadata
from ..utils.timestamps import format_timestamp
from .blocks import ChapterSection, flatten_blocks

_RULE = "=" * 50


def build_text(metadata: VideoMetadata, sections: list[ChapterSection], include_timestamps: bool = True) -> str:
    lines = [
        metadata.title or "Untitled Video",
        f"URL: {metadata.url or 'Unknown'}",
        f"CHANNEL: {metadata.channel or 'Unknown'}",
        f"LANGUAGE: {metadata.detected_language or 'Unknown'}",
        "",
        _RULE,
        "TRANSCRIPT",
        _RULE,
        "",
    ]

    for block in flatten_blocks(sections):
        timestamp_prefix = f"[{format_timestamp(block.start_seconds)}] " if include_timestamps else ""
        code_prefix = "[code, reconstructed from speech] " if block.is_code else ""
        lines.append(f"{timestamp_prefix}{code_prefix}{block.text}")

    lines += [
        "",
        _RULE,
        "END OF TRANSCRIPT",
        _RULE,
        "",
    ]

    return "\n".join(lines)
