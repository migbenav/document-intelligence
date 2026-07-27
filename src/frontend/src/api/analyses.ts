import { apiFetch, API_BASE_URL } from '@/api/client';
import type { AnalysisType, AnalysisRecord, AnalysisStatusSummary } from '@/types/analysis';

/** Error codes returned by the analysis API. */
export type AnalysisErrorCode =
  | 'document_not_found'
  | 'document_not_ready'
  | 'quota_exhausted'
  | 'timeout'
  | 'auth_error'
  | 'analysis_failed'
  | 'unknown_error';

/**
 * Typed error for on-demand analysis API failures.
 * The `code` field maps to backend error codes:
 * - "document_not_found" (404)
 * - "document_not_ready" (409)
 * - "quota_exhausted" (429) — LLM quota/rate limit hit
 * - "timeout" (504) — LLM response timed out
 * - "auth_error" (401) — LLM authentication failure
 * - "analysis_failed" (502) — generic LLM/analysis failure
 */
export class AnalysisApiError extends Error {
  /** Classified error code from the backend response. */
  public readonly errorCode: AnalysisErrorCode;
  /** The model that caused the error (present for quota errors). */
  public readonly modelId: string | undefined;

  constructor(
    public code: string,
    message: string,
    options?: { errorCode?: AnalysisErrorCode; modelId?: string },
  ) {
    super(message);
    this.name = 'AnalysisApiError';
    this.errorCode = options?.errorCode ?? (code as AnalysisErrorCode);
    this.modelId = options?.modelId;
  }
}

/**
 * Map HTTP error responses to typed AnalysisApiError instances.
 * Parses `error_code` and `model_id` from the JSON response body when available.
 */
async function handleErrorResponse(response: Response): Promise<never> {
  const body = await response.json().catch(() => ({}));
  const message = body.message || body.error || `Request failed with status ${response.status}`;
  const errorCode: AnalysisErrorCode | undefined = body.error_code;
  const modelId: string | undefined = body.model_id;

  switch (response.status) {
    case 401:
      throw new AnalysisApiError(
        errorCode ?? 'auth_error',
        message,
        { errorCode: errorCode ?? 'auth_error', modelId },
      );
    case 404:
      throw new AnalysisApiError(
        errorCode ?? 'document_not_found',
        message,
        { errorCode: errorCode ?? 'document_not_found', modelId },
      );
    case 409:
      throw new AnalysisApiError(
        errorCode ?? 'document_not_ready',
        message,
        { errorCode: errorCode ?? 'document_not_ready', modelId },
      );
    case 429:
      throw new AnalysisApiError(
        errorCode ?? 'quota_exhausted',
        message,
        { errorCode: errorCode ?? 'quota_exhausted', modelId },
      );
    case 502:
      throw new AnalysisApiError(
        errorCode ?? 'analysis_failed',
        message,
        { errorCode: errorCode ?? 'analysis_failed', modelId },
      );
    case 504:
      throw new AnalysisApiError(
        errorCode ?? 'timeout',
        message,
        { errorCode: errorCode ?? 'timeout', modelId },
      );
    default:
      throw new AnalysisApiError(
        errorCode ?? 'unknown_error',
        message,
        { errorCode: errorCode ?? 'unknown_error', modelId },
      );
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
