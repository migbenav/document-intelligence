import { describe, it, expect, beforeEach } from 'vitest';
import { getPreferenceHeaders } from '@/api/client';
import { usePreferencesStore } from '@/store/preferencesStore';

describe('getPreferenceHeaders', () => {
  beforeEach(() => {
    localStorage.clear();
    // Reset store to defaults
    usePreferencesStore.setState({
      language: 'es',
      model: 'default',
      autoFallback: true,
    });
  });

  describe('defaults when store is in initial state', () => {
    it('returns Accept-Language as "es" by default', () => {
      const headers = getPreferenceHeaders();
      expect(headers['Accept-Language']).toBe('es');
    });

    it('returns X-Model-Preference as "default" by default', () => {
      const headers = getPreferenceHeaders();
      expect(headers['X-Model-Preference']).toBe('default');
    });

    it('returns X-Auto-Fallback as "true" by default', () => {
      const headers = getPreferenceHeaders();
      expect(headers['X-Auto-Fallback']).toBe('true');
    });

    it('returns exactly three headers', () => {
      const headers = getPreferenceHeaders();
      expect(Object.keys(headers)).toHaveLength(3);
    });
  });

  describe('headers reflect current store state', () => {
    it('reflects language change to English', () => {
      usePreferencesStore.getState().setLanguage('en');

      const headers = getPreferenceHeaders();
      expect(headers['Accept-Language']).toBe('en');
    });

    it('reflects language change back to Spanish', () => {
      usePreferencesStore.getState().setLanguage('en');
      usePreferencesStore.getState().setLanguage('es');

      const headers = getPreferenceHeaders();
      expect(headers['Accept-Language']).toBe('es');
    });

    it('reflects model change to Gemini', () => {
      usePreferencesStore.getState().setModel('gemini/gemini-2.5-flash');

      const headers = getPreferenceHeaders();
      expect(headers['X-Model-Preference']).toBe('gemini/gemini-2.5-flash');
    });

    it('reflects model change to Groq', () => {
      usePreferencesStore.getState().setModel('groq/llama-3.3-70b-versatile');

      const headers = getPreferenceHeaders();
      expect(headers['X-Model-Preference']).toBe('groq/llama-3.3-70b-versatile');
    });

    it('reflects autoFallback disabled', () => {
      usePreferencesStore.getState().setAutoFallback(false);

      const headers = getPreferenceHeaders();
      expect(headers['X-Auto-Fallback']).toBe('false');
    });

    it('reflects autoFallback re-enabled', () => {
      usePreferencesStore.getState().setAutoFallback(false);
      usePreferencesStore.getState().setAutoFallback(true);

      const headers = getPreferenceHeaders();
      expect(headers['X-Auto-Fallback']).toBe('true');
    });

    it('reflects multiple preference changes simultaneously', () => {
      usePreferencesStore.getState().setLanguage('en');
      usePreferencesStore.getState().setModel('gemini/gemini-2.5-flash');
      usePreferencesStore.getState().setAutoFallback(false);

      const headers = getPreferenceHeaders();
      expect(headers['Accept-Language']).toBe('en');
      expect(headers['X-Model-Preference']).toBe('gemini/gemini-2.5-flash');
      expect(headers['X-Auto-Fallback']).toBe('false');
    });
  });
});
