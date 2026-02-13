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
from .utils import clean_text, chunk_text, chunk_text_with_chapters, map_whisper_words_to_chunks, get_audio_duration_seconds, extract_formatting


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
