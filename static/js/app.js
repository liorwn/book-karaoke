/**
 * BookKaraokeApp — Main orchestrator.
 *
 * Manages application state, wires all modules together,
 * and provides demo mode with sample data.
 */

// -----------------------------------------------------------------------
// Demo timestamp data based on sample.txt
// Realistic word timings (~0.2-0.5s per word, with natural pauses)
// -----------------------------------------------------------------------

const DEMO_CHUNKS = [
  // Chunk 0: "I was sitting across from a CEO last year -- let's call him David -- in a glass-walled conference room overlooking downtown Austin."
  [
    { word: "I", start: 0.2, end: 0.35 },
    { word: "was", start: 0.35, end: 0.55 },
    { word: "sitting", start: 0.55, end: 0.90 },
    { word: "across", start: 0.90, end: 1.25 },
    { word: "from", start: 1.25, end: 1.45 },
    { word: "a", start: 1.45, end: 1.55 },
    { word: "CEO", start: 1.55, end: 1.95 },
    { word: "last", start: 1.95, end: 2.20 },
    { word: "year", start: 2.20, end: 2.55 },
    { word: "--", start: 2.55, end: 2.75 },
    { word: "let's", start: 2.75, end: 3.00 },
    { word: "call", start: 3.00, end: 3.25 },
    { word: "him", start: 3.25, end: 3.45 },
    { word: "David", start: 3.45, end: 3.85 },
    { word: "--", start: 3.85, end: 4.05 },
    { word: "in", start: 4.05, end: 4.20 },
    { word: "a", start: 4.20, end: 4.30 },
    { word: "glass-walled", start: 4.30, end: 4.85 },
    { word: "conference", start: 4.85, end: 5.30 },
    { word: "room", start: 5.30, end: 5.55 },
    { word: "overlooking", start: 5.55, end: 6.05 },
    { word: "downtown", start: 6.05, end: 6.45 },
    { word: "Austin.", start: 6.45, end: 6.90 },
  ],
  // Chunk 1: "His company does about forty million a year. Impressive team. Good culture. Growing."
  [
    { word: "His", start: 7.30, end: 7.50 },
    { word: "company", start: 7.50, end: 7.90 },
    { word: "does", start: 7.90, end: 8.15 },
    { word: "about", start: 8.15, end: 8.45 },
    { word: "forty", start: 8.45, end: 8.75 },
    { word: "million", start: 8.75, end: 9.10 },
    { word: "a", start: 9.10, end: 9.20 },
    { word: "year.", start: 9.20, end: 9.60 },
    { word: "Impressive", start: 9.80, end: 10.30 },
    { word: "team.", start: 10.30, end: 10.65 },
    { word: "Good", start: 10.85, end: 11.10 },
    { word: "culture.", start: 11.10, end: 11.55 },
    { word: "Growing.", start: 11.70, end: 12.15 },
  ],
  // Chunk 2: 'I asked him a simple question: "Walk me through what happens when a new customer signs up."'
  [
    { word: "I", start: 12.60, end: 12.75 },
    { word: "asked", start: 12.75, end: 13.05 },
    { word: "him", start: 13.05, end: 13.25 },
    { word: "a", start: 13.25, end: 13.35 },
    { word: "simple", start: 13.35, end: 13.70 },
    { word: "question:", start: 13.70, end: 14.15 },
    { word: "\u201CWalk", start: 14.35, end: 14.65 },
    { word: "me", start: 14.65, end: 14.80 },
    { word: "through", start: 14.80, end: 15.10 },
    { word: "what", start: 15.10, end: 15.30 },
    { word: "happens", start: 15.30, end: 15.65 },
    { word: "when", start: 15.65, end: 15.85 },
    { word: "a", start: 15.85, end: 15.95 },
    { word: "new", start: 15.95, end: 16.15 },
    { word: "customer", start: 16.15, end: 16.55 },
    { word: "signs", start: 16.55, end: 16.85 },
    { word: "up.\u201D", start: 16.85, end: 17.25 },
  ],
  // Chunk 3: 'He smiled. "Oh, that\'s easy. Sales closes the deal, hands it to onboarding, onboarding gets them set up, and then customer success takes over."'
  [
    { word: "He", start: 17.70, end: 17.90 },
    { word: "smiled.", start: 17.90, end: 18.30 },
    { word: "\u201COh,", start: 18.50, end: 18.80 },
    { word: "that's", start: 18.80, end: 19.10 },
    { word: "easy.", start: 19.10, end: 19.50 },
    { word: "Sales", start: 19.70, end: 20.00 },
    { word: "closes", start: 20.00, end: 20.35 },
    { word: "the", start: 20.35, end: 20.50 },
    { word: "deal,", start: 20.50, end: 20.85 },
    { word: "hands", start: 20.85, end: 21.15 },
    { word: "it", start: 21.15, end: 21.30 },
    { word: "to", start: 21.30, end: 21.45 },
    { word: "onboarding,", start: 21.45, end: 21.95 },
    { word: "onboarding", start: 21.95, end: 22.40 },
    { word: "gets", start: 22.40, end: 22.65 },
    { word: "them", start: 22.65, end: 22.85 },
    { word: "set", start: 22.85, end: 23.05 },
    { word: "up,", start: 23.05, end: 23.30 },
  ],
  // Chunk 4: 'and then customer success takes over."'
  [
    { word: "and", start: 23.30, end: 23.50 },
    { word: "then", start: 23.50, end: 23.75 },
    { word: "customer", start: 23.75, end: 24.15 },
    { word: "success", start: 24.15, end: 24.50 },
    { word: "takes", start: 24.50, end: 24.80 },
    { word: "over.\u201D", start: 24.80, end: 25.25 },
  ],
  // Chunk 5: '"Great," I said. "Now walk me through what actually happens."'
  [
    { word: "\u201CGreat,\u201D", start: 25.70, end: 26.10 },
    { word: "I", start: 26.10, end: 26.25 },
    { word: "said.", start: 26.25, end: 26.60 },
    { word: "\u201CNow", start: 26.80, end: 27.10 },
    { word: "walk", start: 27.10, end: 27.35 },
    { word: "me", start: 27.35, end: 27.50 },
    { word: "through", start: 27.50, end: 27.80 },
    { word: "what", start: 27.80, end: 28.05 },
    { word: "actually", start: 28.05, end: 28.45 },
    { word: "happens.\u201D", start: 28.45, end: 28.95 },
  ],
  // Chunk 6: "David paused. Thought about it. Then started talking. Slowly at first, then faster, like a thread unraveling."
  [
    { word: "David", start: 29.40, end: 29.80 },
    { word: "paused.", start: 29.80, end: 30.25 },
    { word: "Thought", start: 30.45, end: 30.80 },
    { word: "about", start: 30.80, end: 31.10 },
    { word: "it.", start: 31.10, end: 31.45 },
    { word: "Then", start: 31.65, end: 31.90 },
    { word: "started", start: 31.90, end: 32.25 },
    { word: "talking.", start: 32.25, end: 32.70 },
    { word: "Slowly", start: 32.90, end: 33.25 },
    { word: "at", start: 33.25, end: 33.40 },
    { word: "first,", start: 33.40, end: 33.75 },
    { word: "then", start: 33.75, end: 33.95 },
    { word: "faster,", start: 33.95, end: 34.35 },
    { word: "like", start: 34.35, end: 34.55 },
    { word: "a", start: 34.55, end: 34.65 },
    { word: "thread", start: 34.65, end: 34.95 },
    { word: "unraveling.", start: 34.95, end: 35.55 },
  ],
];

