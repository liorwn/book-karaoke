#!/usr/bin/env python3
"""
Book Karaoke — Full pipeline: Text -> TTS Audio -> Word Timestamps -> Karaoke Video

Usage:
    python main.py                                          # Process sample text
    python main.py --input path/to/text.txt                 # Custom input
    python main.py --input text.txt --output video.mp4      # Custom input + output
    python main.py --resolution 1920x1080                   # Landscape mode
    python main.py --voice nova                             # Different voice
    python main.py --font-size 60                           # Larger text
    python main.py --ui                                     # Start web UI
    python main.py --input-mode audio --audio recording.mp3 # Audio-only mode
    python main.py --theme neon                             # Use neon color theme
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add project root to path so src/ is importable
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file if it exists (so OPENAI_API_KEY persists across restarts)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Book Karaoke: Generate karaoke-style videos from book text.",
    )
    parser.add_argument(
        "--input", "-i",
        default=str(Path(__file__).parent / "input" / "sample.txt"),
        help="Path to input text file (default: input/sample.txt)",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(Path(__file__).parent / "output" / "karaoke.mp4"),
        help="Path to output video file (default: output/karaoke.mp4)",
    )
    parser.add_argument(
        "--resolution", "-r",
        default="1080x1920",
        help="Video resolution WIDTHxHEIGHT (default: 1080x1920 for portrait/mobile)",
    )
    parser.add_argument(
        "--voice", "-v",
        default="onyx",
        choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        help="OpenAI TTS voice (default: onyx)",
    )
    parser.add_argument(
        "--model", "-m",
        default="tts-1",
        choices=["tts-1", "tts-1-hd"],
        help="OpenAI TTS model (default: tts-1)",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=None,
        help="Font size in pixels (default: auto-calculated based on resolution)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Video frame rate (default: 30)",
    )
    parser.add_argument(
        "--max-words-per-chunk",
        type=int,
        default=20,
        help="Maximum words per display chunk (default: 20)",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Start the web UI server instead of running the CLI pipeline",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the web UI server (default: 8000)",
    )
    parser.add_argument(
        "--input-mode",
        default="text",
        choices=["text", "audio", "text_and_audio"],
        help="Input mode: text (default), audio, or text_and_audio",
    )
    parser.add_argument(
        "--audio",
        default=None,
        help="Path to audio file (required for audio and text_and_audio modes)",
    )
    parser.add_argument(
        "--theme",
        default="dark",
        choices=["dark", "light", "sepia", "neon"],
        help="Color theme preset (default: dark)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # -- Web UI mode -----------------------------------------------------------
    if args.ui:
        import uvicorn
        from src.server import app
        uvicorn.run(app, host="0.0.0.0", port=args.port)
        sys.exit(0)

    # -- CLI pipeline mode -----------------------------------------------------

    # Parse resolution
    try:
        width, height = map(int, args.resolution.lower().split("x"))
    except ValueError:
        print(f"[error] Invalid resolution format: {args.resolution}")
        print("        Expected format: WIDTHxHEIGHT (e.g., 1080x1920)")
        sys.exit(1)

    # Auto-calculate font size based on resolution if not specified
    if args.font_size:
        font_size = args.font_size
    else:
        min_dim = min(width, height)
        font_size = max(32, min(72, int(min_dim * 0.048)))

    print("=" * 60)
    print("  BOOK KARAOKE")
    print("=" * 60)
    print()

    # Validate environment
    if not os.environ.get("OPENAI_API_KEY"):
        print("[error] OPENAI_API_KEY environment variable is not set.")
        print("        Set it with: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    import shutil
    if not shutil.which("ffmpeg"):
        print("[error] ffmpeg is not installed or not on PATH.")
        print("        Install with: brew install ffmpeg (macOS)")
        sys.exit(1)

    if not shutil.which("ffprobe"):
        print("[error] ffprobe is not installed or not on PATH.")
        print("        It should come with ffmpeg.")
        sys.exit(1)

    # Build settings from CLI args
    from src.config import KaraokeSettings
    from src.pipeline import Pipeline

    settings = KaraokeSettings(
        input_mode=args.input_mode,
        voice=args.voice,
        model=args.model,
        width=width,
        height=height,
        fps=args.fps,
        font_size=font_size,
        max_words_per_chunk=args.max_words_per_chunk,
    )
    settings.apply_theme(args.theme)

    # Determine text_path and audio_path based on input mode
    text_path = None
    audio_path = args.audio

    if args.input_mode in ("text", "text_and_audio"):
        text_path = args.input

    if args.input_mode in ("audio", "text_and_audio") and not audio_path:
        print("[error] --audio is required for audio and text_and_audio input modes.")
        sys.exit(1)

    # CLI progress printer
    step_labels = {
        "read_text": "[1/4] Reading input text",
        "tts": "[2/4] Generating TTS audio",
        "transcribe": "[2/4] Transcribing audio",
        "align": "[3/4] Getting word-level timestamps via Whisper",
        "chunk": "[3/4] Building display chunks",
        "render": "[4/4] Rendering karaoke video",
        "done": "Done",
    }

    def cli_progress(step: str, progress: float, message: str) -> None:
        label = step_labels.get(step, step)
        if progress == 0.0:
            print(f"{label}")
        if progress == 1.0:
            print(f"       {message}")
            print()

    pipeline = Pipeline(
        settings=settings,
        text_path=text_path,
        audio_path=audio_path,
        output_path=args.output,
        progress_callback=cli_progress,
    )

    t0 = time.time()
    result = pipeline.run()
    elapsed = time.time() - t0

    # Print summary
    print("=" * 60)
    if result.video_path:
        print(f"  VIDEO SAVED: {result.video_path}")
        file_size = os.path.getsize(result.video_path) / (1024 * 1024)
        print(f"  Size: {file_size:.1f} MB")
    print(f"  Total time: {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
