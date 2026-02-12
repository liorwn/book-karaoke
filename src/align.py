"""
Word-level alignment using local Whisper (mlx-whisper on Apple Silicon).
"""

import mlx_whisper

# Use large-v3-turbo for best quality/speed tradeoff on Apple Silicon.
# Downloaded automatically on first use and cached locally.
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def get_word_timestamps(audio_path: str, progress_callback=None) -> list[dict]:
    """
    Transcribe audio and return word-level timestamps using local Whisper.

    Args:
        audio_path: Path to the audio file (MP3, WAV, etc.).
        progress_callback: Optional callable(step, progress, message).

    Returns:
        A list of dicts, each with keys: "word", "start", "end"
        where start/end are float seconds.
    """
    print(f"[align] Transcribing {audio_path} with local Whisper for word-level timestamps...")

    if progress_callback:
        progress_callback("alignment", 0.0, "Aligning audio (local Whisper)...")

    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=DEFAULT_MODEL,
        word_timestamps=True,
    )

    words = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": float(w["start"]),
                "end": float(w["end"]),
            })

    if not words:
        raise ValueError(
            "Whisper did not return word-level timestamps. "
            "Ensure the audio file is valid and contains speech."
        )

    print(f"[align] Got timestamps for {len(words)} words")
    if words:
        total_duration = words[-1]["end"]
        print(f"[align] Audio duration (from timestamps): {total_duration:.2f}s")

    if progress_callback:
        progress_callback("alignment", 1.0, "Alignment complete")

    return words