const DEMO_DURATION = 36.5; // seconds

// -----------------------------------------------------------------------
// App states
// -----------------------------------------------------------------------
const STATE = {
  IDLE: 'idle',
  UPLOADING: 'uploading',
  PROCESSING: 'processing',
  PLAYING: 'playing',
};

// -----------------------------------------------------------------------
// Main app class
// -----------------------------------------------------------------------

class BookKaraokeApp {
  constructor() {
    this.state = STATE.IDLE;
    this.player = null;
    this.renderer = null;
    this.settings = null;
    this.upload = null;
    this.exportCtrl = null;
    this.projectId = null;
    this.demoMode = false;
    // Search state
    this._searchMatches = [];   // [{chunkIndex, wordIndex, word}]
    this._searchCurrent = -1;
  }

  init() {
    // Initialize settings first (applies CSS vars)
    this.settings = new SettingsController();
    this.settings.bindUI();

    // Initialize player
    this.player = new KaraokePlayer();

    // Initialize renderer
    const container = document.getElementById('karaoke-text');
    const progressBar = document.getElementById('progress-bar-fill');
    this.renderer = new KaraokeRenderer(container, progressBar);

    // Initialize upload (pass settings callback so voice/wordsPerChunk are sent)
    const dropZone = document.getElementById('drop-zone');
    const uploadProgress = document.getElementById('upload-progress-bar');
    const uploadStatus = document.getElementById('upload-status');
    this.upload = new UploadHandler(dropZone, uploadProgress, uploadStatus, {
      getSettings: () => this.settings.getSettings(),
    });

    // Initialize export
    const exportContainer = document.getElementById('export-controls');
    this.exportCtrl = new ExportController(exportContainer);

    // Wire events
    this._wirePlayerEvents();
    this._wireUIEvents();
    this._wireSettingsEvents();
    this._wireUploadEvents();
    this._wireTextInput();
    this._wireSearch();

    // Settings toggle
    const settingsToggle = document.getElementById('settings-toggle');
    const settingsPanel = document.getElementById('settings-panel');
    if (settingsToggle && settingsPanel) {
      settingsToggle.addEventListener('click', () => {
        settingsPanel.classList.toggle('open');
      });
    }

    // Check if we're on a project URL (/p/{slug})
    const projectMatch = window.location.pathname.match(/^\/p\/(.+)$/);
    if (projectMatch) {
      this._loadFromUrl(decodeURIComponent(projectMatch[1]));
    } else {
      // Start in idle state
      this._showSection('upload-section');
      this._loadProjectLibrary();
    }

    // Handle browser back/forward navigation
    window.addEventListener('popstate', (e) => {
      if (e.state && e.state.projectId) {
        this._loadFromUrl(e.state.projectId);
      } else {
        this.player.pause();
        this.player.destroy();
        this._showSection('upload-section');
        this._setState(STATE.IDLE);
        this._loadProjectLibrary();
      }
    });

    console.log('[BookKaraoke] App initialized');
  }

