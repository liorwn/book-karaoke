/**
 * KaraokePlayer — Core audio engine with timestamp synchronization.
 *
 * Uses HTML5 Audio element for playback and requestAnimationFrame
 * for high-frequency time updates that drive word highlighting.
 */

class KaraokePlayer extends EventTarget {
  constructor() {
    super();
    this.audio = null;
    this.chunks = [];       // array of arrays of { word, start, end }
    this.chunkRanges = [];  // [{ start, end }] per chunk
    this.duration = 0;
    this.activeChunkIndex = -1;
    this.activeWordIndex = -1;
    this._rafId = null;
    this._playing = false;

    // Transition settings (seconds)
    this.preRoll = 0.3;
    this.postRoll = 0.3;
  }

  /**
   * Load audio from a URL or Blob.
   */
  async loadAudio(src) {
    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute('src');
    }
    this.audio = new Audio();
    this.audio.crossOrigin = 'anonymous';
    this.audio.preload = 'auto';

    return new Promise((resolve, reject) => {
      this.audio.addEventListener('loadedmetadata', () => {
        this.duration = this.audio.duration;
        this._emit('loaded', { duration: this.duration });
        resolve();
      }, { once: true });

      this.audio.addEventListener('error', (e) => {
        reject(new Error('Failed to load audio: ' + (e.message || 'unknown error')));
      }, { once: true });

      this.audio.addEventListener('ended', () => {
        this._playing = false;
        this._stopLoop();
        this._emit('ended');
      });

      if (src instanceof Blob) {
        this.audio.src = URL.createObjectURL(src);
      } else {
        this.audio.src = src;
      }
    });
  }

  /**
   * Set timestamp data: array of chunks, each chunk is array of { word, start, end }.
   */
  setTimestamps(chunks) {
    this.chunks = chunks;
    this.chunkRanges = chunks.map(chunk => {
      if (!chunk.length) return { start: 0, end: 0 };
      return {
        start: chunk[0].start,
        end: chunk[chunk.length - 1].end,
      };
    });
    this._emit('timestampsloaded', { chunks: this.chunks, chunkRanges: this.chunkRanges });
  }

  play() {
    if (!this.audio) return;
    this.audio.play();
    this._playing = true;
    this._startLoop();
    this._emit('play');
  }

  pause() {
    if (!this.audio) return;
    this.audio.pause();
    this._playing = false;
    this._stopLoop();
    this._emit('pause');
  }

  toggle() {
    if (this._playing) {
      this.pause();
    } else {
      this.play();
    }
  }

  seek(time) {
    if (!this.audio) return;
    this.audio.currentTime = Math.max(0, Math.min(time, this.duration));
    this._updateTime();
    this._emit('seek', { time: this.audio.currentTime });
  }

  seekToChunk(index) {
    if (index >= 0 && index < this.chunkRanges.length) {
      this.seek(this.chunkRanges[index].start);
    }
  }

  get currentTime() {
    return this.audio ? this.audio.currentTime : 0;
  }

  get isPlaying() {
    return this._playing;
  }

  get progress() {
    if (!this.audio || !this.duration) return 0;
    return this.audio.currentTime / this.duration;
  }

  setVolume(vol) {
    if (this.audio) this.audio.volume = Math.max(0, Math.min(1, vol));
  }

  setPlaybackRate(rate) {
    if (this.audio) this.audio.playbackRate = rate;
  }

  destroy() {
    this._stopLoop();
    if (this.audio) {
      this.audio.pause();
      if (this.audio.src.startsWith('blob:')) {
        URL.revokeObjectURL(this.audio.src);
      }
      this.audio = null;
    }
  }

  // --- Private ---

  _startLoop() {
    this._stopLoop();
    const tick = () => {
      this._updateTime();
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  _stopLoop() {
    if (this._rafId) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
  }

  _updateTime() {
    if (!this.audio) return;
    const t = this.audio.currentTime;
    const progress = this.duration > 0 ? t / this.duration : 0;

    // Find active chunk
    let newChunkIdx = -1;
    let fadeAlpha = 1.0;

    for (let i = 0; i < this.chunkRanges.length; i++) {
      const cr = this.chunkRanges[i];
      const preStart = cr.start - this.preRoll;
      const postEnd = cr.end + (i < this.chunkRanges.length - 1 ? this.postRoll : 1.0);

      if (t >= preStart && t <= postEnd) {
        newChunkIdx = i;
        if (t < cr.start) {
          fadeAlpha = Math.max(0, 1.0 - (cr.start - t) / this.preRoll);
        } else if (t > cr.end) {
          const post = i < this.chunkRanges.length - 1 ? this.postRoll : 1.0;
          fadeAlpha = Math.max(0, 1.0 - (t - cr.end) / post);
        }
        break;
      }
    }

    // Find active word within chunk
    let newWordIdx = -1;
    if (newChunkIdx >= 0) {
      const chunk = this.chunks[newChunkIdx];
      for (let w = 0; w < chunk.length; w++) {
        if (t >= chunk[w].start && t < chunk[w].end) {
          newWordIdx = w;
          break;
        }
      }
      // If past all words, set to last word
      if (newWordIdx === -1 && chunk.length > 0 && t >= chunk[chunk.length - 1].end) {
        newWordIdx = chunk.length - 1;
      }
    }

    // Chunk change event
    if (newChunkIdx !== this.activeChunkIndex) {
      const prevChunk = this.activeChunkIndex;
      this.activeChunkIndex = newChunkIdx;
      this._emit('chunkchange', {
        chunkIndex: newChunkIdx,
        previousChunkIndex: prevChunk,
        fadeAlpha,
      });
    }

    // Word change
    if (newWordIdx !== this.activeWordIndex) {
      this.activeWordIndex = newWordIdx;
      this._emit('wordchange', { wordIndex: newWordIdx, chunkIndex: newChunkIdx });
    }

    this._emit('timeupdate', {
      time: t,
      progress,
      chunkIndex: newChunkIdx,
      wordIndex: newWordIdx,
      fadeAlpha,
    });
  }

  _emit(name, detail = {}) {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }
}

window.KaraokePlayer = KaraokePlayer;
