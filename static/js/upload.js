/**
 * UploadHandler — Drag-and-drop file upload with progress tracking.
 *
 * Posts files to /api/upload, then listens for SSE progress on /api/process.
 *
 * Options:
 *   getSettings — callback returning { voice, wordsPerChunk } to include in upload
 */

class UploadHandler {
  constructor(dropZoneEl, progressBarEl, statusEl, options = {}) {
    this.dropZone = dropZoneEl;
    this.progressBar = progressBarEl;
    this.statusEl = statusEl;
    this._onComplete = null;
    this._onError = null;
    this._onProgress = null;
    this._getSettings = options.getSettings || null;

    if (this.dropZone) {
      this._bindEvents();
    }
  }

  onComplete(fn) { this._onComplete = fn; }
  onError(fn) { this._onError = fn; }
  onProgress(fn) { this._onProgress = fn; }

  /**
   * Submit raw text as if it were a .txt file upload.
   */
  handleText(text) {
    const blob = new Blob([text], { type: 'text/plain' });
    const file = new File([blob], 'input.txt', { type: 'text/plain' });
    this._handleFile(file);
  }

  _bindEvents() {
    const dz = this.dropZone;

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
      dz.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
      });
    });

    // Highlight on drag over
    ['dragenter', 'dragover'].forEach(evt => {
      dz.addEventListener(evt, () => dz.classList.add('drag-over'));
    });

    ['dragleave', 'drop'].forEach(evt => {
      dz.addEventListener(evt, () => dz.classList.remove('drag-over'));
    });

    // Handle drop
    dz.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files.length > 0) this._handleFile(files[0]);
    });

    // Handle click to upload
    const fileInput = dz.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) this._handleFile(e.target.files[0]);
      });
    }

    dz.addEventListener('click', () => {
      if (fileInput) fileInput.click();
    });
  }

  async _handleFile(file) {
    this._setStatus(`Uploading ${file.name}...`);
    this._setProgress(0);

    // Detect file type
    const ext = file.name.split('.').pop().toLowerCase();
    const typeMap = {
      txt: 'text', md: 'text', epub: 'epub',
      mp3: 'audio', wav: 'audio', m4a: 'audio', ogg: 'audio',
      pdf: 'pdf',
    };
    const fileType = typeMap[ext] || 'unknown';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', fileType);

    // Include user-selected settings
    if (this._getSettings) {
      const settings = this._getSettings();
      if (settings.voice) {
        formData.append('voice', settings.voice);
      }
      if (settings.wordsPerChunk != null) {
        formData.append('words_per_chunk', String(settings.wordsPerChunk));
      }
    }

    try {
      const resp = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        throw new Error(`Upload failed: ${resp.statusText}`);
      }

      const data = await resp.json();
      this._setStatus('Processing...');
      this._setProgress(20);

      // Emit synthetic progress so the UI can transition to processing view
      if (this._onProgress) {
        this._onProgress({ step: 'upload', progress: 0, message: 'Starting pipeline...' });
      }

      // Listen for SSE progress
      this._listenForProgress(data.id);
    } catch (err) {
      this._setStatus(`Error: ${err.message}`);
      if (this._onError) this._onError(err);
    }
  }

  _listenForProgress(jobId) {
    const evtSource = new EventSource(`/api/process/${jobId}`);
    let finished = false;

    evtSource.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data);
      const pct = data.progress || 0;
      this._setProgress(20 + pct * 0.8);
      this._setStatus(data.message || 'Processing...');
      if (this._onProgress) this._onProgress(data);
    });

    evtSource.addEventListener('complete', (e) => {
      finished = true;
      const data = JSON.parse(e.data);
      this._setProgress(100);
      this._setStatus('Ready!');
      evtSource.close();
      if (this._onComplete) this._onComplete(data);
    });

    // Server-sent named "error" event (pipeline failure with message)
    evtSource.addEventListener('error', (e) => {
      // If this is a MessageEvent (has .data), it's a server-sent error
      if (e instanceof MessageEvent && e.data) {
        finished = true;
        evtSource.close();
        const data = JSON.parse(e.data);
        const msg = data.error || 'Processing failed';
        this._setStatus(`Error: ${msg}`);
        if (this._onError) this._onError(new Error(msg));
      }
    });

    // Native EventSource connection error (only matters if we haven't finished)
    evtSource.onerror = () => {
      if (!finished) {
        evtSource.close();
        this._setStatus('Processing failed');
        if (this._onError) this._onError(new Error('SSE connection lost'));
      }
    };
  }

  _setStatus(msg) {
    if (this.statusEl) this.statusEl.textContent = msg;
  }

  _setProgress(pct) {
    if (this.progressBar) {
      this.progressBar.style.width = Math.min(100, pct) + '%';
    }
  }
}

window.UploadHandler = UploadHandler;