  /**
   * Launch demo mode with hardcoded sample data.
   */
  startDemo() {
    this.demoMode = true;
    this._showSection('player-section');
    this._setState(STATE.PLAYING);

    // Set timestamps
    this.player.setTimestamps(DEMO_CHUNKS);
    this.renderer.setChunks(DEMO_CHUNKS);

    // Create a silent audio buffer for demo
    this._createDemoAudio(DEMO_DURATION).then(() => {
      // Show first chunk
      this.renderer.showChunk(0, false);
      this._showNotification('Demo mode: press Play or Space to start', 'info');
    });
  }

  /**
   * Load external timestamp JSON and audio.
   */
  async loadProject(audioUrl, timestamps, formatting) {
    this.demoMode = false;
    this._showSection('player-section');
    this._setState(STATE.PLAYING);

    // Track generation settings for re-generate detection
    const s = this.settings.getSettings();
    this._lastGenVoice = s.voice;
    this._lastGenWpc = s.wordsPerChunk;
    const regenBtn = document.getElementById('regenerate-btn');
    if (regenBtn) regenBtn.disabled = true;

    this.player.setTimestamps(timestamps);
    this.renderer.setChunks(timestamps);
    this.renderer.setFormatting(formatting || {});
    await this.player.loadAudio(audioUrl);
    this.renderer.showChunk(0, false);
  }

  // --- Private ---

  // --- Project Library ---

