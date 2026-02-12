"""
Generate a self-contained HTML file for a karaoke project.

The output is a single .html file with all CSS, JS, and audio embedded
inline. It works by double-clicking — no server or special software needed.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path


def generate_standalone_html(
    title: str,
    chunks_with_timings: list,
    formatting: dict,
    audio_path: str,
    duration: float,
) -> str:
    """Build a self-contained HTML string with embedded audio and player."""

    # Encode audio as base64 data URI
    audio_bytes = Path(audio_path).read_bytes()
    suffix = Path(audio_path).suffix.lower()
    mime_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }
    mime = mime_types.get(suffix, "audio/mpeg")
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    audio_data_uri = f"data:{mime};base64,{audio_b64}"

    # Serialize data
    chunks_json = json.dumps(chunks_with_timings)
    formatting_json = json.dumps(formatting)

    # Read player.js and renderer.js
    js_dir = Path(__file__).parent.parent / "static" / "js"
    player_js = (js_dir / "player.js").read_text()
    renderer_js = (js_dir / "renderer.js").read_text()

    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_title} — Book Karaoke</title>
<style>
{_STANDALONE_CSS}
</style>
</head>
<body>
<div class="player-wrapper">
  <div class="karaoke-display">
    <div id="karaoke-text"></div>
  </div>
  <div class="progress-container">
    <div id="progress-bar-track">
      <div id="progress-bar-fill"></div>
    </div>
    <div class="time-display">
      <span id="time-current">0:00</span>
      <span id="time-total">0:00</span>
    </div>
  </div>
  <div class="transport-bar">
    <div class="transport-row">
      <div class="volume-control">
        <svg viewBox="0 0 24 24" fill="currentColor" class="vol-icon">
          <path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/>
        </svg>
        <input type="range" id="volume-slider" min="0" max="100" value="80">
      </div>
      <div class="transport-controls">
        <button id="skip-back-btn" class="transport-btn" title="Back 5s">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.5 8V4l-6 6 6 6v-4c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4.5c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
        </button>
        <button id="play-btn" class="transport-btn play-btn" title="Play / Pause">
          <svg id="play-icon" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
        </button>
        <button id="skip-fwd-btn" class="transport-btn" title="Forward 5s">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.5 8V4l6 6-6 6v-4c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z"/></svg>
        </button>
      </div>
      <div class="speed-control">
        <button id="speed-btn" class="speed-btn" title="Playback speed">1x</button>
      </div>
    </div>
  </div>
  <div class="title-bar">{escaped_title}</div>
</div>

<script>
// --- Embedded player engine ---
{player_js}

// --- Embedded renderer ---
{renderer_js}

// --- Embedded data ---
const CHUNKS = {chunks_json};
const FORMATTING = {formatting_json};
const AUDIO_SRC = "{audio_data_uri}";

// --- Standalone bootstrap ---
(function() {{
  const player = new KaraokePlayer();
  const container = document.getElementById('karaoke-text');
  const progressBar = document.getElementById('progress-bar-fill');
  const renderer = new KaraokeRenderer(container, progressBar);

  player.setTimestamps(CHUNKS);
  renderer.setChunks(CHUNKS);
  renderer.setFormatting(FORMATTING);

  player.loadAudio(AUDIO_SRC).then(() => {{
    renderer.showChunk(0, false);
    document.getElementById('time-total').textContent = formatTime(player.duration);
  }});

  // Time updates
  player.addEventListener('timeupdate', (e) => {{
    const {{ time, progress, chunkIndex, wordIndex, fadeAlpha }} = e.detail;
    renderer.updateTime(time, chunkIndex, wordIndex, fadeAlpha);
    renderer.updateProgress(progress);
    document.getElementById('time-current').textContent = formatTime(time);
  }});

  player.addEventListener('chunkchange', (e) => {{
    renderer.showChunk(e.detail.chunkIndex);
  }});

  const playIcon = '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>';
  const pauseIcon = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';

  player.addEventListener('play', () => {{
    document.getElementById('play-btn').innerHTML = pauseIcon;
  }});
  player.addEventListener('pause', () => {{
    document.getElementById('play-btn').innerHTML = playIcon;
  }});
  player.addEventListener('ended', () => {{
    document.getElementById('play-btn').innerHTML = playIcon;
  }});

  // Controls
  document.getElementById('play-btn').addEventListener('click', () => player.toggle());
  document.getElementById('skip-back-btn').addEventListener('click', () => player.seek(player.currentTime - 5));
  document.getElementById('skip-fwd-btn').addEventListener('click', () => player.seek(player.currentTime + 5));

  document.getElementById('progress-bar-track').addEventListener('click', (e) => {{
    const rect = e.currentTarget.getBoundingClientRect();
    player.seek((e.clientX - rect.left) / rect.width * player.duration);
  }});

  document.getElementById('volume-slider').addEventListener('input', (e) => {{
    player.setVolume(e.target.value / 100);
  }});

  // Speed
  const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2];
  let speedIdx = 2;
  document.getElementById('speed-btn').addEventListener('click', () => {{
    speedIdx = (speedIdx + 1) % speeds.length;
    const rate = speeds[speedIdx];
    player.setPlaybackRate(rate);
    const btn = document.getElementById('speed-btn');
    btn.textContent = rate === 1 ? '1x' : rate + 'x';
    btn.classList.toggle('speed-active', rate !== 1);
  }});

  // Keyboard
  document.addEventListener('keydown', (e) => {{
    if (e.code === 'Space') {{ e.preventDefault(); player.toggle(); }}
    if (e.code === 'ArrowLeft') {{ e.preventDefault(); player.seek(player.currentTime - 5); }}
    if (e.code === 'ArrowRight') {{ e.preventDefault(); player.seek(player.currentTime + 5); }}
  }});

  function formatTime(s) {{
    if (!s || !isFinite(s)) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ':' + sec.toString().padStart(2, '0');
  }}
}})();
</script>
</body>
</html>"""


