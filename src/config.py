"""
Karaoke settings and theme presets.

Centralizes all configurable values (colors, dimensions, timing, etc.)
previously hardcoded across render.py, utils.py, and main.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string like '#FFD700' to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an (R, G, B) tuple to a hex color string like '#FFD700'."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


# ---------------------------------------------------------------------------
# Theme presets
# ---------------------------------------------------------------------------

THEME_PRESETS: dict[str, dict[str, str]] = {
    "dark": {
        "bg_color": "#1a1a2e",
        "highlight_color": "#FFD700",
        "spoken_color": "#BBBBBB",
        "upcoming_color": "#555555",
        "progress_bg_color": "#28283c",
        "progress_fg_color": "#FFD700",
    },
    "light": {
        "bg_color": "#f5f5f0",
        "highlight_color": "#d4380d",
        "spoken_color": "#333333",
        "upcoming_color": "#aaaaaa",
        "progress_bg_color": "#dddddd",
        "progress_fg_color": "#d4380d",
    },
    "sepia": {
        "bg_color": "#2b1d0e",
        "highlight_color": "#f4a460",
        "spoken_color": "#c8b89a",
        "upcoming_color": "#5c4a32",
        "progress_bg_color": "#3d2b16",
        "progress_fg_color": "#f4a460",
    },
    "neon": {
        "bg_color": "#0a0a0a",
        "highlight_color": "#00ff88",
        "spoken_color": "#cc66ff",
        "upcoming_color": "#333333",
        "progress_bg_color": "#1a1a1a",
        "progress_fg_color": "#00ff88",
    },
}


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

@dataclass
class KaraokeSettings:
    """All configurable parameters for a Book Karaoke render."""

    # -- Input mode ----------------------------------------------------------
    input_mode: str = "text"  # "text", "audio", or "text_and_audio"

    # -- TTS -----------------------------------------------------------------
    voice: str = "andrew"
    model: str = "tts-1"

    # -- Video dimensions & frame rate ---------------------------------------
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # -- Typography ----------------------------------------------------------
    font_size: int = 52
    margin_x: int = 80
    line_spacing: float = 1.5

    # -- Text chunking -------------------------------------------------------
    max_words_per_chunk: int = 20

    # -- Colors (stored as hex strings) --------------------------------------
    bg_color: str = "#1a1a2e"
    highlight_color: str = "#FFD700"
    spoken_color: str = "#BBBBBB"
    upcoming_color: str = "#555555"
    progress_bg_color: str = "#28283c"
    progress_fg_color: str = "#FFD700"

    # -- Timing (seconds) ----------------------------------------------------
    pre_roll: float = 0.3
    post_roll: float = 0.3
    fade_duration: float = 0.3

    # -- Progress bar --------------------------------------------------------
    progress_bar_height: int = 4
    progress_bar_margin: int = 80
    progress_bar_bottom_offset: int = 60

    # -- Theme ---------------------------------------------------------------
    theme: str = "dark"

    # -- RGB tuple helpers (not serialized) -----------------------------------

    @property
    def bg_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.bg_color)

    @property
    def highlight_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.highlight_color)

    @property
    def spoken_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.spoken_color)

    @property
    def upcoming_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.upcoming_color)

    @property
    def progress_bg_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.progress_bg_color)

    @property
    def progress_fg_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.progress_fg_color)

    # -- Theme application ---------------------------------------------------

    def apply_theme(self, theme_name: str) -> None:
        """Apply a named theme preset, overwriting the color fields."""
        if theme_name not in THEME_PRESETS:
            available = ", ".join(sorted(THEME_PRESETS))
            raise ValueError(
                f"Unknown theme {theme_name!r}. Available: {available}"
            )
        preset = THEME_PRESETS[theme_name]
        self.bg_color = preset["bg_color"]
        self.highlight_color = preset["highlight_color"]
        self.spoken_color = preset["spoken_color"]
        self.upcoming_color = preset["upcoming_color"]
        self.progress_bg_color = preset["progress_bg_color"]
        self.progress_fg_color = preset["progress_fg_color"]
        self.theme = theme_name

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Export all settings as a plain dict (JSON-serializable)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KaraokeSettings:
        """Create a KaraokeSettings instance from a dict.

        Unknown keys are silently ignored so that loading a config from a
        newer version doesn't break.
        """
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
