"""
Utility functions for Book Karaoke: text chunking, font loading, and helpers.
"""

import os
import re
import platform
from pathlib import Path
from PIL import ImageFont


# ---------------------------------------------------------------------------
# Font discovery
# ---------------------------------------------------------------------------

# Ordered preference list of system fonts (macOS paths first, then Linux, then generic)
_FONT_CANDIDATES = [
    # macOS SF Pro (best for modern look)
    "/System/Library/Fonts/SFProText-Regular.otf",
    "/System/Library/Fonts/SFProDisplay-Regular.otf",
    "/System/Library/Fonts/SF-Pro-Text-Regular.otf",
    "/System/Library/Fonts/SF-Pro-Display-Regular.otf",
    # macOS Helvetica Neue
    "/System/Library/Fonts/HelveticaNeue.ttc",
    # macOS Helvetica
    "/System/Library/Fonts/Helvetica.ttc",
    # macOS Arial
    "/Library/Fonts/Arial.ttf",
    # Linux common
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

_BOLD_FONT_CANDIDATES = [
    "/System/Library/Fonts/SFProText-Bold.otf",
    "/System/Library/Fonts/SFProDisplay-Bold.otf",
    "/System/Library/Fonts/SF-Pro-Text-Bold.otf",
    "/System/Library/Fonts/SF-Pro-Display-Bold.otf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
]


def find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Find the best available system font and return it at the requested size.
    Falls back to Pillow's built-in default if nothing else works.
    """
    # Check project fonts/ directory first
    project_fonts = Path(__file__).parent.parent / "fonts"
    if project_fonts.exists():
        for f in sorted(project_fonts.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                try:
                    return ImageFont.truetype(str(f), size)
                except Exception:
                    continue

    candidates = _BOLD_FONT_CANDIDATES if bold else _FONT_CANDIDATES
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    # Last resort: Pillow default (bitmap, not pretty but functional)
    print("[warn] No system TrueType font found, using Pillow default bitmap font.")
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text chunking — splits text into display chunks of ~2-3 short lines
# ---------------------------------------------------------------------------

def strip_markdown(text: str) -> str:
    """Remove markdown formatting syntax while preserving the content.

    Handles: **bold**, *italic*, __bold__, _italic_, # headings,
    > blockquotes, - list items, [links](url), ![images](url),
    ~~strikethrough~~, `inline code`, ``` code blocks ```
    """
    # Remove code blocks (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code (`...`)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Remove links [text](url) — keep the text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Remove bold/italic markers (order matters: ** before *)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"___(.+?)___", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    # Remove heading markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove blockquote markers
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Remove list markers (-, *, numbered)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    return text


def extract_formatting(text: str) -> dict[str, str]:
    """Extract a map of word -> formatting style from markdown text.

    Returns a dict where keys are lowercase words and values are CSS-style
    format strings: 'bold', 'italic', or 'bold-italic'.
    Words not in the dict have no special formatting.
    """
    fmt = {}

    # Bold+italic ***word*** or ___word___
    for m in re.finditer(r"\*\*\*(.+?)\*\*\*|___(.+?)___", text):
        content = m.group(1) or m.group(2)
        for w in content.split():
            fmt[re.sub(r"[^a-zA-Z0-9']", "", w).lower()] = "bold-italic"

    # Bold **word** or __word__
    for m in re.finditer(r"\*\*(.+?)\*\*|__(.+?)__", text):
        content = m.group(1) or m.group(2)
        for w in content.split():
            key = re.sub(r"[^a-zA-Z0-9']", "", w).lower()
            if key not in fmt:
                fmt[key] = "bold"

    # Italic *word* or _word_
    for m in re.finditer(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!\w)_(.+?)_(?!\w)", text):
        content = m.group(1) or m.group(2)
        for w in content.split():
            key = re.sub(r"[^a-zA-Z0-9']", "", w).lower()
            if key not in fmt:
                fmt[key] = "italic"

    return fmt


def clean_text(text: str) -> str:
    """Normalize whitespace, strip markdown syntax, and clean the text."""
    text = text.strip()
    # Strip markdown formatting
    text = strip_markdown(text)
    # Normalize various dash types to standard em-dash
    text = text.replace("—", " -- ")
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences. Handles common abbreviations and quoted speech.
    Returns a list of sentence strings (with trailing space stripped).
    """
    # Simple sentence boundary detection
    # Split on period/question/exclamation followed by space and uppercase, or end of string
    # But be careful with quotes
    sentences = []
    current = []
    words = text.split()

    for i, word in enumerate(words):
        current.append(word)
        # Check if this word ends a sentence
        stripped = word.rstrip('"').rstrip("'").rstrip("\u201d").rstrip("\u2019")
        if stripped and stripped[-1] in ".?!":
            # Check if next word starts with uppercase or we're at the end
            if i == len(words) - 1:
                sentences.append(" ".join(current))
                current = []
            elif i + 1 < len(words):
                next_word = words[i + 1]
                # Strip opening quotes
                next_clean = next_word.lstrip('"').lstrip("'").lstrip("\u201c").lstrip("\u2018")
                if next_clean and (next_clean[0].isupper() or next_clean[0] == "\u201c"):
                    sentences.append(" ".join(current))
                    current = []

    if current:
        sentences.append(" ".join(current))

    return sentences


def chunk_text(text: str, max_words_per_chunk: int = 20) -> list[str]:
    """
    Split text into display chunks suitable for karaoke rendering.
    Each chunk is roughly 2-3 lines of text (targeting max_words_per_chunk words).
    Tries to break on sentence boundaries first, then on natural phrase breaks.
    """
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk_words = []

    for sentence in sentences:
        sentence_words = sentence.split()

        # If adding this sentence would exceed the limit, flush current chunk
        if current_chunk_words and len(current_chunk_words) + len(sentence_words) > max_words_per_chunk:
            chunks.append(" ".join(current_chunk_words))
            current_chunk_words = []

        # If the sentence itself is too long, split it at phrase boundaries
        if len(sentence_words) > max_words_per_chunk:
            # Split on commas, semicolons, dashes, or conjunctions
            phrase_break_words = []
            for w in sentence_words:
                phrase_break_words.append(w)
                if len(phrase_break_words) >= max_words_per_chunk:
                    # Look for a natural break point near the end
                    best_break = len(phrase_break_words)
                    for j in range(len(phrase_break_words) - 1, max(0, len(phrase_break_words) - 6), -1):
                        pw = phrase_break_words[j]
                        if pw.endswith(",") or pw.endswith(";") or pw.endswith("--") or pw.lower() in ("and", "but", "or", "then"):
                            best_break = j + 1
                            break
                    if current_chunk_words:
                        chunks.append(" ".join(current_chunk_words))
                        current_chunk_words = []
                    chunks.append(" ".join(phrase_break_words[:best_break]))
                    phrase_break_words = phrase_break_words[best_break:]

            if phrase_break_words:
                current_chunk_words.extend(phrase_break_words)
        else:
            current_chunk_words.extend(sentence_words)

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    return chunks


# ---------------------------------------------------------------------------
# Word mapping helpers
# ---------------------------------------------------------------------------

def normalize_word(word: str) -> str:
    """Strip punctuation for matching purposes."""
    return re.sub(r"[^a-zA-Z0-9']", "", word).lower()


def map_whisper_words_to_chunks(
    chunks: list[str],
    whisper_words: list[dict],
) -> list[list[dict]]:
    """
    Map Whisper's word-level timestamps to our display chunks.

    Each chunk is a string of words. We match Whisper words sequentially to
    chunk words using normalized comparison. Returns a list (one per chunk)
    of lists of word-timing dicts: {"word": str, "start": float, "end": float}.
    """
    chunk_timings = []
    whisper_idx = 0

    for chunk in chunks:
        chunk_words = chunk.split()
        timings = []

        for cw in chunk_words:
            cw_norm = normalize_word(cw)
            if not cw_norm:
                # Punctuation-only token — give it the timing of the next real word
                timings.append({"word": cw, "start": None, "end": None})
                continue

            # Find the matching Whisper word
            matched = False
            search_limit = min(whisper_idx + 10, len(whisper_words))
            for j in range(whisper_idx, search_limit):
                ww = whisper_words[j]
                ww_norm = normalize_word(ww.get("word", ""))
                if ww_norm == cw_norm or cw_norm.startswith(ww_norm) or ww_norm.startswith(cw_norm):
                    timings.append({
                        "word": cw,
                        "start": ww.get("start", 0.0),
                        "end": ww.get("end", 0.0),
                    })
                    whisper_idx = j + 1
                    matched = True
                    break

            if not matched:
                # Fallback: assign interpolated timing
                if timings and timings[-1]["start"] is not None:
                    last_end = timings[-1]["end"]
                    timings.append({"word": cw, "start": last_end, "end": last_end + 0.2})
                elif whisper_idx < len(whisper_words):
                    ww = whisper_words[whisper_idx]
                    timings.append({
                        "word": cw,
                        "start": ww.get("start", 0.0),
                        "end": ww.get("end", 0.0),
                    })
                    whisper_idx += 1
                else:
                    timings.append({"word": cw, "start": 0.0, "end": 0.0})

        # Fill in None timings (punctuation-only tokens)
        for i, t in enumerate(timings):
            if t["start"] is None:
                if i + 1 < len(timings) and timings[i + 1]["start"] is not None:
                    t["start"] = timings[i + 1]["start"]
                    t["end"] = timings[i + 1]["start"]
                elif i > 0:
                    t["start"] = timings[i - 1]["end"]
                    t["end"] = timings[i - 1]["end"]
                else:
                    t["start"] = 0.0
                    t["end"] = 0.0

        chunk_timings.append(timings)

    return chunk_timings


def chunk_text_with_chapters(
    chapters: list[dict],
    max_words_per_chunk: int = 20,
) -> tuple[list[str], list[dict]]:
    """Chunk text respecting chapter boundaries.

    Parameters
    ----------
    chapters : list[dict]
        Each dict has ``"title"`` and ``"text"`` keys.
    max_words_per_chunk : int
        Maximum words per display chunk.

    Returns
    -------
    (flat_chunks, chapter_ranges) where *flat_chunks* is a single list of
    chunk strings and *chapter_ranges* is a list of dicts with keys
    ``title``, ``start_chunk``, ``end_chunk``, ``word_count``.
    Chunks never cross chapter boundaries.
    """
    flat_chunks: list[str] = []
    chapter_ranges: list[dict] = []

    for ch in chapters:
        title = ch.get("title", "")
        text = ch.get("text", "").strip()
        if not text:
            continue

        start_idx = len(flat_chunks)
        ch_chunks = chunk_text(text, max_words_per_chunk=max_words_per_chunk)
        flat_chunks.extend(ch_chunks)
        end_idx = len(flat_chunks) - 1

        word_count = len(text.split())
        chapter_ranges.append({
            "title": title,
            "start_chunk": start_idx,
            "end_chunk": end_idx,
            "word_count": word_count,
        })

    return flat_chunks, chapter_ranges


def get_audio_duration_seconds(audio_path: str) -> float:
    """Get the duration of an audio file in seconds using ffprobe."""
    import subprocess
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())
