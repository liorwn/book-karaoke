# Book Karaoke

Turn any text into a karaoke-style audio experience with synchronized word highlighting. Paste text or upload a file, pick a voice, and get an interactive player that lights up each word as it's spoken — like karaoke, but for books.

Everything runs locally. No cloud APIs required for the default setup (TTS via [edge-tts](https://github.com/rany2/edge-tts), alignment via [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) on Apple Silicon).

## Features

- **Browser-based player** — real-time word highlighting synced to audio, with play/pause, seek, speed control, and keyboard shortcuts
- **Multiple input modes** — paste text, upload `.txt`, `.pdf`, or `.epub` files, or bring your own audio
- **10 TTS voices** — powered by Microsoft Edge's neural TTS (free, no API key needed)
- **Local word alignment** — Whisper large-v3-turbo runs on-device via Apple's MLX framework
- **Markdown formatting** — bold and italic in your source text render as styled highlights
- **Search** — Ctrl/Cmd+F to find any word and jump straight to it
- **Project library** — saved to disk with readable URLs, reopen anytime
- **Export HTML** — download a single self-contained `.html` file anyone can open by double-clicking (audio embedded as base64, no server needed)
- **Export subtitles** — SRT and VTT export for use in video editors
- **Export video** — render karaoke MP4 with progress bar (portrait for social, landscape for presentations)
- **4 color themes** — dark (gold), light (red), sepia (warm), neon (green)
- **CLI and web UI** — use from the terminal or the browser

## Quick Start

```bash
# Clone the repo
git clone https://github.com/liorwn/book-karaoke.git
cd book-karaoke

# Install dependencies
pip install -r requirements.txt

# Start the web UI
python main.py --ui
```

Open [http://localhost:8000](http://localhost:8000), paste some text, pick a voice, and hit Generate.

> **Note:** The first run downloads the Whisper model (~1.5 GB). Subsequent runs are instant.

## Requirements

- Python 3.11+
- macOS with Apple Silicon (for mlx-whisper; see below for alternatives)
- `ffmpeg` on PATH (only needed for MP4 video export)

## CLI Usage

```bash
# Process a text file with default settings
python main.py --input passage.txt

# Choose a voice and theme
python main.py --input passage.txt --voice nova --theme neon

# Landscape video for presentations
python main.py --input passage.txt --resolution 1920x1080

# Audio-only mode (transcribe existing audio)
python main.py --input-mode audio --audio recording.mp3

# Text + audio mode (skip TTS, use your own narration)
python main.py --input-mode text_and_audio --input passage.txt --audio narration.mp3

# Start the web UI on a custom port
python main.py --ui --port 3000
```

## Available Voices

| Voice | Style |
|-------|-------|
| `andrew` (default) | Warm, conversational male |
| `ava` | Clear, professional female |
| `brian` | Friendly male |
| `christopher` | Authoritative male |
| `emma` | Natural female |
| `eric` | Calm male |
| `guy` | Neutral male |
| `jenny` | Bright female |
| `roger` | Deep male |
| `steffan` | Polished male |

## Color Themes

| Theme | Background | Highlight | Look |
|-------|-----------|-----------|------|
| `dark` | Deep blue | Gold | Default, easy on the eyes |
| `light` | Cream | Red | Clean, high contrast |
| `sepia` | Brown | Sandy orange | Warm, book-like |
| `neon` | Black | Green | Bold, high energy |

## How It Works

1. **Text input** — reads your text (handles plain text, PDF, epub, and markdown formatting)
2. **TTS** — edge-tts converts text to speech using Microsoft's neural voices
3. **Alignment** — mlx-whisper transcribes the audio back with word-level timestamps
4. **Chunking** — text is split into display-sized chunks at sentence boundaries
5. **Playback** — the browser player highlights each word in real time as the audio plays

## Project Structure

```
book-karaoke/
  main.py              # CLI entry point + web UI launcher
  requirements.txt     # Python dependencies
  pyproject.toml       # Package metadata
  .env.example         # Environment variable template
  input/               # Default input text files
    sample.txt
  src/
    config.py          # Settings dataclass and theme presets
    pipeline.py        # Pipeline orchestration (all input modes)
    tts.py             # edge-tts speech generation
    align.py           # mlx-whisper word-level alignment
    transcribe.py      # Audio-to-text transcription
    render.py          # PIL frame rendering + ffmpeg video assembly
    export.py          # Subtitle export (SRT/VTT)
    export_html.py     # Standalone HTML export
    utils.py           # Text chunking, formatting, helpers
    server.py          # FastAPI server + API endpoints
  static/
    index.html         # Web UI
    css/styles.css     # Player and UI styles
    js/
      app.js           # Main application controller
      player.js        # Audio player engine
      renderer.js      # Karaoke text renderer
      settings.js      # Settings panel
      upload.js        # File upload handler
      export.js        # Export controller
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/p/{slug}` | Load a saved project |
| `POST` | `/api/upload` | Upload text/audio file |
| `GET` | `/api/stream/{id}` | SSE progress stream |
| `GET` | `/api/timestamps/{id}` | Get project data |
| `POST` | `/api/reprocess/{id}` | Re-generate with new settings |
| `GET` | `/api/projects` | List saved projects |
| `GET` | `/api/export/html/{id}` | Download standalone HTML |
| `GET` | `/api/export/srt/{id}` | Download SRT subtitles |
| `GET` | `/api/export/vtt/{id}` | Download VTT subtitles |

## Non-Apple Silicon

The default setup uses `mlx-whisper` which requires Apple Silicon. To run on other platforms, swap the alignment backend:

1. Replace `mlx-whisper` with `faster-whisper` in `requirements.txt`
2. Update `src/align.py` to use `faster-whisper`'s `WhisperModel` class (same word timestamp API)

## License

MIT
