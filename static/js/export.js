/**
 * ExportController — Handles MP4/SRT/VTT export with progress.
 */

class ExportController {
  constructor(containerEl) {
    this.container = containerEl;
    this.projectId = null;
    this._bindEvents();
  }

  setProjectId(id) {
    this.projectId = id;
    // Enable export buttons
    if (this.container) {
      this.container.querySelectorAll('button').forEach(btn => {
        btn.disabled = !id;
      });
    }
  }

  _bindEvents() {
    if (!this.container) return;

    const mp4Btn = this.container.querySelector('[data-export="mp4"]');
    const srtBtn = this.container.querySelector('[data-export="srt"]');
    const vttBtn = this.container.querySelector('[data-export="vtt"]');
    const htmlBtn = this.container.querySelector('[data-export="html"]');

    if (mp4Btn) mp4Btn.addEventListener('click', () => this._exportMP4());
    if (srtBtn) srtBtn.addEventListener('click', () => this._exportSRT());
    if (vttBtn) vttBtn.addEventListener('click', () => this._exportVTT());
    if (htmlBtn) htmlBtn.addEventListener('click', () => this._exportHTML());
  }

  async _exportMP4() {
    if (!this.projectId) return;

    const statusEl = this.container.querySelector('.export-status');
    const progressEl = this.container.querySelector('.export-progress-bar');

    if (statusEl) statusEl.textContent = 'Starting MP4 export...';
    if (progressEl) progressEl.style.width = '0%';

    try {
      const resp = await fetch(`/api/export/mp4/${this.projectId}`, { method: 'POST' });
      if (!resp.ok) throw new Error('Export failed');

      const data = await resp.json();

      // Listen for progress via SSE
      const evtSource = new EventSource(`/api/export/progress/${data.job_id}`);

      evtSource.addEventListener('progress', (e) => {
        const d = JSON.parse(e.data);
        if (progressEl) progressEl.style.width = (d.progress * 100) + '%';
        if (statusEl) statusEl.textContent = d.message || 'Rendering...';
      });

      evtSource.addEventListener('complete', (e) => {
        const d = JSON.parse(e.data);
        evtSource.close();
        if (progressEl) progressEl.style.width = '100%';
        if (statusEl) statusEl.textContent = 'Export complete!';

        // Create download link
        if (d.download_url) {
          const link = document.createElement('a');
          link.href = d.download_url;
          link.download = 'karaoke.mp4';
          link.className = 'download-link';
          link.textContent = 'Download MP4';
          this.container.appendChild(link);
        }
      });

      evtSource.onerror = () => {
        evtSource.close();
        if (statusEl) statusEl.textContent = 'Export failed';
      };
    } catch (err) {
      if (statusEl) statusEl.textContent = `Error: ${err.message}`;
    }
  }

  async _exportHTML() {
    if (!this.projectId) return;
    this._downloadFile(`/api/export/html/${this.projectId}`, 'karaoke.html');
  }

  async _exportSRT() {
    if (!this.projectId) return;
    this._downloadFile(`/api/export/srt/${this.projectId}`, 'karaoke.srt');
  }

  async _exportVTT() {
    if (!this.projectId) return;
    this._downloadFile(`/api/export/vtt/${this.projectId}`, 'karaoke.vtt');
  }

  async _downloadFile(url, filename) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('Download failed');
      const blob = await resp.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      const statusEl = this.container.querySelector('.export-status');
      if (statusEl) statusEl.textContent = `Error: ${err.message}`;
    }
  }
}

window.ExportController = ExportController;