  async _loadProjectLibrary() {
    const container = document.getElementById('projects-list');
    const library = document.getElementById('projects-library');
    if (!container || !library) return;

    try {
      const resp = await fetch('/api/projects');
      if (!resp.ok) return;
      const data = await resp.json();
      const projects = data.projects || [];

      if (projects.length === 0) {
        library.classList.add('hidden');
        return;
      }

      library.classList.remove('hidden');
      container.innerHTML = '';

      for (const p of projects) {
        const card = document.createElement('a');
        card.href = `/p/${encodeURIComponent(p.id)}`;
        card.className = 'project-card';
        card.addEventListener('click', (e) => {
          e.preventDefault();
          history.pushState({ projectId: p.id }, '', `/p/${encodeURIComponent(p.id)}`);
          this._loadFromUrl(p.id);
        });

        const duration = p.duration ? this._formatTime(p.duration) : '';
        const meta = [
          duration ? duration : null,
          p.word_count ? `${p.word_count} words` : null,
        ].filter(Boolean).join(' · ');

        card.innerHTML = `
          <div class="project-icon">&#9835;</div>
          <div class="project-info">
            <div class="project-title">${this._escapeHtml(p.title || p.id)}</div>
            ${meta ? `<div class="project-meta">${meta}</div>` : ''}
          </div>
          <div class="project-arrow">&rsaquo;</div>
        `;
        container.appendChild(card);
      }
    } catch (err) {
      console.warn('[BookKaraoke] Failed to load projects:', err);
    }
  }

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // --- Search ---

