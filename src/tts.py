"""
TTS generation using edge-tts (Microsoft Edge's free TTS service).

No API key required, no character limit, runs locally.
For long texts, splits into chunks and reports per-chunk progress.
"""

import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path

import edge_tts

# Map short friendly names to edge-tts voice IDs
VOICE_MAP = {
    "andrew": "en-US-AndrewNeural",
    "ava": "en-US-AvaNeural",
    "brian": "en-US-BrianNeural",
    "christopher": "en-US-ChristopherNeural",
    "emma": "en-US-EmmaNeural",
    "eric": "en-US-EricNeural",
    "guy": "en-US-GuyNeural",
    "jenny": "en-US-JennyNeural",
    "roger": "en-US-RogerNeural",
    "steffan": "en-US-SteffanNeural",
}

DEFAULT_VOICE = "andrew"

# Split long text into chunks of this size for progress reporting
CHUNK_SIZE = 4000


def _resolve_voice(voice: str) -> str:
    """Resolve a friendly voice name to an edge-tts voice ID."""
    lower = voice.lower().strip()
    if lower in VOICE_MAP:
        return VOICE_MAP[lower]
    if "-" in voice and "Neural" in voice:
        return voice
    return VOICE_MAP[DEFAULT_VOICE]


def _split_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    """Split text at sentence boundaries into chunks under max_chars."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            words = sentence.split()
            for word in words:
                if len(current) + len(word) + 1 > max_chars:
                    chunks.append(current.strip())
                    current = word
                else:
                    current = f"{current} {word}" if current else word
        elif len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


MAX_RETRIES = 3


async def _generate_one(text: str, voice_id: str, output_path: str) -> None:
    """Generate a single TTS segment with retry on transient errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(text, voice_id)
            await communicate.save(output_path)
            return
        except Exception as exc:
            if attempt < MAX_RETRIES:
                wait = attempt * 2
                _log(f"[tts] Attempt {attempt} failed ({exc}), retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise


async def _generate_all(
    chunks: list[str],
    voice_id: str,
    output_path: str,
    progress_callback=None,
) -> str:
    """Generate TTS for all chunks in a single event loop."""
    total = len(chunks)

    if total == 1:
        await _generate_one(chunks[0], voice_id, output_path)
    else:
        tmp_dir = tempfile.mkdtemp(prefix="tts_segments_")
        segment_paths = []

        for i, chunk in enumerate(chunks):
            pct = i / total
            _log(f"[tts] Chunk {i + 1}/{total} ({len(chunk)} chars)...")

            if progress_callback:
                progress_callback("tts", pct, f"Generating speech ({i + 1}/{total})...")

            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp3")
            await _generate_one(chunk, voice_id, seg_path)
            segment_paths.append(seg_path)

        # Concatenate MP3 segments
        with open(output_path, "wb") as out:
            for p in segment_paths:
                out.write(Path(p).read_bytes())

        # Cleanup
        for p in segment_paths:
            os.unlink(p)
        os.rmdir(tmp_dir)

    return output_path


def _log(msg: str) -> None:
    """Print and flush immediately."""
    print(msg, flush=True)


def _run_async(coro):
    """Run an async coroutine, creating a new event loop if needed."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an existing event loop (e.g. FastAPI thread) —
        # create a fresh loop in this thread.
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    else:
        return asyncio.run(coro)


def generate_tts_segment(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
) -> str:
    """Generate TTS for a single chapter/segment. No progress callback."""
    voice_id = _resolve_voice(voice)
    chunks = _split_text(text)
    _log(f"[tts] Segment: {len(text)} chars, {len(chunks)} chunk(s)")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run_async(_generate_all(chunks, voice_id, output_path))
    return output_path


def concatenate_mp3_files(segment_paths: list[str], output_path: str) -> str:
    """Binary-append MP3 files into one. MP3 is frame-based so this is valid."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as out:
        for p in segment_paths:
            out.write(Path(p).read_bytes())
    _log(f"[tts] Concatenated {len(segment_paths)} segments -> {output_path}")
    return output_path


def generate_tts(
    text: str,
    output_path: str,
    model: str = "tts-1",
    voice: str = DEFAULT_VOICE,
    progress_callback=None,
) -> str:
    """
    Generate speech audio from text using edge-tts.

    For texts longer than CHUNK_SIZE, splits into chunks and reports
    per-chunk progress so the UI stays responsive.
    """
    voice_id = _resolve_voice(voice)
    chunks = _split_text(text)
    total = len(chunks)

    _log(f"[tts] Generating speech with edge-tts, voice={voice_id}")
    _log(f"[tts] Text length: {len(text)} chars, ~{len(text.split())} words, {total} chunk(s)")

    if progress_callback:
        progress_callback("tts", 0.0, f"Generating speech ({voice})...")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    _run_async(_generate_all(chunks, voice_id, output_path, progress_callback))

    file_size = os.path.getsize(output_path)
    _log(f"[tts] Audio saved to {output_path} ({file_size / 1024:.1f} KB)")

    if progress_callback:
        progress_callback("tts", 1.0, "Speech generated")

    return output_path
