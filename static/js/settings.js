/**
 * SettingsController — Manages theme, colors, font size, and preferences.
 *
 * All changes instantly update CSS custom properties on the player container.
 * Settings persist to localStorage.
 */

const THEME_PRESETS = {
  dark: {
    label: 'Dark',
    bg: '#1a1a2e',
    highlight: '#FFD700',
    spoken: '#BBBBBB',
    upcoming: '#555555',
  },
  light: {
    label: 'Light',
    bg: '#FFFFFF',
    highlight: '#2563EB',
    spoken: '#333333',
    upcoming: '#AAAAAA',
  },
  sepia: {
    label: 'Sepia',
    bg: '#F4ECD8',
    highlight: '#8B4513',
    spoken: '#5C4033',
    upcoming: '#B8A88A',
  },
  neon: {
    label: 'Neon',
    bg: '#0a0a0a',
    highlight: '#00FF88',
    spoken: '#FF00FF',
    upcoming: '#333333',
  },
};

const STORAGE_KEY = 'bookKaraokeSettings';

const DEFAULT_SETTINGS = {
  theme: 'dark',
  bgColor: '#1a1a2e',
  highlightColor: '#FFD700',
  spokenColor: '#BBBBBB',
  upcomingColor: '#555555',
  fontSize: 48,
  wordsPerChunk: 20,
  voice: 'andrew',
};

class SettingsController {
  constructor() {
    this.settings = { ...DEFAULT_SETTINGS };
    this._listeners = [];
    this._load();
  }

