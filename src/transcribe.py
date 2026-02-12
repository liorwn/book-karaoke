"""
Audio transcription using local Whisper (mlx-whisper on Apple Silicon).
"""

from pathlib import Path

import mlx_whisper

# Same model as align.py for consistency
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def transcribe_audio(audio_path: str, progress_callback=None) -> str:
    """
    Transcribe audio file to text using local Whisper.

    Args:
        audio_path: Path to the audio file (MP3, WAV, etc.).
        progress_callback: Optional callable(status_str) for progress updates.

    Returns:
        The transcribed text as a string.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    file_size = path.stat().st_size

    def _report(msg: str):
        print(f"[transcribe] {msg}")
        if progress_callback:
            progress_callback(msg)

    _report(f"Transcribing {audio_path} ({file_size / 1024:.1f} KB) with local Whisper...")

    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=DEFAULT_MODEL,
    )

    text = result.get("text", "").strip()

    word_count = len(text.split())
    _report(f"Transcription complete: {word_count} words")

    return text
