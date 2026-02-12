/**
 * KaraokeRenderer — DOM-based text renderer with smooth word highlighting.
 *
 * Renders words as <span> elements. Uses CSS classes and transitions
 * for buttery smooth color changes. Handles chunk transitions with fades.
 */

class KaraokeRenderer {
  constructor(containerEl, progressBarEl) {
    this.container = containerEl;
    this.progressBar = progressBarEl;
    this.chunks = [];
    this.currentChunkIndex = -1;
    this.wordSpans = [];
    this.settings = {};
    this.formatting = {};
    this._transitioning = false;
  }

  /**
   * Set the full chunk/timing data.
   */
  setChunks(chunks) {
    this.chunks = chunks;
  }

  /**
   * Set formatting map (word -> 'bold' | 'italic' | 'bold-italic').
   */
  setFormatting(formatting) {
    this.formatting = formatting || {};
  }

  /**
   * Render a specific chunk into the container.
   * Handles fade transitions between chunks.
   */
  showChunk(chunkIndex, animate = true) {
    if (chunkIndex === this.currentChunkIndex) return;
    if (chunkIndex < 0 || chunkIndex >= this.chunks.length) {
      this._clear();
      return;
    }

    const chunk = this.chunks[chunkIndex];
    const prevIndex = this.currentChunkIndex;
    this.currentChunkIndex = chunkIndex;

    if (animate && prevIndex >= 0) {
      this._transitionChunk(chunk);
    } else {
      this._renderChunk(chunk);
    }
  }

  /**
   * Update word highlighting based on current time.
   */
  updateTime(time, chunkIndex, wordIndex, fadeAlpha) {
    if (chunkIndex !== this.currentChunkIndex) {
      this.showChunk(chunkIndex);
    }

    if (chunkIndex < 0 || !this.chunks[chunkIndex]) return;

    const chunk = this.chunks[chunkIndex];

    // Update each word span's state
    for (let i = 0; i < this.wordSpans.length; i++) {
      const span = this.wordSpans[i];
      if (i >= chunk.length) break;

      const wordTiming = chunk[i];
      span.classList.remove('word-active', 'word-spoken', 'word-upcoming');

      if (time >= wordTiming.start && time < wordTiming.end) {
        span.classList.add('word-active');
      } else if (time >= wordTiming.end) {
        span.classList.add('word-spoken');
      } else {
        span.classList.add('word-upcoming');
      }
    }

    // Apply fade alpha to container
    if (fadeAlpha !== undefined && fadeAlpha < 1) {
      this.container.style.opacity = fadeAlpha;
    } else {
      this.container.style.opacity = 1;
    }
  }

  /**
   * Update the progress bar.
   */
  updateProgress(progress) {
    if (this.progressBar) {
      this.progressBar.style.setProperty('--progress', `${progress * 100}%`);
    }
  }

  /**
   * Apply settings (font size, etc.) to the renderer.
   */
  applySettings(settings) {
    this.settings = settings;
    if (settings.fontSize) {
      this.container.style.fontSize = settings.fontSize + 'px';
    }
  }

  // --- Private ---

  _renderChunk(chunk) {
    this.container.innerHTML = '';
    this.wordSpans = [];

    if (!chunk || !chunk.length) return;

    const textBlock = document.createElement('div');
    textBlock.className = 'karaoke-text-block';

    chunk.forEach((wordData, i) => {
      const span = document.createElement('span');
      span.className = 'karaoke-word word-upcoming';

      // Apply formatting (bold/italic) from the formatting map
      const normWord = wordData.word.replace(/[^a-zA-Z0-9']/g, '').toLowerCase();
      if (normWord && this.formatting[normWord]) {
        span.classList.add('word-' + this.formatting[normWord]);
      }

      span.textContent = wordData.word;
      span.dataset.index = i;
      span.dataset.start = wordData.start;
      span.dataset.end = wordData.end;
      textBlock.appendChild(span);

      // Add space between words (except after last)
      if (i < chunk.length - 1) {
        textBlock.appendChild(document.createTextNode(' '));
      }

      this.wordSpans.push(span);
    });

    this.container.appendChild(textBlock);
    this.container.style.opacity = 1;
  }

  _transitionChunk(chunk) {
    if (this._transitioning) return;
    this._transitioning = true;

    // Fade out current
    this.container.classList.add('chunk-fade-out');

    const onFadeOut = () => {
      this.container.classList.remove('chunk-fade-out');
      this._renderChunk(chunk);

      // Fade in new
      this.container.classList.add('chunk-fade-in');

      // Wait for fade-in to complete, then clean up
      const onFadeIn = () => {
        this.container.classList.remove('chunk-fade-in');
        this._transitioning = false;
      };
      this.container.addEventListener('animationend', onFadeIn, { once: true });

      // Fallback in case animationend doesn't fire
      setTimeout(() => {
        this.container.classList.remove('chunk-fade-in');
        this._transitioning = false;
      }, 350);
    };

    this.container.addEventListener('animationend', onFadeOut, { once: true });

    // Fallback
    setTimeout(() => {
      this.container.classList.remove('chunk-fade-out');
      this._renderChunk(chunk);
      this._transitioning = false;
    }, 350);
  }

  _clear() {
    this.container.innerHTML = '';
    this.wordSpans = [];
    this.currentChunkIndex = -1;
  }
}

window.KaraokeRenderer = KaraokeRenderer;