  _wireSearch() {
    const toggle = document.getElementById('search-toggle');
    const closeBtn = document.getElementById('search-close');
    const prevBtn = document.getElementById('search-prev');
    const nextBtn = document.getElementById('search-next');
    const input = document.getElementById('search-input');

    if (toggle) {
      toggle.addEventListener('click', () => this._openSearch());
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this._closeSearch());
    }
    if (prevBtn) {
      prevBtn.addEventListener('click', () => this._searchNav(-1));
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', () => this._searchNav(1));
    }
    if (input) {
      input.addEventListener('input', () => this._runSearch(input.value));
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this._searchNav(e.shiftKey ? -1 : 1);
        }
      });
    }
  }

  _openSearch() {
    const bar = document.getElementById('search-bar');
    const input = document.getElementById('search-input');
    if (!bar) return;
    bar.classList.remove('hidden');
    // Trigger reflow so transition runs
    bar.offsetHeight;
    bar.classList.add('open');
    if (input) {
      input.focus();
      input.select();
    }
  }

  _closeSearch() {
    const bar = document.getElementById('search-bar');
    if (!bar || !bar.classList.contains('open')) return;
    bar.classList.remove('open');
    setTimeout(() => bar.classList.add('hidden'), 250);
    this._clearSearchHighlights();
    this._searchMatches = [];
    this._searchCurrent = -1;
    const count = document.getElementById('search-count');
    if (count) count.textContent = '';
  }

  _runSearch(query) {
    this._clearSearchHighlights();
    this._searchMatches = [];
    this._searchCurrent = -1;

    const count = document.getElementById('search-count');
    const q = query.trim().toLowerCase();

    if (!q || !this.player || !this.player.chunks) {
      if (count) count.textContent = '';
      return;
    }

    // Find all matching words across all chunks
    const chunks = this.player.chunks;
    for (let ci = 0; ci < chunks.length; ci++) {
      for (let wi = 0; wi < chunks[ci].length; wi++) {
        const word = chunks[ci][wi].word || '';
        if (word.toLowerCase().includes(q)) {
          this._searchMatches.push({
            chunkIndex: ci,
            wordIndex: wi,
            start: chunks[ci][wi].start,
          });
        }
      }
    }

    if (count) {
      count.textContent = this._searchMatches.length > 0
        ? `${this._searchMatches.length} match${this._searchMatches.length !== 1 ? 'es' : ''}`
        : 'No matches';
    }

    // Auto-navigate to first match
    if (this._searchMatches.length > 0) {
      this._searchCurrent = 0;
      this._goToSearchMatch(0);
    }
  }

  _searchNav(direction) {
    if (this._searchMatches.length === 0) return;
    this._searchCurrent = (this._searchCurrent + direction + this._searchMatches.length) % this._searchMatches.length;
    this._goToSearchMatch(this._searchCurrent);

    const count = document.getElementById('search-count');
    if (count) {
      count.textContent = `${this._searchCurrent + 1} / ${this._searchMatches.length}`;
    }
  }

  _goToSearchMatch(idx) {
    const match = this._searchMatches[idx];
    if (!match) return;

    // Seek audio to the matched word
    this.player.seek(Math.max(0, match.start - 0.3));

    // Show the chunk containing the match
    this.renderer.showChunk(match.chunkIndex, false);

    // Highlight matching words in current chunk
    this._highlightSearchInChunk(match.chunkIndex, idx);
  }

  _highlightSearchInChunk(chunkIndex, currentMatchIdx) {
    this._clearSearchHighlights();

    const spans = this.renderer.wordSpans;
    if (!spans) return;

    // Find all matches in this chunk and highlight them
    for (let i = 0; i < this._searchMatches.length; i++) {
      const m = this._searchMatches[i];
      if (m.chunkIndex !== chunkIndex) continue;
      if (m.wordIndex < spans.length) {
        spans[m.wordIndex].classList.add('search-match');
        if (i === currentMatchIdx) {
          spans[m.wordIndex].classList.add('search-current');
        }
      }
    }
  }

  _clearSearchHighlights() {
    document.querySelectorAll('.search-match, .search-current').forEach(el => {
      el.classList.remove('search-match', 'search-current');
    });
  }

  async _reprocess() {
    const s = this.settings.getSettings();
    this.player.pause();
    this.player.destroy();

    // Close settings panel
    const panel = document.getElementById('settings-panel');
    if (panel) panel.classList.remove('open');

    // Show processing section
    this._setState(STATE.PROCESSING);
    this._showSection('processing-section');
    this._resetProcessingUI();

    try {
      // Tell server to update settings and reset session
      const formData = new FormData();
      if (s.voice) formData.append('voice', s.voice);
      if (s.wordsPerChunk != null) formData.append('words_per_chunk', String(s.wordsPerChunk));

      const resp = await fetch(`/api/reprocess/${this.projectId}`, {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        throw new Error(`Re-process failed: ${resp.statusText}`);
      }

      // Listen for SSE progress (same as initial upload)
      this._listenForReprocess(this.projectId);
    } catch (err) {
      this._showNotification(err.message, 'error');
      this._showSection('player-section');
      this._setState(STATE.PLAYING);
    }
  }

  _listenForReprocess(sessionId) {
    const evtSource = new EventSource(`/api/process/${sessionId}`);
    let finished = false;

    evtSource.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data);
      this._updateProcessingStep(data.step, data.progress, data.message);
    });

    evtSource.addEventListener('complete', (e) => {
      finished = true;
      evtSource.close();
      const data = JSON.parse(e.data);

      this._setState(STATE.PLAYING);
      this._showSection('player-section');

      // Update URL
      history.replaceState({ projectId: sessionId }, '', `/p/${sessionId}`);

      if (data.audio_url && data.timestamps) {
        this.loadProject(data.audio_url, data.timestamps, data.formatting);
      }
    });

    evtSource.addEventListener('error', (e) => {
      if (e instanceof MessageEvent && e.data) {
        finished = true;
        evtSource.close();
        const data = JSON.parse(e.data);
        this._showNotification(data.error || 'Re-processing failed', 'error');
        this._showSection('player-section');
        this._setState(STATE.PLAYING);
      }
    });

    evtSource.onerror = () => {
      if (!finished) {
        evtSource.close();
        this._showNotification('Connection lost during re-processing', 'error');
        this._showSection('player-section');
        this._setState(STATE.PLAYING);
      }
    };
  }

  async _loadFromUrl(sessionId) {
    this._showSection('player-section');
    this._setState(STATE.PLAYING);

    try {
      const resp = await fetch(`/api/timestamps/${sessionId}`);
      if (!resp.ok) {
        throw new Error(resp.status === 404 ? 'Project not found' : 'Failed to load project');
      }
      const data = await resp.json();

      this.projectId = sessionId;
      this.exportCtrl.setProjectId(sessionId);
      await this.loadProject(
        `/api/audio/${sessionId}`,
        data.chunks_with_timings,
        data.formatting,
      );
    } catch (err) {
      this._showNotification(err.message, 'error');
      this._showSection('upload-section');
      this._setState(STATE.IDLE);
      history.replaceState(null, '', '/');
    }
  }

  async _createDemoAudio(duration) {
    // Use AudioContext to create a silent buffer, then convert to blob
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const sampleRate = ctx.sampleRate;
    const numSamples = Math.ceil(duration * sampleRate);
    const buffer = ctx.createBuffer(1, numSamples, sampleRate);

    // Add very subtle ambient tone so audio element works
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < numSamples; i++) {
      channel[i] = Math.sin(i / sampleRate * 2 * Math.PI * 220) * 0.001;
    }

    // Encode as WAV
    const wav = this._bufferToWav(buffer);
    const blob = new Blob([wav], { type: 'audio/wav' });

    await this.player.loadAudio(blob);
    ctx.close();
  }

  _bufferToWav(buffer) {
    const numChannels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;
    const format = 1; // PCM
    const bitsPerSample = 16;
    const data = buffer.getChannelData(0);
    const dataLength = data.length * (bitsPerSample / 8);
    const headerLength = 44;
    const totalLength = headerLength + dataLength;

    const arrayBuffer = new ArrayBuffer(totalLength);
    const view = new DataView(arrayBuffer);

    // RIFF header
    this._writeString(view, 0, 'RIFF');
    view.setUint32(4, totalLength - 8, true);
    this._writeString(view, 8, 'WAVE');

    // fmt chunk
    this._writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, format, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * (bitsPerSample / 8), true);
    view.setUint16(32, numChannels * (bitsPerSample / 8), true);
    view.setUint16(34, bitsPerSample, true);

    // data chunk
    this._writeString(view, 36, 'data');
    view.setUint32(40, dataLength, true);

    let offset = 44;
    for (let i = 0; i < data.length; i++) {
      const sample = Math.max(-1, Math.min(1, data[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
      offset += 2;
    }

    return arrayBuffer;
  }

  _writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  _wirePlayerEvents() {
    this.player.addEventListener('timeupdate', (e) => {
      const { time, progress, chunkIndex, wordIndex, fadeAlpha } = e.detail;
      this.renderer.updateTime(time, chunkIndex, wordIndex, fadeAlpha);
      this.renderer.updateProgress(progress);

      // Update time display
      const currentEl = document.getElementById('time-current');
      const totalEl = document.getElementById('time-total');
      if (currentEl) currentEl.textContent = this._formatTime(time);
      if (totalEl) totalEl.textContent = this._formatTime(this.player.duration);
    });

    this.player.addEventListener('chunkchange', (e) => {
      const { chunkIndex } = e.detail;
      this.renderer.showChunk(chunkIndex);
    });

    this.player.addEventListener('play', () => {
      const btn = document.getElementById('play-btn');
      if (btn) btn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
    });

    this.player.addEventListener('pause', () => {
      const btn = document.getElementById('play-btn');
      if (btn) btn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6"><polygon points="5,3 19,12 5,21"/></svg>';
    });

    this.player.addEventListener('ended', () => {
      const btn = document.getElementById('play-btn');
      if (btn) btn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6"><polygon points="5,3 19,12 5,21"/></svg>';
    });
  }

  _wireUIEvents() {
    // Play/pause button
    const playBtn = document.getElementById('play-btn');
    if (playBtn) {
      playBtn.addEventListener('click', () => this.player.toggle());
    }

    // Skip back 5s
    const skipBackBtn = document.getElementById('skip-back-btn');
    if (skipBackBtn) {
      skipBackBtn.addEventListener('click', () => {
        this.player.seek(this.player.currentTime - 5);
      });
    }

    // Skip forward 5s
    const skipFwdBtn = document.getElementById('skip-fwd-btn');
    if (skipFwdBtn) {
      skipFwdBtn.addEventListener('click', () => {
        this.player.seek(this.player.currentTime + 5);
      });
    }

    // Progress bar click-to-seek
    const progressTrack = document.getElementById('progress-bar-track');
    if (progressTrack) {
      progressTrack.addEventListener('click', (e) => {
        const rect = progressTrack.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        this.player.seek(pct * this.player.duration);
      });
    }

    // Volume slider
    const volumeSlider = document.getElementById('volume-slider');
    if (volumeSlider) {
      volumeSlider.addEventListener('input', () => {
        this.player.setVolume(volumeSlider.value / 100);
      });
    }

    // Speed control — cycles through rates on click
    const speedBtn = document.getElementById('speed-btn');
    if (speedBtn) {
      const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2];
      let speedIdx = 2; // start at 1x
      speedBtn.addEventListener('click', () => {
        speedIdx = (speedIdx + 1) % speeds.length;
        const rate = speeds[speedIdx];
        this.player.setPlaybackRate(rate);
        speedBtn.textContent = rate === 1 ? '1x' : rate + 'x';
        speedBtn.classList.toggle('speed-active', rate !== 1);
      });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      // Ctrl/Cmd+F: open search (works from anywhere)
      if ((e.ctrlKey || e.metaKey) && e.key === 'f' && this.state === STATE.PLAYING) {
        e.preventDefault();
        this._openSearch();
        return;
      }

      // Escape: close search
      if (e.key === 'Escape') {
        this._closeSearch();
        return;
      }

      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

      switch (e.code) {
        case 'Space':
          e.preventDefault();
          this.player.toggle();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          this.player.seek(this.player.currentTime - 5);
          break;
        case 'ArrowRight':
          e.preventDefault();
          this.player.seek(this.player.currentTime + 5);
          break;
      }
    });

    // Demo button
    const demoBtn = document.getElementById('demo-btn');
    if (demoBtn) {
      demoBtn.addEventListener('click', () => this.startDemo());
    }

    // Back to upload
    const backBtn = document.getElementById('back-btn');
    if (backBtn) {
      backBtn.addEventListener('click', () => {
        this.player.pause();
        this.player.destroy();
        this._showSection('upload-section');
        this._setState(STATE.IDLE);
        // Reset upload progress
        const bar = document.getElementById('upload-progress-bar');
        const status = document.getElementById('upload-status');
        if (bar) bar.style.width = '0%';
        if (status) status.textContent = '';
        // Navigate back to root
        history.pushState(null, '', '/');
        this._loadProjectLibrary();
      });
    }
  }

  _wireSettingsEvents() {
    this.settings.onChange((s) => {
      this.renderer.applySettings(s);
    });

    // Track generation settings changes to enable Re-generate button
    this._lastGenVoice = null;
    this._lastGenWpc = null;

    const regenBtn = document.getElementById('regenerate-btn');
    const voiceSelect = document.getElementById('setting-voice');
    const wpcSlider = document.getElementById('setting-words-per-chunk');

    const checkRegenNeeded = () => {
      if (!regenBtn || !this.projectId) return;
      const s = this.settings.getSettings();
      const changed = (this._lastGenVoice && s.voice !== this._lastGenVoice) ||
                      (this._lastGenWpc && s.wordsPerChunk !== this._lastGenWpc);
      regenBtn.disabled = !changed;
    };

    if (voiceSelect) voiceSelect.addEventListener('change', checkRegenNeeded);
    if (wpcSlider) wpcSlider.addEventListener('input', checkRegenNeeded);

    if (regenBtn) {
      regenBtn.addEventListener('click', () => {
        if (!this.projectId) return;
        this._reprocess();
      });
    }
  }

  _wireTextInput() {
    const textarea = document.getElementById('text-input');
    const charCount = document.getElementById('char-count');
    const generateBtn = document.getElementById('generate-btn');

    if (!textarea || !generateBtn) return;

    textarea.addEventListener('input', () => {
      const len = textarea.value.length;
      if (charCount) charCount.textContent = `${len} character${len !== 1 ? 's' : ''}`;
      generateBtn.disabled = len < 10;
    });

    generateBtn.addEventListener('click', () => {
      const text = textarea.value.trim();
      if (text.length >= 10) {
        this.upload.handleText(text);
      }
    });
  }

  _wireUploadEvents() {
    this.upload.onProgress((data) => {
      // Show processing section on first progress event
      if (this.state !== STATE.PROCESSING) {
        this._setState(STATE.PROCESSING);
        this._showSection('processing-section');
        this._resetProcessingUI();
      }
      this._updateProcessingStep(data.step, data.progress, data.message);
    });

    this.upload.onComplete((data) => {
      this._setState(STATE.PLAYING);
      this._showSection('player-section');
      this.projectId = data.id;
      this.exportCtrl.setProjectId(data.id);

      // Update URL to dedicated project page
      if (data.id) {
        history.pushState({ projectId: data.id }, '', `/p/${data.id}`);
      }

      if (data.audio_url && data.timestamps) {
        this.loadProject(data.audio_url, data.timestamps, data.formatting);
      }
    });

    this.upload.onError((err) => {
      this._showNotification(err.message, 'error');
      this._showSection('upload-section');
      this._setState(STATE.IDLE);
    });

    // Cancel button
    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        this._showSection('upload-section');
        this._setState(STATE.IDLE);
      });
    }
  }

  _resetProcessingUI() {
    // Reset all steps to inactive
    document.querySelectorAll('.pipeline-step').forEach(el => {
      el.classList.remove('step-active', 'step-complete');
    });
    const bar = document.getElementById('processing-progress-bar');
    if (bar) bar.style.width = '0%';
    const status = document.getElementById('processing-status');
    if (status) status.textContent = 'Starting pipeline...';
  }

  _updateProcessingStep(step, progress, message) {
    const stepMap = {
      upload: 'tts',
      read_text: 'tts',
      tts: 'tts',
      align: 'align',
      alignment: 'align',
      chunk: 'chunk',
      chunking: 'chunk',
      done: 'chunk',
    };
    const mapped = stepMap[step] || step;
    const stepOrder = ['tts', 'align', 'chunk'];
    const currentIdx = stepOrder.indexOf(mapped);

    // Update step indicators
    document.querySelectorAll('.pipeline-step').forEach(el => {
      const s = el.dataset.step;
      const idx = stepOrder.indexOf(s);
      el.classList.remove('step-active', 'step-complete');
      if (idx < currentIdx) {
        el.classList.add('step-complete');
      } else if (idx === currentIdx) {
        el.classList.add('step-active');
      }
    });

    // Update the active step's detail text with the message
    if (message && currentIdx >= 0) {
      const activeStep = document.querySelector(`.pipeline-step[data-step="${stepOrder[currentIdx]}"]`);
      if (activeStep) {
        const detail = activeStep.querySelector('.step-detail');
        if (detail) detail.textContent = message;
      }
    }

    // Calculate overall progress: each step is ~33% of total
    if (progress != null && currentIdx >= 0) {
      const stepWeight = 100 / stepOrder.length;
      const overall = (currentIdx * stepWeight) + (progress * stepWeight);
      const bar = document.getElementById('processing-progress-bar');
      if (bar) bar.style.width = Math.min(100, overall) + '%';
    }

    const status = document.getElementById('processing-status');
    if (status && message) status.textContent = message;
  }

  _setState(newState) {
    this.state = newState;
    document.body.dataset.state = newState;
  }

  _showSection(sectionId) {
    document.querySelectorAll('.app-section').forEach(s => {
      s.classList.toggle('hidden', s.id !== sectionId);
    });
  }

  _showNotification(message, type = 'info') {
    const notif = document.getElementById('notification');
    if (!notif) return;
    notif.textContent = message;
    notif.className = `notification notification-${type} show`;
    setTimeout(() => notif.classList.remove('show'), 4000);
  }

  _formatTime(seconds) {
    if (!seconds || !isFinite(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
  window.app = new BookKaraokeApp();
  window.app.init();
});
