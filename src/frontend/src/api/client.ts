import { usePreferencesStore } from '@/store/preferencesStore';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const UPLOAD_TIMEOUT_MS = 30_000;
export const POLL_INTERVAL_MS = 2_000;
export const MAX_POLL_FAILURES = 3;

/** Threshold in ms after which onSlowConnection is called */
export const SLOW_CONNECTION_THRESHOLD_MS = 3_000;

/**
 * Build preference headers from the current store state.
 * Uses getState() so it works outside React components.
 */
export function getPreferenceHeaders(): Record<string, string> {
  const { language, model, autoFallback } = usePreferencesStore.getState();
  return {
    'Accept-Language': language,
    'X-Model-Preference': model,
    'X-Auto-Fallback': String(autoFallback),
  };
}

/**
 * Wrapper around the global fetch that automatically injects user preference headers.
 * All API calls that may trigger LLM work should use this instead of raw fetch.
 */
export function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const preferenceHeaders = getPreferenceHeaders();
  const mergedHeaders: Record<string, string> = {
    ...preferenceHeaders,
    ...(init?.headers as Record<string, string> | undefined),
  };

  return fetch(input, {
    ...init,
    headers: mergedHeaders,
  });
}
