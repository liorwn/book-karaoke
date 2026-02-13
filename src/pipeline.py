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
from .tts import generate_tts, generate_tts_segment, concatenate_mp3_files
from .align import get_word_timestamps
from .transcribe import transcribe_audio
from .render import render_video
from .utils import (
    clean_text, chunk_text, chunk_text_with_chapters,
    map_whisper_words_to_chunks, get_audio_duration_seconds,
    extract_formatting, split_text_into_segments, split_audio_file,
)

# Texts at or above this word count use per-chapter TTS + alignment
CHAPTER_PROCESSING_THRESHOLD = 5000

# Audio files longer than this (seconds) get split for chunked transcription/alignment
AUDIO_CHUNK_DURATION = 600  # 10 minutes


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
    chapters: Optional[list[dict]] = None
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
        self._epub_chapters = None

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

    def _read_epub(self, path: Path) -> str:
        """Extract text from an epub, preserving chapter structure.

        Stores ``self._epub_chapters`` as a side effect for chapter-aware
        chunking later in the pipeline.
        """
        chapters = self._read_epub_chapters(path)
        if not chapters:
            raise ValueError("No readable text found in epub file")
        self._epub_chapters = chapters
        return "\n\n".join(ch["text"] for ch in chapters)

    @staticmethod
    def _read_epub_chapters(path: Path) -> list[dict]:
        """Extract chapters from an EPUB with titles and text.

        Returns a list of ``{"title": str, "text": str}`` dicts in spine
        reading order.  Filters out very short entries (<30 words) such as
        cover pages and copyright notices.
        """
        import zipfile
        import re
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(str(path), "r") as zf:
            # --- locate OPF via container.xml ---
            try:
                container_xml = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
                container_root = ET.fromstring(container_xml)
                ns_container = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
                rootfile_el = container_root.find(".//c:rootfile", ns_container)
                opf_path = rootfile_el.attrib["full-path"] if rootfile_el is not None else None
            except Exception:
                opf_path = None

            # Fallback: find .opf by scanning namelist
            if not opf_path:
                for name in zf.namelist():
                    if name.endswith(".opf"):
                        opf_path = name
                        break
            if not opf_path:
                # Last resort: read all xhtml files in order
                return Pipeline._read_epub_flat(zf)

            opf_dir = str(Path(opf_path).parent)
            if opf_dir == ".":
                opf_dir = ""

            # --- parse OPF manifest + spine ---
            opf_xml = zf.read(opf_path).decode("utf-8", errors="replace")
            opf_root = ET.fromstring(opf_xml)

            # Detect default namespace
            opf_ns = ""
            m = re.match(r"\{(.+?)\}", opf_root.tag)
            if m:
                opf_ns = m.group(1)
            ns = {"opf": opf_ns} if opf_ns else {}

            def _find(parent, tag):
                if ns:
                    return parent.findall(f"opf:{tag}", ns)
                return parent.findall(tag)

            # Build id->href manifest map
            manifest_el = opf_root.find(f"{{{opf_ns}}}manifest" if opf_ns else "manifest")
            id_to_href: dict[str, str] = {}
            if manifest_el is not None:
                for item in _find(manifest_el, "item"):
                    item_id = item.attrib.get("id", "")
                    href = item.attrib.get("href", "")
                    if item_id and href:
                        id_to_href[item_id] = href

            # Spine reading order
            spine_el = opf_root.find(f"{{{opf_ns}}}spine" if opf_ns else "spine")
            spine_hrefs: list[str] = []
            if spine_el is not None:
                for itemref in _find(spine_el, "itemref"):
                    idref = itemref.attrib.get("idref", "")
                    if idref in id_to_href:
                        href = id_to_href[idref]
                        full = f"{opf_dir}/{href}" if opf_dir else href
                        spine_hrefs.append(full)

            if not spine_hrefs:
                return Pipeline._read_epub_flat(zf)

            # --- extract TOC titles ---
            toc_titles = Pipeline._extract_toc_titles(zf, opf_root, opf_ns, opf_dir, ns)

            # --- read each spine file ---
            chapters: list[dict] = []
            for href in spine_hrefs:
                # Normalise path separators
                href_norm = href.replace("\\", "/")
                try:
                    html = zf.read(href_norm).decode("utf-8", errors="replace")
                except KeyError:
                    continue

                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()

                if len(text.split()) < 30:
                    continue

                # Try to find a title from TOC, else derive from filename
                basename = Path(href_norm).stem
                title = toc_titles.get(href_norm) or toc_titles.get(basename) or basename.replace("-", " ").replace("_", " ").title()

                chapters.append({"title": title, "text": text})

            return chapters if chapters else Pipeline._read_epub_flat(zf)

    @staticmethod
    def _read_epub_flat(zf) -> list[dict]:
        """Fallback: read all xhtml files without chapter metadata."""
        import re
        chapters = []
        for name in sorted(zf.namelist()):
            if name.endswith((".xhtml", ".html", ".htm")):
                html = zf.read(name).decode("utf-8", errors="replace")
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()
                if text and len(text.split()) >= 30:
                    stem = Path(name).stem
                    title = stem.replace("-", " ").replace("_", " ").title()
                    chapters.append({"title": title, "text": text})
        return chapters

    @staticmethod
    def _extract_toc_titles(zf, opf_root, opf_ns, opf_dir, ns) -> dict[str, str]:
        """Extract href->title map from toc.ncx (EPUB2) or nav.xhtml (EPUB3)."""
        import re
        import xml.etree.ElementTree as ET

        titles: dict[str, str] = {}

        # --- Try toc.ncx (EPUB2) ---
        def _find_opf(parent, tag):
            if ns:
                return parent.findall(f"opf:{tag}", ns)
            return parent.findall(tag)

        manifest_el = opf_root.find(f"{{{opf_ns}}}manifest" if opf_ns else "manifest")
        ncx_path = None
        nav_path = None
        if manifest_el is not None:
            for item in _find_opf(manifest_el, "item"):
                href = item.attrib.get("href", "")
                media = item.attrib.get("media-type", "")
                props = item.attrib.get("properties", "")
                if media == "application/x-dtbncx+xml":
                    ncx_path = f"{opf_dir}/{href}" if opf_dir else href
                if "nav" in props:
                    nav_path = f"{opf_dir}/{href}" if opf_dir else href

        # EPUB2: toc.ncx
        if ncx_path:
            try:
                ncx_xml = zf.read(ncx_path).decode("utf-8", errors="replace")
                ncx_root = ET.fromstring(ncx_xml)
                ncx_ns_match = re.match(r"\{(.+?)\}", ncx_root.tag)
                ncx_ns = ncx_ns_match.group(1) if ncx_ns_match else ""

                for nav_point in ncx_root.iter(f"{{{ncx_ns}}}navPoint" if ncx_ns else "navPoint"):
                    text_el = nav_point.find(f"{{{ncx_ns}}}navLabel/{{{ncx_ns}}}text" if ncx_ns else "navLabel/text")
                    content_el = nav_point.find(f"{{{ncx_ns}}}content" if ncx_ns else "content")
                    if text_el is not None and content_el is not None and text_el.text:
                        src = content_el.attrib.get("src", "")
                        # Strip fragment
                        src = src.split("#")[0]
                        full = f"{opf_dir}/{src}" if opf_dir else src
                        titles[full] = text_el.text.strip()
                        # Also store by basename for fuzzy matching
                        titles[Path(full).stem] = text_el.text.strip()
            except Exception:
                pass

        # EPUB3: nav.xhtml
        if nav_path and not titles:
            try:
                nav_html = zf.read(nav_path).decode("utf-8", errors="replace")
                # Simple regex extraction of <a href="...">Title</a> from nav
                for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', nav_html, re.DOTALL):
                    href = m.group(1).split("#")[0]
                    title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                    if title:
                        full = f"{opf_dir}/{href}" if opf_dir else href
                        titles[full] = title
                        titles[Path(full).stem] = title
            except Exception:
                pass

        return titles

    # ------------------------------------------------------------------
    # Per-chapter processing (long texts)
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_chapter_processing(text: str) -> bool:
        return len(text.split()) >= CHAPTER_PROCESSING_THRESHOLD

    def _ensure_chapters(self, text: str) -> list[dict]:
        """Return chapter list, auto-segmenting plain text if needed."""
        if self._epub_chapters:
            return self._epub_chapters
        chapters = split_text_into_segments(text)
        # Store so build_chunks uses chapter-aware chunking
        self._epub_chapters = chapters
        return chapters

    def _run_chapter_pipeline(self, text: str, audio_dir: str) -> PipelineResult:
        """TTS + align each chapter independently, then merge."""
        t0 = time.time()
        chapters = self._ensure_chapters(text)
        total_ch = len(chapters)

        all_whisper_words: list[dict] = []
        segment_paths: list[str] = []
        cumulative_offset = 0.0

        for i, ch in enumerate(chapters):
            ch_label = ch.get("title", f"Chapter {i + 1}")
            ch_text = ch["text"].strip()
            if not ch_text:
                continue

            # --- TTS for this chapter ---
            self._progress(
                "tts",
                i / total_ch,
                f"Generating speech: {ch_label} ({i + 1}/{total_ch})",
            )
            seg_path = str(Path(audio_dir) / f"chapter_{i:03d}.mp3")
            generate_tts_segment(ch_text, seg_path, voice=self.settings.voice)
            segment_paths.append(seg_path)

            # --- Align this chapter ---
            self._progress(
                "align",
                i / total_ch,
                f"Aligning: {ch_label} ({i + 1}/{total_ch})",
            )
            ch_words = get_word_timestamps(seg_path)

            # Offset timestamps by cumulative prior duration
            for w in ch_words:
                w["start"] += cumulative_offset
                w["end"] += cumulative_offset
            all_whisper_words.extend(ch_words)

            # Use ffprobe for exact MP3 duration (includes trailing silence)
            ch_duration = get_audio_duration_seconds(seg_path)
            cumulative_offset += ch_duration

        self._progress("tts", 1.0, "Speech generated")
        self._progress("align", 1.0, f"Aligned {len(all_whisper_words)} words")

        # --- Concatenate chapter audio files ---
        final_audio = str(Path(audio_dir) / "audio.mp3")
        concatenate_mp3_files(segment_paths, final_audio)

        # --- Chunk and map (same as single-pass) ---
        chunks, chunks_with_timings = self.build_chunks(text, all_whisper_words)

        duration = get_audio_duration_seconds(final_audio)

        # --- Render (optional) ---
        video_path = None
        if self.output_path:
            video_path = self.render(chunks_with_timings, final_audio)

        elapsed = time.time() - t0
        self._progress("done", 1.0, f"Pipeline complete in {elapsed:.1f}s")

        # --- Formatting ---
        formatting = {}
        if hasattr(self, "_raw_text") and self._raw_text:
            formatting = extract_formatting(self._raw_text)

        # --- Chapter timestamps ---
        ch_timestamps = None
        if self._chapter_ranges:
            ch_timestamps = []
            for cr in self._chapter_ranges:
                start_chunk = cr["start_chunk"]
                end_chunk = cr["end_chunk"]
                start_time = 0.0
                if start_chunk < len(chunks_with_timings) and chunks_with_timings[start_chunk]:
                    start_time = chunks_with_timings[start_chunk][0].get("start", 0.0)
                end_time = duration
                if end_chunk < len(chunks_with_timings) and chunks_with_timings[end_chunk]:
                    end_time = chunks_with_timings[end_chunk][-1].get("end", duration)
                ch_timestamps.append({
                    "title": cr["title"],
                    "start_chunk": start_chunk,
                    "end_chunk": end_chunk,
                    "start_time": start_time,
                    "end_time": end_time,
                    "word_count": cr["word_count"],
                })

        return PipelineResult(
            text=text,
            audio_path=final_audio,
            chunks=chunks,
            chunks_with_timings=chunks_with_timings,
            formatting=formatting,
            chapters=ch_timestamps,
            video_path=video_path,
            duration=duration,
        )

    # ------------------------------------------------------------------
    # Chunked audio processing (long audio uploads)
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_audio_chunking(audio_path: str) -> bool:
        """Return True if the audio file is long enough to require chunked processing."""
        try:
            duration = get_audio_duration_seconds(audio_path)
            print(f"[pipeline] Audio duration: {duration:.1f}s, chunk threshold: {AUDIO_CHUNK_DURATION}s, chunking: {duration > AUDIO_CHUNK_DURATION}")
            return duration > AUDIO_CHUNK_DURATION
        except Exception as e:
            print(f"[pipeline] WARNING: Could not determine audio duration ({e}), falling back to single-pass")
            return False

    def _run_chunked_audio_pipeline(self, audio_path: str, text: str | None = None) -> PipelineResult:
        """Transcribe/align long audio in segments to avoid Whisper OOM.

        Parameters
        ----------
        audio_path : str
            Path to the original (full) audio file.
        text : str | None
            If provided (text_and_audio mode), skip transcription and only
            align each segment.  If *None* (audio mode), transcribe each
            segment and merge the text.
        """
        t0 = time.time()
        work_dir = str(Path(audio_path).parent)

        # --- Split audio into segments ---
        self._progress("split", 0.0, "Splitting audio into segments...")
        segments = split_audio_file(audio_path, work_dir, segment_duration=AUDIO_CHUNK_DURATION)
        total_seg = len(segments)
        self._progress("split", 1.0, f"Split into {total_seg} segments")

        all_whisper_words: list[dict] = []
        transcribed_parts: list[str] = []
        cumulative_offset = 0.0

        for i, seg_path in enumerate(segments):
            seg_label = f"Segment {i + 1}"

            if text is None:
                # Audio-only: single Whisper call for both text + word timestamps
                self._progress(
                    "transcribe",
                    i / total_seg,
                    f"Transcribing & aligning: {seg_label} ({i + 1}/{total_seg})",
                )
                import mlx_whisper
                result = mlx_whisper.transcribe(
                    seg_path,
                    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
                    word_timestamps=True,
                )
                seg_text = result.get("text", "").strip()
                transcribed_parts.append(seg_text)

                seg_words = []
                for segment in result.get("segments", []):
                    for w in segment.get("words", []):
                        seg_words.append({
                            "word": w["word"].strip(),
                            "start": float(w["start"]),
                            "end": float(w["end"]),
                        })
                print(f"[pipeline] {seg_label}: {len(seg_text.split())} words transcribed, {len(seg_words)} word timestamps")
            else:
                # Text+audio: only need alignment
                self._progress(
                    "align",
                    i / total_seg,
                    f"Aligning: {seg_label} ({i + 1}/{total_seg})",
                )
                seg_words = get_word_timestamps(seg_path)

            # Offset timestamps by cumulative prior duration
            for w in seg_words:
                w["start"] += cumulative_offset
                w["end"] += cumulative_offset
            all_whisper_words.extend(seg_words)

            seg_duration = get_audio_duration_seconds(seg_path)
            cumulative_offset += seg_duration

        if text is None:
            self._progress("transcribe", 1.0, f"Transcribed {len(all_whisper_words)} words")
        self._progress("align", 1.0, f"Aligned {len(all_whisper_words)} words")

        # --- Merge text ---
        if text is None:
            text = " ".join(transcribed_parts)

        # --- Auto-generate chapter segments for chapter-aware chunking ---
        self._epub_chapters = [
            {"title": f"Section {i + 1}", "text": part}
            for i, part in enumerate(transcribed_parts)
        ] if transcribed_parts else None

        # --- Chunk and map ---
        chunks, chunks_with_timings = self.build_chunks(text, all_whisper_words)

        duration = get_audio_duration_seconds(audio_path)

        # --- Render (optional) ---
        video_path = None
        if self.output_path:
            video_path = self.render(chunks_with_timings, audio_path)

        elapsed = time.time() - t0
        self._progress("done", 1.0, f"Pipeline complete in {elapsed:.1f}s")

        # --- Formatting ---
        formatting = {}
        if hasattr(self, "_raw_text") and self._raw_text:
            formatting = extract_formatting(self._raw_text)

        # --- Chapter timestamps ---
        ch_timestamps = None
        if self._chapter_ranges:
            ch_timestamps = []
            for cr in self._chapter_ranges:
                start_chunk = cr["start_chunk"]
                end_chunk = cr["end_chunk"]
                start_time = 0.0
                if start_chunk < len(chunks_with_timings) and chunks_with_timings[start_chunk]:
                    start_time = chunks_with_timings[start_chunk][0].get("start", 0.0)
                end_time = duration
                if end_chunk < len(chunks_with_timings) and chunks_with_timings[end_chunk]:
                    end_time = chunks_with_timings[end_chunk][-1].get("end", duration)
                ch_timestamps.append({
                    "title": cr["title"],
                    "start_chunk": start_chunk,
                    "end_chunk": end_chunk,
                    "start_time": start_time,
                    "end_time": end_time,
                    "word_count": cr["word_count"],
                })

        return PipelineResult(
            text=text,
            audio_path=audio_path,  # Original file — no concatenation needed
            chunks=chunks,
            chunks_with_timings=chunks_with_timings,
            formatting=formatting,
            chapters=ch_timestamps,
            video_path=video_path,
            duration=duration,
        )

    # ------------------------------------------------------------------
    # Individual step methods
    # ------------------------------------------------------------------

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

        if self._epub_chapters:
            chunks, self._chapter_ranges = chunk_text_with_chapters(
                self._epub_chapters,
                max_words_per_chunk=self.settings.max_words_per_chunk,
            )
        else:
            chunks = chunk_text(text, max_words_per_chunk=self.settings.max_words_per_chunk)
            self._chapter_ranges = None

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

            # Long texts: per-chapter TTS + alignment to avoid OOM
            if self._needs_chapter_processing(text):
                return self._run_chapter_pipeline(text, audio_dir)

            audio_path = str(Path(audio_dir) / "audio.mp3")

            self.generate_audio(text, audio_path)

        elif mode == "audio":
            # audio -> transcribe -> align -> render
            audio_path = self.audio_path
            print(f"[pipeline] Audio mode: {audio_path}")
            if self._needs_audio_chunking(audio_path):
                return self._run_chunked_audio_pipeline(audio_path, text=None)
            text = self.transcribe(audio_path)

        elif mode == "text_and_audio":
            # text + audio -> align (skip TTS) -> render
            text = self.read_text()
            audio_path = self.audio_path
            if self._needs_audio_chunking(audio_path):
                return self._run_chunked_audio_pipeline(audio_path, text=text)

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

        # -- Chapter timestamps --------------------------------------------
        chapters = None
        if self._chapter_ranges:
            chapters = []
            for cr in self._chapter_ranges:
                start_chunk = cr["start_chunk"]
                end_chunk = cr["end_chunk"]
                # First word of first chunk in chapter
                start_time = 0.0
                if start_chunk < len(chunks_with_timings) and chunks_with_timings[start_chunk]:
                    start_time = chunks_with_timings[start_chunk][0].get("start", 0.0)
                # Last word of last chunk in chapter
                end_time = duration
                if end_chunk < len(chunks_with_timings) and chunks_with_timings[end_chunk]:
                    end_time = chunks_with_timings[end_chunk][-1].get("end", duration)
                chapters.append({
                    "title": cr["title"],
                    "start_chunk": start_chunk,
                    "end_chunk": end_chunk,
                    "start_time": start_time,
                    "end_time": end_time,
                    "word_count": cr["word_count"],
                })

        return PipelineResult(
            text=text,
            audio_path=audio_path,
            chunks=chunks,
            chunks_with_timings=chunks_with_timings,
            formatting=formatting,
            chapters=chapters,
            video_path=video_path,
            duration=duration,
        )
