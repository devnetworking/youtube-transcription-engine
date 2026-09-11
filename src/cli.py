"""CLI entry point (spec section 18)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

# Some Windows terminals (legacy conhost, or a non-UTF-8 codepage) can't
# encode the checkmark/dim symbols rich prints; force UTF-8 with a safe
# fallback so progress output never crashes the run.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

from .config import load_config
from .pipeline import process_video, resolve_urls

app = typer.Typer(add_completion=False, help="Intelligent YouTube transcription engine.")
console = Console(legacy_windows=False)

_LEVEL_STYLES = {"error": "red", "success": "green", "warning": "yellow", "step": "dim"}


def _console_report(message: str, level: str) -> None:
    style = _LEVEL_STYLES.get(level)
    console.print(f"[{style}]{message}[/{style}]" if style else message)


@app.command()
def main(
    urls: list[str] = typer.Argument(..., help="One or more YouTube video URLs."),
    output: Path = typer.Option(Path("output"), "--output", help="Output directory root."),
    language: str = typer.Option("auto", "--language", help="Preferred language code, or 'auto'."),
    model: str = typer.Option("auto", "--model", help="Whisper model size, or 'auto' to size by available memory."),
    prefer_captions: bool = typer.Option(True, "--prefer-captions/--no-prefer-captions", help="Prefer YouTube captions over local transcription."),
    force_whisper: bool = typer.Option(False, "--force-whisper", help="Skip captions and always transcribe audio locally."),
    timestamps: bool = typer.Option(True, "--timestamps/--no-timestamps", help="Include timestamps in the transcript."),
    chapters_enabled: bool = typer.Option(True, "--chapters/--no-chapters", help="Detect/infer chapters."),
    summary: bool = typer.Option(True, "--summary/--no-summary", help="Generate an executive summary and takeaways."),
    diarize: bool = typer.Option(False, "--diarize", help="Attempt speaker diarization (best-effort; omitted if unavailable)."),
    research_mode: bool = typer.Option(False, "--research-mode", help="Add a Research Mode Analysis section."),
    remove_filler_words: bool = typer.Option(False, "--remove-filler-words", help="Strip filler words (um, uh, ...)."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Path to a YAML config file."),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed logs."),
) -> None:
    """Transcribe one or more YouTube videos into transcript.md and transcript.txt."""
    config = load_config(config_path)
    config.language = language
    config.whisper_model = model
    config.prefer_captions = prefer_captions
    config.force_whisper = force_whisper
    config.timestamps = timestamps
    config.chapter_detection = chapters_enabled
    config.generate_summary = summary
    config.diarize = diarize
    config.research_mode = research_mode
    config.remove_filler_words = remove_filler_words
    config.verbose = verbose
    output_root = output

    output_root.mkdir(parents=True, exist_ok=True)

    resolved_urls = resolve_urls(list(urls), report=_console_report, verbose=config.verbose)

    successes, failures = 0, 0
    for url in resolved_urls:
        console.print()
        outcome = process_video(url, config, output_root, report=_console_report)
        if outcome.success:
            successes += 1
        else:
            failures += 1

    console.print(f"\n[bold]Done:[/bold] {successes} succeeded, {failures} failed.")
    if failures and not successes:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
