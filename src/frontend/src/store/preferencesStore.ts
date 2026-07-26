import { create } from 'zustand';

// --- Types ---

export interface PreferencesState {
  language: 'es' | 'en';
  model: string;
  autoFallback: boolean;
}

export interface PreferencesActions {
  setLanguage: (lang: 'es' | 'en') => void;
  setModel: (model: string) => void;
  setAutoFallback: (enabled: boolean) => void;
}

export type PreferencesStore = PreferencesState & PreferencesActions;

// --- Constants ---

const STORAGE_KEY = 'user_preferences';

const DEFAULTS: PreferencesState = {
  language: 'es',
  model: 'default',
  autoFallback: true,
};

// --- Helpers ---

function loadFromStorage(): PreferencesState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };

    const parsed = JSON.parse(raw);

    // Validate and merge with defaults
    return {
      language: parsed.language === 'en' || parsed.language === 'es' ? parsed.language : DEFAULTS.language,
      model: typeof parsed.model === 'string' ? parsed.model : DEFAULTS.model,
      autoFallback: typeof parsed.autoFallback === 'boolean' ? parsed.autoFallback : DEFAULTS.autoFallback,
    };
  } catch {
    // Invalid JSON, localStorage unavailable, or any other error
    return { ...DEFAULTS };
  }
}

function persistToStorage(state: PreferencesState): void {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        language: state.language,
        model: state.model,
        autoFallback: state.autoFallback,
      })
    );
  } catch {
    // localStorage unavailable (e.g. private browsing quota exceeded) — silently ignore
  }
}

// --- Store ---

export const usePreferencesStore = create<PreferencesStore>((set, get) => ({
  ...loadFromStorage(),

  setLanguage: (lang) => {
    set({ language: lang });
    persistToStorage(get());
  },

  setModel: (model) => {
    set({ model });
    persistToStorage(get());
  },

  setAutoFallback: (enabled) => {
    set({ autoFallback: enabled });
    persistToStorage(get());
  },
}));
