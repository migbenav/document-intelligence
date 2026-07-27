import { apiFetch, API_BASE_URL } from '@/api/client';
import type { AnalysisType, AnalysisRecord, AnalysisStatusSummary } from '@/types/analysis';

/**
 * Typed error for on-demand analysis API failures.
 * The `code` field maps to backend error codes:
 * - "document_not_found" (404)
 * - "document_not_ready" (409)
 * - "analysis_failed" (502)
 */
export class AnalysisApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = 'AnalysisApiError';
  }
}

/**
 * Map HTTP error responses to typed AnalysisApiError instances.
 */
async function handleErrorResponse(response: Response): Promise<never> {
  const body = await response.json().catch(() => ({}));
  const message = body.message || body.error || `Request failed with status ${response.status}`;

  switch (response.status) {
    case 404:
      throw new AnalysisApiError('document_not_found', message);
    case 409:
      throw new AnalysisApiError('document_not_ready', message);
    case 502:
      throw new AnalysisApiError('analysis_failed', message);
    default:
      throw new AnalysisApiError('unknown_error', message);
  }
}

/**
 * Trigger an on-demand analysis for a document.
 * The request includes user preference headers (language, model, auto-fallback)
 * automatically via `apiFetch`.
 *
 * The endpoint waits synchronously for the LLM response (5-15s typically).
 * If a completed, non-outdated result already exists, it is returned immediately.
 */
export async function triggerAnalysis(
  documentId: string,
  type: AnalysisType,
): Promise<AnalysisRecord> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/analyses/${type}`;

  const response = await apiFetch(url, { method: 'POST' });

  if (!response.ok) {
    await handleErrorResponse(response);
  }

  return (await response.json()) as AnalysisRecord;
}

/**
 * Get the status summary for all analysis types on a document.
 * Returns one entry per analysis type with its current status and last update time.
 */
export async function getAnalysisStatuses(
  documentId: string,
): Promise<AnalysisStatusSummary> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/analyses`;

  const response = await apiFetch(url);

  if (!response.ok) {
    await handleErrorResponse(response);
  }

  return (await response.json()) as AnalysisStatusSummary;
}

/**
 * Get the stored result for a specific analysis type on a document.
 * Returns the full AnalysisRecord if completed/outdated, or a record with
 * status "not_started" and null result if never executed.
 */
export async function getAnalysisResult(
  documentId: string,
  type: AnalysisType,
): Promise<AnalysisRecord> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/analyses/${type}`;

  const response = await apiFetch(url);

  if (!response.ok) {
    await handleErrorResponse(response);
  }

  return (await response.json()) as AnalysisRecord;
}
