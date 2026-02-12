# Book Karaoke

Turn any text into a karaoke-style audio experience with synchronized word highlighting. Browser-based player with edge-tts for speech and mlx-whisper for local word-level alignment.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the web UI (primary usage)
python main.py --ui

# Start on a custom port
python main.py --ui --port 3000

# CLI: process a text file directly
python main.py --input passage.txt --output karaoke.mp4

# CLI: different voice and theme
python main.py --input passage.txt --voice nova --theme neon

# CLI: audio-only mode (transcribe existing audio)
python main.py --input-mode audio --audio recording.mp3

# CLI: text + audio (skip TTS, use your own narration)
python main.py --input-mode text_and_audio --input passage.txt --audio narration.mp3
```

## Pipeline

1. **Text input** — reads plain text, PDF, epub; extracts markdown bold/italic formatting
2. **TTS** — edge-tts (Microsoft Edge neural voices, free, no API key)
3. **Alignment** — mlx-whisper (whisper-large-v3-turbo, runs locally on Apple Silicon)
4. **Chunking** — splits text into display-sized chunks at sentence boundaries
5. **Playback** — browser player highlights each word in real time as audio plays

## Architecture

```
main.py                 — CLI entry point + web UI launcher (.env loader)
src/
  config.py             — KaraokeSettings dataclass, 4 theme presets (dark/light/sepia/neon)
  pipeline.py           — Pipeline class orchestrating all input modes, returns PipelineResult
  tts.py                — edge-tts wrapper, 10 voices (VOICE_MAP), chunked generation for long text
  align.py              — mlx-whisper word-level timestamps (whisper-large-v3-turbo)
  transcribe.py         — mlx-whisper audio-to-text transcription
  render.py             — PIL frame rendering + ffmpeg video assembly (MP4 export)
  export.py             — SRT/VTT subtitle export
  export_html.py        — Standalone HTML export (base64 audio, inline JS/CSS, self-contained)
  utils.py              — clean_text, chunk_text, map_whisper_words_to_chunks, extract_formatting
  server.py             — FastAPI server: upload, SSE progress, project persistence, all exports
static/
  index.html            — Single-page web UI
  css/styles.css        — All styles (player, upload, processing, search, library, export)
  js/
    app.js              — Main app controller (wires everything, state management, search, URL routing)
    player.js           — Audio player engine (HTML5 Audio wrapper, time events, chunk tracking)
    renderer.js         — Karaoke text renderer (word highlighting, formatting, fade animations)
    settings.js         — Settings panel (voice, theme, words-per-chunk, localStorage persistence)
    upload.js           — File upload + text paste handler (FormData to /api/upload)
    export.js           — Export controller (MP4, SRT, VTT, HTML download triggers)
```

## Key Patterns

- **SSE progress** — server.py streams pipeline progress via Server-Sent Events (`/api/stream/{id}`), client listens in app.js
- **Project persistence** — projects saved to `projects/{slug}/` on disk (JSON + audio + input file), restored on server startup via `_load_projects()`
- **Slug URLs** — `/p/{slug}` routes; slug derived from filename (`_slugify_filename`) or first words of text (`_slugify_text`), with collision avoidance (`_unique_slug`)
- **Reprocessing** — `POST /api/reprocess/{id}` re-runs pipeline with new settings on existing files (no re-upload)
- **Formatting pipeline** — `extract_formatting()` in utils.py builds a word→style map from markdown; stripped before TTS, preserved for renderer CSS classes
- **Standalone HTML** — `export_html.py` embeds audio as base64 data URI, inlines player.js + renderer.js, includes full CSS and bootstrap JS

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/p/{slug}` | Load saved project by slug |
| `POST` | `/api/upload` | Upload file (accepts `voice`, `words_per_chunk` form params) |
| `GET` | `/api/stream/{id}` | SSE progress stream for pipeline |
| `GET` | `/api/timestamps/{id}` | Get chunks, formatting, audio URL, duration |
| `POST` | `/api/reprocess/{id}` | Re-generate with new settings |
| `GET` | `/api/projects` | List all saved projects |
| `GET` | `/api/export/html/{id}` | Download standalone HTML |
| `GET` | `/api/export/srt/{id}` | Download SRT subtitles |
| `GET` | `/api/export/vtt/{id}` | Download VTT subtitles |
| `POST` | `/api/export/mp4/{id}` | Start MP4 render job |

## Dependencies

- `edge-tts` — Microsoft Edge neural TTS (free, no API key)
- `mlx-whisper` — Local Whisper on Apple Silicon (auto-downloads whisper-large-v3-turbo on first use)
- `Pillow` — Frame rendering for MP4 export
- `fastapi` + `uvicorn` — Web server
- `python-multipart` — File upload handling
- `ffmpeg` — Required on PATH for MP4 video export only

## Design Decisions

- Primary experience is browser-based playback, video export is secondary
- All processing runs locally (no cloud API calls in default config)
- Portrait (1080x1920) default for social media / mobile viewing
- Gold (#FFD700) highlight for current word in dark theme
- Three brightness levels: spoken → active (highlighted) → upcoming
- Sentence-based chunking (~20 words per chunk, configurable)
- Projects auto-save to disk with readable slugs for persistent URLs
- Single-file HTML export embeds everything for zero-dependency sharing
