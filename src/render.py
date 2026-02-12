"""
Karaoke video renderer.

Generates frames with PIL/Pillow and assembles them into a video with ffmpeg.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .utils import find_font


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

COLOR_BG = (26, 26, 46)            # #1a1a2e — deep navy/black
COLOR_HIGHLIGHT = (255, 215, 0)     # #FFD700 — gold for current word
COLOR_SPOKEN = (187, 187, 187)      # #BBBBBB — already spoken
COLOR_UPCOMING = (85, 85, 85)       # #555555 — not yet spoken
COLOR_PROGRESS_BG = (40, 40, 60)    # progress bar background
COLOR_PROGRESS_FG = (255, 215, 0)   # progress bar fill (gold)


# ---------------------------------------------------------------------------
# Text layout engine
# ---------------------------------------------------------------------------

class TextLayout:
    """Handles word-wrapping and positioning of text on a frame."""

    def __init__(
        self,
        width: int,
        height: int,
        font: ImageFont.FreeTypeFont,
        margin_x: int = 80,
        margin_top: int = 0,
        line_spacing: float = 1.5,
    ):
        self.width = width
        self.height = height
        self.font = font
        self.margin_x = margin_x
        self.margin_top = margin_top
        self.line_spacing = line_spacing
        self.max_text_width = width - 2 * margin_x

    def get_word_size(self, word: str) -> tuple[int, int]:
        """Get the pixel dimensions of a word."""
        bbox = self.font.getbbox(word)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def get_space_width(self) -> int:
        """Get the pixel width of a space character."""
        bbox = self.font.getbbox(" ")
        return bbox[2] - bbox[0]

    def layout_words(self, words: list[str]) -> list[list[tuple[str, int, int]]]:
        """
        Wrap words into lines that fit within max_text_width.

        Returns a list of lines, where each line is a list of
        (word, x_offset, word_index_in_input) tuples.
        """
        lines = []
        current_line = []
        current_x = 0
        space_w = self.get_space_width()

        for idx, word in enumerate(words):
            w, h = self.get_word_size(word)

            if current_line and current_x + space_w + w > self.max_text_width:
                lines.append(current_line)
                current_line = []
                current_x = 0

            if current_line:
                current_x += space_w

            current_line.append((word, current_x, idx))
            current_x += w

        if current_line:
            lines.append(current_line)

        return lines

    def get_block_height(self, lines: list) -> int:
        """Calculate total height of a text block."""
        if not lines:
            return 0
        _, h = self.get_word_size("Hg")  # representative height
        line_h = int(h * self.line_spacing)
        return line_h * len(lines)

    def get_vertical_offset(self, lines: list) -> int:
        """Calculate Y offset to vertically center the text block."""
        block_h = self.get_block_height(lines)
        # Center vertically, but bias slightly upward
        return max(self.margin_top, (self.height - block_h) // 2 - 40)


# ---------------------------------------------------------------------------
# Frame renderer
# ---------------------------------------------------------------------------

def render_frame(
    draw: ImageDraw.ImageDraw,
    layout: TextLayout,
    chunk_words: list[str],
    chunk_timings: list[dict],
    current_time: float,
    progress: float,
    width: int,
    height: int,
    fade_alpha: float = 1.0,
    settings=None,
) -> None:
    """
    Render a single karaoke frame onto an ImageDraw surface.

    Args:
        draw: PIL ImageDraw to draw on.
        layout: TextLayout instance for word positioning.
        chunk_words: List of word strings for this chunk.
        chunk_timings: List of timing dicts with "word", "start", "end".
        current_time: Current playback time in seconds.
        progress: Overall progress 0.0-1.0 (for progress bar).
        width: Frame width.
        height: Frame height.
        fade_alpha: Opacity for fade transitions (0.0-1.0).
        settings: Optional KaraokeSettings instance. When provided, colors
            and progress bar dimensions are taken from settings instead of
            the module-level COLOR_* constants.
    """
    # Resolve colors — settings override hardcoded constants
    if settings is not None:
        color_bg = settings.bg_rgb
        color_highlight = settings.highlight_rgb
        color_spoken = settings.spoken_rgb
        color_upcoming = settings.upcoming_rgb
        color_progress_bg = settings.progress_bg_rgb
        color_progress_fg = settings.progress_fg_rgb
        bar_height = settings.progress_bar_height
        bar_bottom_offset = settings.progress_bar_bottom_offset
        bar_margin = settings.progress_bar_margin
    else:
        color_bg = COLOR_BG
        color_highlight = COLOR_HIGHLIGHT
        color_spoken = COLOR_SPOKEN
        color_upcoming = COLOR_UPCOMING
        color_progress_bg = COLOR_PROGRESS_BG
        color_progress_fg = COLOR_PROGRESS_FG
        bar_height = 4
        bar_bottom_offset = 60
        bar_margin = 80

    # Background
    draw.rectangle([0, 0, width, height], fill=color_bg)

    if not chunk_words:
        return

    # Lay out words into lines
    lines = layout.layout_words(chunk_words)
    y_start = layout.get_vertical_offset(lines)

    _, char_h = layout.get_word_size("Hg")
    line_h = int(char_h * layout.line_spacing)

    for line_idx, line in enumerate(lines):
        y = y_start + line_idx * line_h

        # Center the line horizontally
        if line:
            last_word, last_x, _ = line[-1]
            last_w, _ = layout.get_word_size(last_word)
            line_width = last_x + last_w
            x_offset = (width - line_width) // 2
        else:
            x_offset = layout.margin_x

        for word, x, word_idx in line:
            # Determine word color based on timing
            if word_idx < len(chunk_timings):
                timing = chunk_timings[word_idx]
                word_start = timing["start"]
                word_end = timing["end"]

                if current_time >= word_start and current_time < word_end:
                    # Currently being spoken
                    color = color_highlight
                elif current_time >= word_end:
                    # Already spoken
                    color = color_spoken
                else:
                    # Not yet spoken
                    color = color_upcoming
            else:
                color = color_upcoming

            # Apply fade alpha
            if fade_alpha < 1.0:
                color = tuple(int(c * fade_alpha) for c in color)

            draw.text((x_offset + x, y), word, fill=color, font=layout.font)

    # Progress bar at bottom
    bar_y = height - bar_bottom_offset
    bar_width = width - 2 * bar_margin

    # Background bar
    draw.rectangle(
        [bar_margin, bar_y, bar_margin + bar_width, bar_y + bar_height],
        fill=color_progress_bg,
    )
    # Fill bar
    fill_width = int(bar_width * progress)
    if fill_width > 0:
        draw.rectangle(
            [bar_margin, bar_y, bar_margin + fill_width, bar_y + bar_height],
            fill=color_progress_fg,
        )


# ---------------------------------------------------------------------------
# Video assembly
# ---------------------------------------------------------------------------

def render_video(
    chunk_timings: list[list[dict]],
    audio_path: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    font_size: int = 52,
    settings=None,
    progress_callback=None,
) -> str:
    """
    Render the full karaoke video.

    Args:
        chunk_timings: List of chunks, each containing a list of word timing dicts.
        audio_path: Path to the audio file.
        output_path: Where to save the final video.
        width: Video width in pixels.
        height: Video height in pixels.
        fps: Frames per second.
        font_size: Font size for the karaoke text.
        settings: Optional KaraokeSettings instance. When provided, overrides
            width/height/fps/font_size and supplies colors to render_frame().
        progress_callback: Optional callable(step, progress, message) for
            reporting rendering progress.

    Returns:
        Path to the generated video file.
    """
    from .utils import get_audio_duration_seconds

    # When settings is provided, it overrides the explicit parameters
    if settings is not None:
        width = settings.width
        height = settings.height
        fps = settings.fps
        font_size = settings.font_size
        margin_x = settings.margin_x
        line_spacing = settings.line_spacing
    else:
        margin_x = 80
        line_spacing = 1.5

    # Get audio duration
    audio_duration = get_audio_duration_seconds(audio_path)
    total_frames = int(audio_duration * fps)

    print(f"[render] Video: {width}x{height} @ {fps}fps")
    print(f"[render] Audio duration: {audio_duration:.2f}s, total frames: {total_frames}")
    print(f"[render] Chunks: {len(chunk_timings)}")

    # Load font
    font = find_font(font_size)
    print(f"[render] Font loaded: {font_size}px")

    # Set up layout
    layout = TextLayout(width, height, font, margin_x=margin_x, line_spacing=line_spacing)

    # Determine chunk time ranges
    chunk_ranges = []
    for chunk in chunk_timings:
        if chunk:
            start = chunk[0]["start"]
            end = chunk[-1]["end"]
            chunk_ranges.append((start, end))
        else:
            chunk_ranges.append((0, 0))

    # Add padding between chunks for transitions
    fade_duration = settings.fade_duration if settings is not None else 0.3

    # Create temp directory for frames
    temp_dir = tempfile.mkdtemp(prefix="book_karaoke_")
    print(f"[render] Temp frames directory: {temp_dir}")

    try:
        # Render frames
        print(f"[render] Rendering {total_frames} frames...")
        last_percent = -1

        for frame_idx in range(total_frames):
            current_time = frame_idx / fps
            progress = current_time / audio_duration if audio_duration > 0 else 0

            # Find active chunk
            active_chunk_idx = None
            fade_alpha = 1.0

            for ci, (cs, ce) in enumerate(chunk_ranges):
                # Add some pre-roll so text appears slightly before the words start
                pre_roll = settings.pre_roll if settings is not None else 0.3
                # Add post-roll so text stays briefly after last word
                base_post_roll = settings.post_roll if settings is not None else 0.3
                post_roll = base_post_roll if ci < len(chunk_ranges) - 1 else 1.0

                if current_time >= cs - pre_roll and current_time <= ce + post_roll:
                    active_chunk_idx = ci

                    # Fade in
                    if current_time < cs:
                        fade_alpha = max(0.0, 1.0 - (cs - current_time) / pre_roll)
                    # Fade out
                    elif current_time > ce:
                        fade_alpha = max(0.0, 1.0 - (current_time - ce) / post_roll)
                    else:
                        fade_alpha = 1.0
                    break

            # Resolve colors for frame creation
            _bg = settings.bg_rgb if settings is not None else COLOR_BG

            # Create frame
            img = Image.new("RGB", (width, height), _bg)
            draw = ImageDraw.Draw(img)

            if active_chunk_idx is not None:
                chunk = chunk_timings[active_chunk_idx]
                chunk_words = [w["word"] for w in chunk]
                render_frame(
                    draw=draw,
                    layout=layout,
                    chunk_words=chunk_words,
                    chunk_timings=chunk,
                    current_time=current_time,
                    progress=progress,
                    width=width,
                    height=height,
                    fade_alpha=fade_alpha,
                    settings=settings,
                )
            else:
                # Empty frame (between chunks or before/after audio)
                if settings is not None:
                    _progress_bg = settings.progress_bg_rgb
                    _progress_fg = settings.progress_fg_rgb
                    _bar_height = settings.progress_bar_height
                    _bar_bottom = settings.progress_bar_bottom_offset
                    _bar_margin = settings.progress_bar_margin
                else:
                    _progress_bg = COLOR_PROGRESS_BG
                    _progress_fg = COLOR_PROGRESS_FG
                    _bar_height = 4
                    _bar_bottom = 60
                    _bar_margin = 80

                draw.rectangle([0, 0, width, height], fill=_bg)
                # Still draw progress bar
                bar_y = height - _bar_bottom
                bar_width_px = width - 2 * _bar_margin
                draw.rectangle(
                    [_bar_margin, bar_y, _bar_margin + bar_width_px, bar_y + _bar_height],
                    fill=_progress_bg,
                )
                fill_width = int(bar_width_px * progress)
                if fill_width > 0:
                    draw.rectangle(
                        [_bar_margin, bar_y, _bar_margin + fill_width, bar_y + _bar_height],
                        fill=_progress_fg,
                    )

            # Save frame
            frame_path = os.path.join(temp_dir, f"frame_{frame_idx:06d}.png")
            img.save(frame_path)

            # Progress reporting
            percent = int((frame_idx + 1) / total_frames * 100)
            if percent != last_percent and percent % 5 == 0:
                print(f"[render] {percent}% ({frame_idx + 1}/{total_frames} frames)")
                last_percent = percent

            # Progress callback (every 30 frames to avoid excessive calls)
            if progress_callback and frame_idx % 30 == 0:
                progress_callback(
                    "rendering",
                    frame_idx / total_frames,
                    f"Rendering frame {frame_idx}/{total_frames}",
                )

        print(f"[render] All frames rendered. Assembling video with ffmpeg...")

        if progress_callback:
            progress_callback("rendering", 0.95, "Assembling video with ffmpeg...")

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Assemble video with ffmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(temp_dir, "frame_%06d.png"),
            "-i", audio_path,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ]

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"[render] ffmpeg stderr:\n{result.stderr}")
            raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

        file_size = os.path.getsize(output_path)
        print(f"[render] Video saved to {output_path} ({file_size / (1024 * 1024):.1f} MB)")

        if progress_callback:
            progress_callback("rendering", 1.0, "Video rendering complete")

        return output_path

    finally:
        # Clean up temp frames
        print(f"[render] Cleaning up temp frames...")
        shutil.rmtree(temp_dir, ignore_errors=True)
