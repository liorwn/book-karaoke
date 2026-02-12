"""
Export utilities for Book Karaoke: SRT subtitles, WebVTT subtitles, and thumbnails.
"""

from pathlib import Path
from PIL import Image, ImageDraw

from .utils import find_font
from .render import TextLayout, render_frame, COLOR_BG


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    if seconds is None or seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as WebVTT timestamp: HH:MM:SS.mmm"""
    if seconds is None or seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def export_srt(chunks_with_timings: list[list[dict]], output_path: str) -> str:
    """
    Generate an SRT subtitle file from chunk timings.

    Args:
        chunks_with_timings: List of chunks, each a list of word timing dicts
                             with "word", "start", "end" keys.
        output_path: Where to write the .srt file.

    Returns:
        Path to the generated SRT file.
    """
    lines = []
    for i, chunk in enumerate(chunks_with_timings):
        if not chunk:
            continue
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["word"] for w in chunk)

        lines.append(str(i + 1))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(text)
        lines.append("")  # blank line between entries

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return output_path


def export_vtt(chunks_with_timings: list[list[dict]], output_path: str) -> str:
    """
    Generate a WebVTT subtitle file from chunk timings.

    Includes word-level timestamp cues using VTT's <HH:MM:SS.mmm> inline tags.

    Args:
        chunks_with_timings: List of chunks, each a list of word timing dicts
                             with "word", "start", "end" keys.
        output_path: Where to write the .vtt file.

    Returns:
        Path to the generated VTT file.
    """
    lines = ["WEBVTT", ""]

    for i, chunk in enumerate(chunks_with_timings):
        if not chunk:
            continue
        start = chunk[0]["start"]
        end = chunk[-1]["end"]

        lines.append(str(i + 1))
        lines.append(f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}")

        # Build text with word-level timing cues
        word_parts = []
        for w in chunk:
            ts = _format_vtt_time(w["start"])
            word_parts.append(f"<{ts}>{w['word']}")
        lines.append("".join(word_parts))
        lines.append("")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return output_path


def generate_thumbnail(
    chunks_with_timings: list[list[dict]],
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    font_size: int = 52,
) -> str:
    """
    Generate a thumbnail image showing the first chunk with karaoke styling.

    Renders the first chunk as a static image with the first word highlighted,
    suitable for social media preview images.

    Args:
        chunks_with_timings: List of chunks with word timings.
        output_path: Where to save the thumbnail image (PNG).
        width: Image width in pixels.
        height: Image height in pixels.
        font_size: Font size for the text.

    Returns:
        Path to the generated thumbnail image.
    """
    # Find the first non-empty chunk
    chunk = None
    for c in chunks_with_timings:
        if c:
            chunk = c
            break

    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    if chunk:
        font = find_font(font_size)
        layout = TextLayout(width, height, font, margin_x=80)
        chunk_words = [w["word"] for w in chunk]

        # Render with the first word highlighted (current_time = first word's start)
        render_frame(
            draw=draw,
            layout=layout,
            chunk_words=chunk_words,
            chunk_timings=chunk,
            current_time=chunk[0]["start"],
            progress=0.0,
            width=width,
            height=height,
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return output_path
