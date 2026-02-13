"""
FastAPI backend for Book Karaoke web UI.

Provides file upload, pipeline processing with SSE progress,
audio/video serving, subtitle export, and theme listing.
Projects are persisted to the projects/ directory on disk.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import THEME_PRESETS, KaraokeSettings
from .export import export_srt, export_vtt
from .export_html import generate_standalone_html
from .pipeline import Pipeline

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Book Karaoke", version="1.0.0")

# Static files directory (served under /static, root HTML served separately)
STATIC_DIR = Path(__file__).parent.parent / "static"

# Projects directory — persistent storage on disk
PROJECTS_DIR = Path(__file__).parent.parent / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

sessions: dict[str, dict[str, Any]] = {}


def _get_session(session_id: str) -> dict:
    """Retrieve a session or raise 404."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return sessions[session_id]


def _new_session_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def _slugify_filename(filename: str) -> str | None:
    """Generate a slug from a filename. Returns None if generic/unusable."""
    if not filename:
        return None
    stem = Path(filename).stem.lower()
    # Skip generic names
    if stem in ("input", "file", "upload", "text", "document", "untitled"):
        return None
    # Replace non-alphanumeric with hyphens, collapse multiples
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug if slug else None


def _slugify_text(text: str, max_words: int = 6) -> str:
    """Generate a slug from the first few words of text."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower())
    words = clean.split()[:max_words]
    slug = "-".join(words)
    if not slug:
        slug = _new_session_id()
    return slug


def _unique_slug(base_slug: str) -> str:
    """Ensure slug is unique by appending a number if needed."""
    slug = base_slug
    counter = 2
    while slug in sessions or (PROJECTS_DIR / slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


# ---------------------------------------------------------------------------
# Project persistence
# ---------------------------------------------------------------------------

def _save_project(session: dict) -> None:
    """Save a completed project to disk."""
    slug = session["id"]
    project_dir = PROJECTS_DIR / slug
    project_dir.mkdir(parents=True, exist_ok=True)

    # Copy audio file to project dir
    audio_src = session.get("audio_generated_path") or session.get("audio_path")
    audio_dest = None
    if audio_src and Path(audio_src).exists():
        ext = Path(audio_src).suffix
        audio_dest = str(project_dir / f"audio{ext}")
        if str(Path(audio_src).resolve()) != str(Path(audio_dest).resolve()):
            shutil.copy2(audio_src, audio_dest)

    # Copy input file to project dir
    text_src = session.get("text_path")
    text_dest = None
    if text_src and Path(text_src).exists():
        ext = Path(text_src).suffix
        text_dest = str(project_dir / f"input{ext}")
        if str(Path(text_src).resolve()) != str(Path(text_dest).resolve()):
            shutil.copy2(text_src, text_dest)

    # Build preview (first ~100 chars of text)
    text = session.get("text") or ""
    preview = text[:120].replace("\n", " ").strip()
    if len(text) > 120:
        preview += "..."

    # Save metadata
    meta = {
        "id": slug,
        "title": _title_from_text(text),
        "preview": preview,
        "created_at": session.get("created_at", datetime.now().isoformat()),
        "duration": session.get("duration"),
        "word_count": len(text.split()) if text else 0,
        "settings": session.get("settings", {}),
        "chunks": session.get("chunks"),
        "chunks_with_timings": session.get("chunks_with_timings"),
        "formatting": session.get("formatting", {}),
        "chapters": session.get("chapters"),
        "audio_file": Path(audio_dest).name if audio_dest else None,
        "input_file": Path(text_dest).name if text_dest else None,
    }

    (project_dir / "project.json").write_text(json.dumps(meta, indent=2))


def _title_from_text(text: str) -> str:
    """Generate a display title from the first line or few words."""
    first_line = text.strip().split("\n")[0].strip() if text else ""
    # Use first line if short enough, otherwise first ~8 words
    if len(first_line) <= 60:
        return first_line
    words = first_line.split()[:8]
    return " ".join(words) + "..."


def _load_projects() -> None:
    """Scan the projects/ directory and load saved projects into sessions."""
    if not PROJECTS_DIR.exists():
        return

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        meta_path = project_dir / "project.json"
        if not meta_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text())
            slug = meta["id"]

            # Find audio file
            audio_path = None
            if meta.get("audio_file"):
                audio_path = str(project_dir / meta["audio_file"])

            # Find input file
            text_path = None
            if meta.get("input_file"):
                text_path = str(project_dir / meta["input_file"])

            session = {
                "id": slug,
                "work_dir": str(project_dir),
                "text_path": text_path,
                "audio_path": audio_path,
                "text": None,  # not loaded into memory
                "chunks": meta.get("chunks"),
                "chunks_with_timings": meta.get("chunks_with_timings"),
                "settings": meta.get("settings", {}),
                "formatting": meta.get("formatting", {}),
                "chapters": meta.get("chapters"),
                "audio_generated_path": audio_path,
                "video_path": None,
                "duration": meta.get("duration"),
                "status": "ready",
                "error": None,
                "progress_events": [],
                "processing_done": None,
                "created_at": meta.get("created_at"),
            }
            sessions[slug] = session
        except Exception as exc:
            print(f"[warn] Failed to load project {project_dir.name}: {exc}")


# Load existing projects on import
_load_projects()


# ---------------------------------------------------------------------------
# POST /api/upload  --  Upload text/audio/epub file
# ---------------------------------------------------------------------------

ALLOWED_TEXT_EXT = {".txt", ".md", ".text"}
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
ALLOWED_EPUB_EXT = {".epub"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    type: str = Form("text"),
    voice: str | None = Form(None),
    words_per_chunk: int | None = Form(None),
):
    """Accept a file upload, store it, and return a session_id."""
    # Use a temp ID during processing; slug assigned after text is known
    temp_id = _new_session_id()
    work_dir = tempfile.mkdtemp(prefix=f"karaoke_{temp_id}_")

    # Save uploaded file
    ext = Path(file.filename or "file.txt").suffix.lower()
    saved_name = f"input{ext}"
    saved_path = Path(work_dir) / saved_name

    content = await file.read()
    saved_path.write_bytes(content)

    # Determine what we got
    text_path = None
    audio_path = None
    input_mode = "text"

    if type == "audio" or ext in ALLOWED_AUDIO_EXT:
        audio_path = str(saved_path)
        input_mode = "audio"
    elif type in ("text", "epub", "pdf") or ext in ALLOWED_TEXT_EXT:
        text_path = str(saved_path)
        input_mode = "text"
    else:
        text_path = str(saved_path)
        input_mode = "text"

    # Build settings dict with user-selected values
    settings: dict[str, Any] = {"input_mode": input_mode}
    if voice:
        settings["voice"] = voice
    if words_per_chunk is not None:
        settings["max_words_per_chunk"] = words_per_chunk

    session = {
        "id": temp_id,
        "work_dir": work_dir,
        "text_path": text_path,
        "audio_path": audio_path,
        "text": None,
        "chunks": None,
        "chunks_with_timings": None,
        "settings": settings,
        "chapters": None,
        "audio_generated_path": None,
        "video_path": None,
        "duration": None,
        "status": "uploaded",
        "error": None,
        "progress_events": [],
        "processing_done": None,
        "created_at": datetime.now().isoformat(),
        "original_filename": file.filename,
    }
    sessions[temp_id] = session

    return {"id": temp_id, "status": "uploaded", "input_mode": input_mode}


# ---------------------------------------------------------------------------
# POST /api/reprocess/{session_id}  --  Update settings and re-run pipeline
# ---------------------------------------------------------------------------

@app.post("/api/reprocess/{session_id}")
async def reprocess_session(
    session_id: str,
    voice: str | None = Form(None),
    words_per_chunk: int | None = Form(None),
):
    """Update generation settings and reset session for re-processing.

    After calling this, connect to GET /api/process/{session_id} for SSE progress.
    """
    session = _get_session(session_id)

    # Update settings
    if voice:
        session["settings"]["voice"] = voice
    if words_per_chunk is not None:
        session["settings"]["max_words_per_chunk"] = words_per_chunk

    # Reset session state so /api/process will re-run the pipeline
    session["status"] = "uploaded"
    session["chunks"] = None
    session["chunks_with_timings"] = None
    session["chapters"] = None
    session["audio_generated_path"] = None
    session["video_path"] = None
    session["duration"] = None
    session["error"] = None
    session["progress_events"] = []
    session["processing_done"] = None

    return {"id": session_id, "status": "uploaded"}


# ---------------------------------------------------------------------------
# GET /api/process/{session_id}  --  Start pipeline + stream SSE progress
# ---------------------------------------------------------------------------

@app.get("/api/process/{session_id}")
async def process_session(session_id: str):
    """Run the pipeline for a session and stream progress as SSE.

    The frontend connects with EventSource to this endpoint.
    Named events: 'progress' and 'complete' (or 'error').
    """
    session = _get_session(session_id)

    if session["status"] == "ready":
        # Already processed -- send a single complete event
        async def already_done():
            data = {
                "id": session_id,
                "audio_url": f"/api/audio/{session_id}",
                "timestamps": session["chunks_with_timings"],
                "duration": session["duration"],
                "formatting": session.get("formatting", {}),
                "chapters": session.get("chapters"),
            }
            yield f"event: complete\ndata: {json.dumps(data)}\n\n"

        return StreamingResponse(already_done(), media_type="text/event-stream")

    session["status"] = "processing"
    done_event = asyncio.Event()
    session["processing_done"] = done_event
    session["progress_events"] = []

    async def event_generator():
        # Start the pipeline in a background thread
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, _run_pipeline, session_id)

        # Poll for progress events while the pipeline runs
        idx = 0
        while not done_event.is_set():
            await asyncio.sleep(0.15)
            events = session["progress_events"]
            while idx < len(events):
                evt = events[idx]
                idx += 1
                yield f"event: progress\ndata: {json.dumps(evt)}\n\n"

        # Drain any remaining progress events
        events = session["progress_events"]
        while idx < len(events):
            evt = events[idx]
            idx += 1
            yield f"event: progress\ndata: {json.dumps(evt)}\n\n"

        # Wait for the background task to finish and check for errors
        try:
            await task
        except Exception:
            pass

        # Send final event — use the (possibly updated) slug as ID
        final_id = session["id"]
        if session["status"] == "error":
            yield f"event: error\ndata: {json.dumps({'error': session['error']})}\n\n"
        else:
            data = {
                "id": final_id,
                "audio_url": f"/api/audio/{final_id}",
                "timestamps": session["chunks_with_timings"],
                "duration": session["duration"],
                "formatting": session.get("formatting", {}),
                "chapters": session.get("chapters"),
            }
            yield f"event: complete\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _run_pipeline(session_id: str) -> None:
    """Run the pipeline synchronously (called in a thread)."""
    session = sessions[session_id]
    done_event = session["processing_done"]

    def progress_callback(step: str, progress: float, message: str):
        session["progress_events"].append({
            "step": step,
            "progress": progress,
            "message": message,
        })

    try:
        settings_data = dict(session["settings"])
        settings = KaraokeSettings.from_dict(settings_data)

        pipeline = Pipeline(
            settings=settings,
            text_path=session["text_path"],
            audio_path=session["audio_path"],
            output_path=None,  # no video render during process
            progress_callback=progress_callback,
        )

        result = pipeline.run()

        session["text"] = result.text
        session["chunks"] = result.chunks
        session["chunks_with_timings"] = result.chunks_with_timings
        session["formatting"] = result.formatting or {}
        session["chapters"] = result.chapters
        session["audio_generated_path"] = result.audio_path
        session["duration"] = result.duration
        session["status"] = "ready"

        # Assign a readable slug (if still using temp hex ID)
        old_id = session["id"]
        if len(old_id) == 12 and all(c in "0123456789abcdef" for c in old_id):
            # Prefer filename, fall back to first words of text
            base_slug = _slugify_filename(session.get("original_filename")) \
                        or _slugify_text(result.text)
            slug = _unique_slug(base_slug)
            session["id"] = slug
            sessions[slug] = session
            del sessions[old_id]

        # Persist to disk
        _save_project(session)

    except Exception as exc:
        session["status"] = "error"
        session["error"] = str(exc)

    finally:
        done_event.set()


# ---------------------------------------------------------------------------
# POST /api/export/mp4/{session_id}  --  Start video render
# ---------------------------------------------------------------------------

# Export jobs (for MP4 rendering with separate progress tracking)
export_jobs: dict[str, dict[str, Any]] = {}


@app.post("/api/export/mp4/{session_id}")
async def export_mp4(session_id: str):
    """Start an MP4 export job. Returns a job_id for progress tracking."""
    session = _get_session(session_id)

    if session["status"] != "ready":
        raise HTTPException(status_code=400, detail="Session not ready; run /api/process first")

    if not session["chunks_with_timings"]:
        raise HTTPException(status_code=400, detail="No timestamp data available")

    job_id = _new_session_id()
    export_jobs[job_id] = {
        "session_id": session_id,
        "status": "rendering",
        "progress_events": [],
        "done_event": asyncio.Event(),
        "video_path": None,
        "error": None,
    }

    # Start render in background
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_export, job_id)

    return {"job_id": job_id, "status": "rendering"}


def _run_export(job_id: str) -> None:
    """Run video rendering synchronously (called in a thread)."""
    job = export_jobs[job_id]
    session = sessions[job["session_id"]]
    done_event = job["done_event"]

    def progress_callback(step: str, progress: float, message: str):
        job["progress_events"].append({
            "step": step,
            "progress": progress,
            "message": message,
        })

    try:
        settings = KaraokeSettings.from_dict(session["settings"])
        output_path = str(Path(session["work_dir"]) / "karaoke.mp4")

        audio_path = session.get("audio_generated_path") or session.get("audio_path")
        if not audio_path:
            raise ValueError("No audio file available for rendering")

        pipeline = Pipeline(
            settings=settings,
            text_path=session["text_path"],
            audio_path=audio_path,
            output_path=output_path,
            progress_callback=progress_callback,
        )

        # Only run the render step since we already have chunks_with_timings
        video_path = pipeline.render(session["chunks_with_timings"], audio_path)

        job["video_path"] = video_path
        session["video_path"] = video_path
        job["status"] = "complete"

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)

    finally:
        done_event.set()


@app.get("/api/export/progress/{job_id}")
async def export_progress(job_id: str):
    """Stream SSE progress for an MP4 export job."""
    if job_id not in export_jobs:
        raise HTTPException(status_code=404, detail=f"Export job {job_id} not found")

    job = export_jobs[job_id]
    done_event = job["done_event"]

    async def event_generator():
        idx = 0
        while not done_event.is_set():
            await asyncio.sleep(0.15)
            events = job["progress_events"]
            while idx < len(events):
                evt = events[idx]
                idx += 1
                yield f"event: progress\ndata: {json.dumps(evt)}\n\n"

        # Drain remaining events
        events = job["progress_events"]
        while idx < len(events):
            evt = events[idx]
            idx += 1
            yield f"event: progress\ndata: {json.dumps(evt)}\n\n"

        if job["status"] == "error":
            yield f"event: error\ndata: {json.dumps({'error': job['error']})}\n\n"
        else:
            session_id = job["session_id"]
            yield f"event: complete\ndata: {json.dumps({'download_url': f'/api/video/{session_id}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /api/timestamps/{session_id}  --  Return word timestamps + chunks
# ---------------------------------------------------------------------------

@app.get("/api/timestamps/{session_id}")
async def get_timestamps(session_id: str):
    """Return word timestamps and chunks as JSON for the player."""
    session = _get_session(session_id)

    if session["chunks_with_timings"] is None:
        raise HTTPException(status_code=400, detail="Session has not been processed yet")

    return {
        "chunks_with_timings": session["chunks_with_timings"],
        "chunks": session["chunks"],
        "duration": session["duration"],
        "formatting": session.get("formatting", {}),
        "chapters": session.get("chapters"),
    }


# ---------------------------------------------------------------------------
# GET /api/audio/{session_id}  --  Serve the audio file
# ---------------------------------------------------------------------------

@app.get("/api/audio/{session_id}")
async def get_audio(session_id: str):
    """Serve the audio file (generated or uploaded)."""
    session = _get_session(session_id)

    audio_path = session.get("audio_generated_path") or session.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    suffix = Path(audio_path).suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
    }
    media_type = media_types.get(suffix, "audio/mpeg")

    return FileResponse(audio_path, media_type=media_type, filename=f"audio{suffix}")


# ---------------------------------------------------------------------------
# GET /api/video/{session_id}  --  Serve the rendered MP4
# ---------------------------------------------------------------------------

@app.get("/api/video/{session_id}")
async def get_video(session_id: str):
    """Serve the rendered MP4 video."""
    session = _get_session(session_id)

    video_path = session.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=404, detail="Video not found; export it first")

    return FileResponse(video_path, media_type="video/mp4", filename="karaoke.mp4")


# ---------------------------------------------------------------------------
# GET /api/export/srt/{session_id}  --  Export SRT subtitles
# ---------------------------------------------------------------------------

@app.get("/api/export/srt/{session_id}")
async def get_srt(session_id: str):
    """Generate and serve an SRT subtitle file."""
    session = _get_session(session_id)

    if not session["chunks_with_timings"]:
        raise HTTPException(status_code=400, detail="No timestamp data; process the session first")

    srt_path = str(Path(session["work_dir"]) / "karaoke.srt")
    export_srt(session["chunks_with_timings"], srt_path)

    return FileResponse(srt_path, media_type="text/plain", filename="karaoke.srt")


# ---------------------------------------------------------------------------
# GET /api/export/vtt/{session_id}  --  Export WebVTT subtitles
# ---------------------------------------------------------------------------

@app.get("/api/export/vtt/{session_id}")
async def get_vtt(session_id: str):
    """Generate and serve a WebVTT subtitle file."""
    session = _get_session(session_id)

    if not session["chunks_with_timings"]:
        raise HTTPException(status_code=400, detail="No timestamp data; process the session first")

    vtt_path = str(Path(session["work_dir"]) / "karaoke.vtt")
    export_vtt(session["chunks_with_timings"], vtt_path)

    return FileResponse(vtt_path, media_type="text/vtt", filename="karaoke.vtt")


# ---------------------------------------------------------------------------
# GET /api/export/html/{session_id}  --  Export standalone HTML
# ---------------------------------------------------------------------------

@app.get("/api/export/html/{session_id}")
async def get_html(session_id: str):
    """Generate and serve a self-contained HTML karaoke player."""
    session = _get_session(session_id)

    if not session["chunks_with_timings"]:
        raise HTTPException(status_code=400, detail="No timestamp data; process the session first")

    audio_path = session.get("audio_generated_path") or session.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    title = _title_from_text(session.get("text") or session["id"])

    html_content = generate_standalone_html(
        title=title,
        chunks_with_timings=session["chunks_with_timings"],
        formatting=session.get("formatting", {}),
        audio_path=audio_path,
        duration=session.get("duration", 0),
    )

    # Save to project dir and serve
    html_path = Path(session["work_dir"]) / "karaoke.html"
    html_path.write_text(html_content)

    slug = session["id"]
    filename = f"{slug}.html"

    return FileResponse(
        str(html_path),
        media_type="text/html",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/projects  --  List all saved projects
# ---------------------------------------------------------------------------

@app.get("/api/projects")
async def list_projects():
    """Return a list of all saved projects (for the library view)."""
    projects = []
    for sid, session in sessions.items():
        if session["status"] != "ready":
            continue
        projects.append({
            "id": session["id"],
            "title": _title_from_text(session.get("text") or ""),
            "preview": (session.get("text") or "")[:120].replace("\n", " ").strip(),
            "duration": session.get("duration"),
            "created_at": session.get("created_at"),
            "word_count": len((session.get("text") or "").split()) if session.get("text") else None,
        })

    # Also read from disk for projects where text wasn't loaded into memory
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        meta_path = project_dir / "project.json"
        if not meta_path.exists():
            continue
        slug = project_dir.name
        # Skip if already in the list from sessions
        if any(p["id"] == slug for p in projects):
            continue
        try:
            meta = json.loads(meta_path.read_text())
            projects.append({
                "id": meta["id"],
                "title": meta.get("title", slug),
                "preview": meta.get("preview", ""),
                "duration": meta.get("duration"),
                "created_at": meta.get("created_at"),
                "word_count": meta.get("word_count"),
            })
        except Exception:
            pass

    # Sort newest first
    projects.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return {"projects": projects}


# ---------------------------------------------------------------------------
# GET /api/settings/themes  --  List available theme presets
# ---------------------------------------------------------------------------

@app.get("/api/settings/themes")
async def get_themes():
    """Return all available theme presets."""
    return {"themes": THEME_PRESETS}


# ---------------------------------------------------------------------------
# Static files and root
# ---------------------------------------------------------------------------

# Mount static files (CSS, JS, etc.)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    """Serve the main web UI."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/p/{session_id:path}")
async def project_page(session_id: str):
    """Serve the web UI for a specific project. JS reads the session_id from the URL."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(index_path), media_type="text/html")
