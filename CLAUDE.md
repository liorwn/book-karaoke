# Book Karaoke

A Python pipeline that converts book text into karaoke-style videos with synchronized word highlighting.

## Pipeline

1. **TTS Generation** — OpenAI TTS API (`tts-1`, voice `onyx`) converts text to speech
2. **Alignment** — OpenAI Whisper API transcribes the audio back with word-level timestamps
3. **Rendering** — PIL generates frames with karaoke highlighting, ffmpeg assembles the video

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run with sample text (default)
python main.py

# Run with custom input/output
python main.py --input path/to/text.txt --output path/to/output.mp4

# Landscape mode (default is portrait 1080x1920)
python main.py --resolution 1920x1080

# Start the web UI
python main.py --ui

# Start the web UI on a custom port
python main.py --ui --port 3000
```

## Web UI Mode

Start the web interface with `python main.py --ui`. This launches a FastAPI server at `http://localhost:8000` (or the port specified with `--port`).

### API Endpoints

- `POST /api/generate` — Submit a karaoke generation job (text, settings, optional audio file)
- `GET /api/status/{job_id}` — Poll job status and progress
- `GET /api/download/{job_id}` — Download the completed video
- `GET /api/settings/defaults` — Get default settings and available options
- `GET /` — Serves the web UI

## Input Modes

Three input modes are supported via `--input-mode`:

- **text** (default) — Provide a text file via `--input`. TTS generates audio, Whisper aligns timestamps, video is rendered.
- **audio** — Provide an audio file via `--audio`. Whisper transcribes the audio to text, then aligns timestamps and renders video.
- **text_and_audio** — Provide both `--input` (text) and `--audio` (audio file). Skips TTS, goes straight to alignment and rendering.

```bash
# Text mode (default)
python main.py --input passage.txt

# Audio mode
python main.py --input-mode audio --audio recording.mp3

# Text + audio mode (skip TTS)
python main.py --input-mode text_and_audio --input passage.txt --audio narration.mp3
```

## Settings and Themes

All rendering settings are centralized in `KaraokeSettings` (`src/config.py`). Four built-in color themes are available:

| Theme  | Background | Highlight | Description            |
|--------|-----------|-----------|------------------------|
| dark   | #1a1a2e   | #FFD700   | Dark blue with gold    |
| light  | #f5f5f0   | #d4380d   | Light cream with red   |
| sepia  | #2b1d0e   | #f4a460   | Warm brown tones       |
| neon   | #0a0a0a   | #00ff88   | Black with green glow  |

```bash
python main.py --theme neon
python main.py --theme sepia --voice nova
```

## Requirements

- Python 3.11+
- `ffmpeg` installed and on PATH
- `OPENAI_API_KEY` environment variable set

## Project Structure

```
book-karaoke/
  main.py              — CLI entry point (also starts web UI with --ui)
  requirements.txt     — Python dependencies
  pyproject.toml       — Project metadata and packaging config
  .env.example         — Environment variable template
  LICENSE              — MIT license
  input/               — Default input text files
    sample.txt
  output/              — Default output directory for generated videos
  src/
    __init__.py
    config.py          — KaraokeSettings dataclass and theme presets
    pipeline.py        — Pipeline orchestration (text/audio/text_and_audio modes)
    tts.py             — OpenAI TTS generation
    align.py           — Whisper word-level timestamp alignment
    transcribe.py      — Whisper audio-to-text transcription
    render.py          — PIL frame rendering + ffmpeg video assembly
    export.py          — Export utilities
    utils.py           — Text chunking, font loading, helpers
    server.py          — FastAPI web server and API endpoints
```

## Architecture

- `src/config.py` — `KaraokeSettings` dataclass centralizes all configurable values (colors, dimensions, timing, themes)
- `src/pipeline.py` — `Pipeline` class orchestrates the full workflow for all input modes
- `src/tts.py` — OpenAI TTS generation
- `src/align.py` — Whisper word-level timestamp alignment
- `src/transcribe.py` — Whisper audio-to-text transcription
- `src/render.py` — PIL frame rendering + ffmpeg video assembly
- `src/utils.py` — Text chunking, font loading, helpers
- `src/server.py` — FastAPI server with job queue and SSE progress updates

## Design Choices

- Portrait (1080x1920) default for social media / mobile viewing
- Gold (#FFD700) highlight for the current word (in dark theme)
- Three brightness levels: spoken, current (highlighted), upcoming
- ~2-3 lines of text shown at a time via sentence-based chunking
- Progress bar at the bottom of the video
- 30 FPS rendering for smooth highlighting transitions
