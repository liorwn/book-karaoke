"""
Core pipeline orchestration for Book Karaoke.

Supports three input modes:
  - "text":           text file -> TTS -> align -> (optional) render
  - "audio":          audio file -> transcribe -> align -> (optional) render
  - "text_and_audio": text + audio -> align -> (optional) render
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import KaraokeSettings
from .tts import generate_tts
from .align import get_word_timestamps
from .transcribe import transcribe_audio
from .render import render_video
from .utils import clean_text, chunk_text, map_whisper_words_to_chunks, get_audio_duration_seconds, extract_formatting


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Everything produced by a pipeline run."""

    text: str
    audio_path: str
    chunks: list[str]
    chunks_with_timings: list[list[dict]]
    formatting: dict = None
    video_path: Optional[str] = None
    duration: float = 0.0


# Type alias for the progress callback.
# signature: callback(step: str, progress: float, message: str)
ProgressCallback = Callable[[str, float, str], None]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """Orchestrates the full Book Karaoke workflow.

    Parameters
    ----------
    settings : KaraokeSettings
        All configurable parameters (TTS voice, resolution, colors, etc.).
    text_path : str | None
        Path to a plain-text input file (required for "text" and "text_and_audio" modes).
    audio_path : str | None
        Path to an existing audio file (required for "audio" and "text_and_audio" modes).
    output_path : str | None
        Where to write the rendered video. If *None*, video rendering is skipped.
    progress_callback : ProgressCallback | None
        Optional ``(step, progress, message)`` callable for UI progress updates.
    """

    def __init__(
        self,
        settings: KaraokeSettings,
        text_path: Optional[str] = None,
        audio_path: Optional[str] = None,
        output_path: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.settings = settings
        self.text_path = text_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.progress_callback = progress_callback

        self._validate_inputs()

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def _validate_inputs(self) -> None:
        mode = self.settings.input_mode

        if mode == "text":
            if not self.text_path:
                raise ValueError("input_mode='text' requires text_path")
            if not Path(self.text_path).exists():
                raise FileNotFoundError(f"Text file not found: {self.text_path}")

        elif mode == "audio":
            if not self.audio_path:
                raise ValueError("input_mode='audio' requires audio_path")
            if not Path(self.audio_path).exists():
                raise FileNotFoundError(f"Audio file not found: {self.audio_path}")

        elif mode == "text_and_audio":
            if not self.text_path:
                raise ValueError("input_mode='text_and_audio' requires text_path")
            if not self.audio_path:
                raise ValueError("input_mode='text_and_audio' requires audio_path")
            if not Path(self.text_path).exists():
                raise FileNotFoundError(f"Text file not found: {self.text_path}")
            if not Path(self.audio_path).exists():
                raise FileNotFoundError(f"Audio file not found: {self.audio_path}")

        else:
            raise ValueError(
                f"Unknown input_mode {mode!r}. Expected 'text', 'audio', or 'text_and_audio'."
            )

    # ------------------------------------------------------------------
    # Progress helper
    # ------------------------------------------------------------------

    def _progress(self, step: str, progress: float, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(step, progress, message)

    # ------------------------------------------------------------------
    # Individual step methods
    # ------------------------------------------------------------------

    def read_text(self) -> str:
        """Read and clean the text file. Returns the cleaned text.

        Also stores ``self._raw_text`` for formatting extraction.
        """
        self._progress("read_text", 0.0, "Reading text file...")

        path = Path(self.text_path)
        ext = path.suffix.lower()

        # Handle PDF files
        if ext == ".pdf":
            raw = self._read_pdf(path)
        # Handle epub files
        elif ext == ".epub":
            raw = self._read_epub(path)
        else:
            # Try UTF-8 first, fall back to latin-1 (which accepts any byte)
            try:
                raw = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = path.read_text(encoding="latin-1")

        self._raw_text = raw
        text = clean_text(raw)

        word_count = len(text.split())
        self._progress("read_text", 1.0, f"Read {word_count} words")
        return text

    @staticmethod
    def _read_pdf(path: Path) -> str:
        """Extract text from a PDF using pdftotext or fallback."""
        import subprocess
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdftotext failed: {result.stderr.strip()}")
        return result.stdout

    @staticmethod
    def _read_epub(path: Path) -> str:
        """Extract text from an epub by reading the XHTML content files."""
        import zipfile
        import re
        texts = []
        with zipfile.ZipFile(str(path), "r") as zf:
            for name in zf.namelist():
                if name.endswith((".xhtml", ".html", ".htm")):
                    html = zf.read(name).decode("utf-8", errors="replace")
                    # Strip HTML tags
                    clean = re.sub(r"<[^>]+>", " ", html)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    if clean:
                        texts.append(clean)
        if not texts:
            raise ValueError("No readable text found in epub file")
        return "\n\n".join(texts)

    def generate_audio(self, text: str, audio_output_path: str) -> str:
        """Run TTS to produce an audio file. Returns the audio path."""
        self._progress("tts", 0.0, f"Generating TTS (voice={self.settings.voice})...")

        # Use the already-read text (which handled encoding/PDF/epub).
        raw_text = text.strip()

        result_path = generate_tts(
            text=raw_text,
            output_path=audio_output_path,
            model=self.settings.model,
            voice=self.settings.voice,
            progress_callback=self.progress_callback,
        )

        self._progress("tts", 1.0, "TTS complete")
        return result_path

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text via Whisper. Returns the text."""
        self._progress("transcribe", 0.0, "Transcribing audio...")

        text = transcribe_audio(audio_path)

        word_count = len(text.split())
        self._progress("transcribe", 1.0, f"Transcribed {word_count} words")
        return text

    def align(self, audio_path: str) -> list[dict]:
        """Get word-level timestamps from audio via Whisper. Returns word list."""
        self._progress("align", 0.0, "Aligning words to audio...")

        whisper_words = get_word_timestamps(audio_path)

        self._progress("align", 1.0, f"Aligned {len(whisper_words)} words")
        return whisper_words

    def build_chunks(self, text: str, whisper_words: list[dict]) -> tuple[list[str], list[list[dict]]]:
        """Chunk text and map Whisper timestamps to chunks.

        Returns (chunks, chunks_with_timings).
        """
        self._progress("chunk", 0.0, "Building display chunks...")

        chunks = chunk_text(text, max_words_per_chunk=self.settings.max_words_per_chunk)
        chunks_with_timings = map_whisper_words_to_chunks(chunks, whisper_words)

        self._progress("chunk", 1.0, f"Created {len(chunks)} chunks")
        return chunks, chunks_with_timings

    def render(self, chunks_with_timings: list[list[dict]], audio_path: str) -> str:
        """Render the karaoke video. Returns the output video path."""
        if not self.output_path:
            raise ValueError("No output_path specified; cannot render video.")

        self._progress("render", 0.0, "Rendering video...")

        video_path = render_video(
            chunk_timings=chunks_with_timings,
            audio_path=audio_path,
            output_path=self.output_path,
            width=self.settings.width,
            height=self.settings.height,
            fps=self.settings.fps,
            font_size=self.settings.font_size,
            settings=self.settings,
            progress_callback=self.progress_callback,
        )

        self._progress("render", 1.0, "Video rendered")
        return video_path

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """Execute the full pipeline based on ``settings.input_mode``.

        Returns a :class:`PipelineResult` with all outputs.
        """
        mode = self.settings.input_mode
        t0 = time.time()

        # -- Acquire text and audio ----------------------------------------

        if mode == "text":
            # text -> TTS -> align -> render
            text = self.read_text()

            # Determine where to write the generated audio
            if self.output_path:
                audio_dir = str(Path(self.output_path).parent)
            else:
                audio_dir = str(Path(self.text_path).parent)
            audio_path = str(Path(audio_dir) / "audio.mp3")

            self.generate_audio(text, audio_path)

        elif mode == "audio":
            # audio -> transcribe -> align -> render
            audio_path = self.audio_path
            text = self.transcribe(audio_path)

        elif mode == "text_and_audio":
            # text + audio -> align (skip TTS) -> render
            text = self.read_text()
            audio_path = self.audio_path

        # -- Align ---------------------------------------------------------

        whisper_words = self.align(audio_path)

        # -- Chunk and map -------------------------------------------------

        chunks, chunks_with_timings = self.build_chunks(text, whisper_words)

        # -- Audio duration ------------------------------------------------

        duration = get_audio_duration_seconds(audio_path)

        # -- Render (optional) ---------------------------------------------

        video_path = None
        if self.output_path:
            video_path = self.render(chunks_with_timings, audio_path)

        elapsed = time.time() - t0
        self._progress("done", 1.0, f"Pipeline complete in {elapsed:.1f}s")

        # -- Formatting map ------------------------------------------------
        formatting = {}
        if hasattr(self, "_raw_text") and self._raw_text:
            formatting = extract_formatting(self._raw_text)

        return PipelineResult(
            text=text,
            audio_path=audio_path,
            chunks=chunks,
            chunks_with_timings=chunks_with_timings,
            formatting=formatting,
            video_path=video_path,
            duration=duration,
        )
