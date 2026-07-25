export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const UPLOAD_TIMEOUT_MS = 30_000;
export const POLL_INTERVAL_MS = 2_000;
export const MAX_POLL_FAILURES = 3;

/** Threshold in ms after which onSlowConnection is called */
export const SLOW_CONNECTION_THRESHOLD_MS = 3_000;
