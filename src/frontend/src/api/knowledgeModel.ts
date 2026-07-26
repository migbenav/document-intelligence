import { API_BASE_URL, apiFetch } from './client';
import type { KnowledgeModelResponse } from '@/types/knowledgeModel';

/** 30s timeout for cold-start tolerance */
const FETCH_TIMEOUT_MS = 30_000;

/**
 * Error thrown when the Knowledge Model API returns a non-success status.
 */
export class KnowledgeModelApiError extends Error {
  public readonly status: number;
  public readonly code: 'not_found' | 'not_ready' | 'unknown';

  constructor(status: number, message: string) {
    super(message);
    this.name = 'KnowledgeModelApiError';
    this.status = status;

    if (status === 404) {
      this.code = 'not_found';
    } else if (status === 409) {
      this.code = 'not_ready';
    } else {
      this.code = 'unknown';
    }
  }
}

/**
 * Error thrown when the request times out or a network error occurs.
 */
export class KnowledgeModelNetworkError extends Error {
  public readonly code: 'timeout' | 'network';

  constructor(code: 'timeout' | 'network', message: string) {
    super(message);
    this.name = 'KnowledgeModelNetworkError';
    this.code = code;
  }
}

/**
 * Fetch the Knowledge Model for a document.
 *
 * @param documentId - The document UUID
 * @returns The Knowledge Model response
 * @throws {KnowledgeModelApiError} on 404 (not found) or 409 (not ready)
 * @throws {KnowledgeModelNetworkError} on timeout or network failure
 */
export async function getKnowledgeModel(
  documentId: string,
): Promise<KnowledgeModelResponse> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/knowledge-model`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const response = await apiFetch(url, { signal: controller.signal });

    if (response.ok) {
      return (await response.json()) as KnowledgeModelResponse;
    }

    // Handle known error statuses
    let message: string;
    try {
      const body = await response.json();
      message = body.message || body.error || `Request failed with status ${response.status}`;
    } catch {
      message = `Request failed with status ${response.status}`;
    }

    throw new KnowledgeModelApiError(response.status, message);
  } catch (error) {
    if (error instanceof KnowledgeModelApiError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new KnowledgeModelNetworkError(
        'timeout',
        'Request timed out. The server may be starting up — please try again.',
      );
    }

    if (error instanceof TypeError) {
      // fetch throws TypeError on network failures (DNS, connection refused, etc.)
      throw new KnowledgeModelNetworkError(
        'network',
        'Unable to reach the server. Please check your connection.',
      );
    }

    // Re-throw unexpected errors
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}