  /**
   * Bind UI elements to settings controls.
   */
  bindUI() {
    // Theme preset buttons
    document.querySelectorAll('[data-theme]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.applyTheme(btn.dataset.theme);
      });
    });

    // Color pickers
    this._bindInput('setting-bg', 'bgColor');
    this._bindInput('setting-highlight', 'highlightColor');
    this._bindInput('setting-spoken', 'spokenColor');
    this._bindInput('setting-upcoming', 'upcomingColor');

    // Font size slider
    const fontSlider = document.getElementById('setting-font-size');
    const fontValue = document.getElementById('font-size-value');
    if (fontSlider) {
      fontSlider.value = this.settings.fontSize;
      if (fontValue) fontValue.textContent = this.settings.fontSize + 'px';
      fontSlider.addEventListener('input', () => {
        this.settings.fontSize = parseInt(fontSlider.value);
        if (fontValue) fontValue.textContent = this.settings.fontSize + 'px';
        this._apply();
      });
    }

    // Words per chunk slider
    const chunkSlider = document.getElementById('setting-words-per-chunk');
    const chunkValue = document.getElementById('words-per-chunk-value');
    if (chunkSlider) {
      chunkSlider.value = this.settings.wordsPerChunk;
      if (chunkValue) chunkValue.textContent = this.settings.wordsPerChunk;
      chunkSlider.addEventListener('input', () => {
        this.settings.wordsPerChunk = parseInt(chunkSlider.value);
        if (chunkValue) chunkValue.textContent = this.settings.wordsPerChunk;
        this._syncPregenControl('wordsPerChunk', this.settings.wordsPerChunk);
        this._apply();
      });
    }

    // Voice dropdown
    const voiceSelect = document.getElementById('setting-voice');
    if (voiceSelect) {
      voiceSelect.value = this.settings.voice;
      voiceSelect.addEventListener('change', () => {
        this.settings.voice = voiceSelect.value;
        this._syncPregenControl('voice', voiceSelect.value);
        this._apply();
      });
    }

    // Bind pre-generation controls (upload section)
    this._bindPregenControls();

    // Apply theme on init
    this._applyCSS();
    this._highlightActiveTheme();
  }

  /**
   * Register a callback for settings changes.
   */
  onChange(fn) {
    this._listeners.push(fn);
  }

  /**
   * Apply a theme preset.
   */
  applyTheme(themeName) {
    const preset = THEME_PRESETS[themeName];
    if (!preset) return;

    this.settings.theme = themeName;
    this.settings.bgColor = preset.bg;
    this.settings.highlightColor = preset.highlight;
    this.settings.spokenColor = preset.spoken;
    this.settings.upcomingColor = preset.upcoming;

    // Update color picker UI
    this._setInputValue('setting-bg', preset.bg);
    this._setInputValue('setting-highlight', preset.highlight);
    this._setInputValue('setting-spoken', preset.spoken);
    this._setInputValue('setting-upcoming', preset.upcoming);

    this._highlightActiveTheme();
    this._apply();
  }

  getSettings() {
    return { ...this.settings };
  }

  // --- Private ---

  _bindPregenControls() {
    // Pre-gen voice dropdown
    const pregenVoice = document.getElementById('pregen-voice');
    if (pregenVoice) {
      pregenVoice.value = this.settings.voice;
      pregenVoice.addEventListener('change', () => {
        this.settings.voice = pregenVoice.value;
        this._syncSettingControl('voice', pregenVoice.value);
        this._apply();
      });
    }

    // Pre-gen words-per-chunk slider
    const pregenWpc = document.getElementById('pregen-words-per-chunk');
    const pregenWpcValue = document.getElementById('pregen-wpc-value');
    if (pregenWpc) {
      pregenWpc.value = this.settings.wordsPerChunk;
      if (pregenWpcValue) pregenWpcValue.textContent = this.settings.wordsPerChunk;
      pregenWpc.addEventListener('input', () => {
        this.settings.wordsPerChunk = parseInt(pregenWpc.value);
        if (pregenWpcValue) pregenWpcValue.textContent = this.settings.wordsPerChunk;
        this._syncSettingControl('wordsPerChunk', this.settings.wordsPerChunk);
        this._apply();
      });
    }
  }

  /** Sync a value from the settings panel to the pre-gen control. */
  _syncPregenControl(key, value) {
    if (key === 'voice') {
      const el = document.getElementById('pregen-voice');
      if (el) el.value = value;
    } else if (key === 'wordsPerChunk') {
      const el = document.getElementById('pregen-words-per-chunk');
      const valEl = document.getElementById('pregen-wpc-value');
      if (el) el.value = value;
      if (valEl) valEl.textContent = value;
    }
  }

  /** Sync a value from the pre-gen control to the settings panel. */
  _syncSettingControl(key, value) {
    if (key === 'voice') {
      const el = document.getElementById('setting-voice');
      if (el) el.value = value;
    } else if (key === 'wordsPerChunk') {
      const el = document.getElementById('setting-words-per-chunk');
      const valEl = document.getElementById('words-per-chunk-value');
      if (el) el.value = value;
      if (valEl) valEl.textContent = value;
    }
  }

  _bindInput(id, key) {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = this.settings[key];
    el.addEventListener('input', () => {
      this.settings[key] = el.value;
      this.settings.theme = 'custom';
      this._highlightActiveTheme();
      this._apply();
    });
  }

  _setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
  }

  _apply() {
    this._applyCSS();
    this._save();
    this._listeners.forEach(fn => fn(this.settings));
  }

  _applyCSS() {
    const root = document.documentElement;
    root.style.setProperty('--karaoke-bg', this.settings.bgColor);
    root.style.setProperty('--karaoke-highlight', this.settings.highlightColor);
    root.style.setProperty('--karaoke-spoken', this.settings.spokenColor);
    root.style.setProperty('--karaoke-upcoming', this.settings.upcomingColor);
    root.style.setProperty('--karaoke-font-size', this.settings.fontSize + 'px');
  }

  _highlightActiveTheme() {
    document.querySelectorAll('[data-theme]').forEach(btn => {
      btn.classList.toggle('theme-active', btn.dataset.theme === this.settings.theme);
    });
  }

  _save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings));
    } catch (e) {
      // localStorage might be unavailable
    }
  }

  _load() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        Object.assign(this.settings, parsed);
      }
    } catch (e) {
      // ignore
    }
  }
}

window.SettingsController = SettingsController;
window.THEME_PRESETS = THEME_PRESETS;