_STANDALONE_CSS = """
:root {
  --karaoke-bg: #1a1a2e;
  --karaoke-highlight: #FFD700;
  --karaoke-spoken: #BBBBBB;
  --karaoke-upcoming: #555555;
  --karaoke-font-size: 48px;
  --progress: 0%;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d0d1a;
  color: #e0e0e0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  margin: 0;
  min-height: 100vh;
}
.player-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.karaoke-display {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--karaoke-bg);
  padding: 40px;
  min-height: 50vh;
  transition: background-color 0.4s;
}
#karaoke-text {
  text-align: center;
  font-size: var(--karaoke-font-size);
  line-height: 1.5;
  max-width: 900px;
  width: 100%;
  transition: opacity 0.25s;
}
.karaoke-text-block { display: inline; }
.karaoke-word {
  display: inline;
  transition: color 0.15s, text-shadow 0.15s;
}
.word-upcoming { color: var(--karaoke-upcoming); }
.word-spoken { color: var(--karaoke-spoken); }
.word-active {
  color: var(--karaoke-highlight);
  text-shadow: 0 0 20px color-mix(in srgb, var(--karaoke-highlight) 40%, transparent),
               0 0 40px color-mix(in srgb, var(--karaoke-highlight) 20%, transparent);
}
.word-bold { font-weight: 700; }
.word-italic { font-style: italic; }
.word-bold-italic { font-weight: 700; font-style: italic; }
.chunk-fade-out { animation: fadeOut 0.2s ease-out forwards; }
.chunk-fade-in { animation: fadeIn 0.25s ease-in forwards; }
@keyframes fadeOut { from{opacity:1;transform:translateY(0)} to{opacity:0;transform:translateY(-8px)} }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
.progress-container { padding: 0 24px; margin-bottom: 8px; }
#progress-bar-track {
  height: 4px; background: #222; border-radius: 2px;
  cursor: pointer; position: relative; overflow: hidden;
}
#progress-bar-track:hover { height: 6px; }
#progress-bar-fill {
  height: 100%; width: var(--progress);
  background: var(--karaoke-highlight); border-radius: 2px;
  transition: width 0.1s linear;
}
.time-display {
  display: flex; justify-content: space-between;
  font-size: 12px; color: #666; padding: 4px 24px 0;
  font-variant-numeric: tabular-nums;
}
.transport-bar {
  background: #111118; border-top: 1px solid #222; padding: 16px 24px;
}
.transport-row {
  display: flex; align-items: center; justify-content: space-between;
}
.transport-controls {
  display: flex; align-items: center; justify-content: center; gap: 16px;
}
.transport-btn {
  background: none; border: none; color: #ccc; cursor: pointer;
  padding: 8px; border-radius: 50%; transition: background 0.2s, color 0.2s;
  display: flex; align-items: center; justify-content: center;
}
.transport-btn:hover { background: rgba(255,255,255,0.1); color: #fff; }
.transport-btn svg { width: 24px; height: 24px; }
.play-btn {
  width: 56px; height: 56px;
  background: var(--karaoke-highlight) !important; color: #000 !important;
  border-radius: 50%;
}
.play-btn:hover { background: color-mix(in srgb, var(--karaoke-highlight) 85%, white) !important; }
.play-btn svg { width: 28px; height: 28px; }
.volume-control { display: flex; align-items: center; gap: 8px; width: 120px; }
.vol-icon { width: 16px; height: 16px; color: #555; }
#volume-slider { width: 80px; accent-color: var(--karaoke-highlight); }
.speed-control { display: flex; align-items: center; justify-content: flex-end; width: 80px; }
.speed-btn {
  background: none; border: 1px solid #333; color: #999;
  padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.2s; min-width: 48px; text-align: center;
}
.speed-btn:hover { border-color: #555; color: #ccc; }
.speed-btn.speed-active { border-color: var(--karaoke-highlight); color: var(--karaoke-highlight); }
.title-bar {
  text-align: center; font-size: 12px; color: #444;
  padding: 8px; background: #0a0a12; border-top: 1px solid #1a1a22;
}
@media (max-width: 768px) {
  #karaoke-text { font-size: calc(var(--karaoke-font-size) * 0.65); padding: 0 16px; }
  .karaoke-display { padding: 24px 16px; min-height: 40vh; }
  .play-btn { width: 48px; height: 48px; }
}
@media (max-width: 480px) {
  #karaoke-text { font-size: calc(var(--karaoke-font-size) * 0.5); line-height: 1.4; }
}
"""
