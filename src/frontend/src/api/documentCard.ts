import { API_BASE_URL } from './client';
import type { DocumentCard } from '@/types/documentCard';

/**
 * Structured error from the document card API.
 */
export class CardApiError extends Error {
  public readonly status: number;
  public readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'CardApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * Fetch the document card for a given document.
 * Returns the DocumentCard on success, or throws a CardApiError on failure.
 */
export async function fetchCard(documentId: string): Promise<DocumentCard> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/card`;
  const response = await fetch(url);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const code = body?.error || 'card_not_found';
    const message =
      body?.message || `Request failed with status ${response.status}`;
    throw new CardApiError(response.status, code, message);
  }

  return (await response.json()) as DocumentCard;
}

/**
 * Retry the LLM analysis phase for a partial card.
 * Returns the updated DocumentCard on success, or throws a CardApiError on failure.
 */
export async function retryLlm(documentId: string): Promise<DocumentCard> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/card/retry-llm`;
  const response = await fetch(url, { method: 'POST' });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const code = body?.error || 'card_not_found';
    const message =
      body?.message || `Request failed with status ${response.status}`;
    throw new CardApiError(response.status, code, message);
  }

  return (await response.json()) as DocumentCard;
}
