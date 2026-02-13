/**
 * TeleprompterRenderer — Scrolling full-text view with auto-scroll tracking.
 *
 * Same interface as KaraokeRenderer so app.js can delegate to either.
 * Renders ALL chunks into a scrollable wrapper, highlights the active word,
 * and auto-scrolls to keep it centered.
 */

class TeleprompterRenderer {
  constructor(containerEl, progressBarEl) {
    this.container = containerEl;
    this.progressBar = progressBarEl;
    this.chunks = [];
    this.formatting = {};
    this._allSpans = [];           // flat array of all word spans
    this._chunkWordOffsets = [];    // starting flat index for each chunk
    this._prevFlatIndex = -1;
    this._scrollEl = null;
    this._autoScrollEnabled = true;
    this._scrollThrottleTimer = null;
    this._userScrollTimer = null;
    this._built = false;
  }

  setChunks(chunks) {
    this.chunks = chunks;
  }

  setFormatting(formatting) {
    this.formatting = formatting || {};
  }

  /**
   * Render ALL chunks into a scrollable wrapper inside the container.
   */
  build(chapters) {
    this.container.innerHTML = '';
    this._allSpans = [];
    this._chunkWordOffsets = [];
    this._prevFlatIndex = -1;
    this._autoScrollEnabled = true;

    const scrollWrapper = document.createElement('div');
    scrollWrapper.className = 'teleprompter-scroll';
    this._scrollEl = scrollWrapper;

    // Build a chapter lookup: chunkIndex -> chapter
    const chapterMap = {};
    if (chapters && chapters.length > 0) {
      for (const ch of chapters) {
        if (ch.start_chunk != null) {
          chapterMap[ch.start_chunk] = ch.title;
        }
      }
    }

    let flatIdx = 0;
    for (let ci = 0; ci < this.chunks.length; ci++) {
      // Insert chapter title if this chunk starts a chapter
      if (chapterMap[ci]) {
        const titleEl = document.createElement('div');
        titleEl.className = 'teleprompter-chapter-title';
        titleEl.textContent = chapterMap[ci];
        scrollWrapper.appendChild(titleEl);
      }

      this._chunkWordOffsets.push(flatIdx);

      const chunkEl = document.createElement('div');
      chunkEl.className = 'teleprompter-chunk';

      const chunk = this.chunks[ci];
      for (let wi = 0; wi < chunk.length; wi++) {
        const wordData = chunk[wi];
        const span = document.createElement('span');
        span.className = 'karaoke-word word-upcoming';

        // Apply formatting
        const normWord = wordData.word.replace(/[^a-zA-Z0-9']/g, '').toLowerCase();
        if (normWord && this.formatting[normWord]) {
          span.classList.add('word-' + this.formatting[normWord]);
        }

        span.textContent = wordData.word;
        span.dataset.flat = flatIdx;
        chunkEl.appendChild(span);

        if (wi < chunk.length - 1) {
          chunkEl.appendChild(document.createTextNode(' '));
        }

        this._allSpans.push(span);
        flatIdx++;
      }

      scrollWrapper.appendChild(chunkEl);
    }

    this.container.appendChild(scrollWrapper);

    // User scroll override: suppress auto-scroll for 3 seconds
    const suppressAutoScroll = () => {
      this._autoScrollEnabled = false;
      clearTimeout(this._userScrollTimer);
      this._userScrollTimer = setTimeout(() => {
        this._autoScrollEnabled = true;
      }, 3000);
    };

    scrollWrapper.addEventListener('wheel', suppressAutoScroll, { passive: true });
    scrollWrapper.addEventListener('touchmove', suppressAutoScroll, { passive: true });

    this._built = true;
  }

  /**
   * Update word highlighting based on current time.
   * Only toggles classes between previous and new flat index (no full scan).
   */
  updateTime(time, chunkIndex, wordIndex, fadeAlpha) {
    if (!this._built || chunkIndex < 0 || wordIndex < 0) return;
    if (chunkIndex >= this._chunkWordOffsets.length) return;

    const flatIndex = this._chunkWordOffsets[chunkIndex] + wordIndex;
    if (flatIndex === this._prevFlatIndex) return;

    const prevFlat = this._prevFlatIndex;
    this._prevFlatIndex = flatIndex;

    // Determine range to update
    const lo = Math.min(prevFlat < 0 ? 0 : prevFlat, flatIndex);
    const hi = Math.max(prevFlat < 0 ? 0 : prevFlat, flatIndex);

    for (let i = lo; i <= hi; i++) {
      if (i >= this._allSpans.length) break;
      const span = this._allSpans[i];
      span.classList.remove('word-active', 'word-spoken', 'word-upcoming');
      if (i < flatIndex) {
        span.classList.add('word-spoken');
      } else if (i === flatIndex) {
        span.classList.add('word-active');
      } else {
        span.classList.add('word-upcoming');
      }
    }

    // Also mark everything before lo as spoken (on first update or big seek)
    if (prevFlat < 0) {
      for (let i = 0; i < flatIndex; i++) {
        const span = this._allSpans[i];
        span.classList.remove('word-active', 'word-upcoming');
        span.classList.add('word-spoken');
      }
    }

    // Auto-scroll: throttle to max once per 300ms
    if (this._autoScrollEnabled && !this._scrollThrottleTimer) {
      const activeSpan = this._allSpans[flatIndex];
      if (activeSpan && this._scrollEl) {
        activeSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      this._scrollThrottleTimer = setTimeout(() => {
        this._scrollThrottleTimer = null;
      }, 300);
    }
  }

  updateProgress(progress) {
    if (this.progressBar) {
      this.progressBar.style.setProperty('--progress', `${progress * 100}%`);
    }
  }

  applySettings(settings) {
    if (settings.fontSize) {
      this.container.style.fontSize = settings.fontSize + 'px';
    }
  }

  destroy() {
    clearTimeout(this._scrollThrottleTimer);
    clearTimeout(this._userScrollTimer);
    this._built = false;
    this._allSpans = [];
    this._chunkWordOffsets = [];
    this._prevFlatIndex = -1;
  }
}

window.TeleprompterRenderer = TeleprompterRenderer;
