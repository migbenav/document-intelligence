import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchCard, retryLlm, CardApiError } from '@/api/documentCard';
import type { DocumentCard } from '@/types/documentCard';

const mockCompletedCard: DocumentCard = {
  id: 'card-001',
  document_id: 'doc-123',
  title: 'Reglamento de Propiedad Horizontal',
  summary: 'Este documento establece las normas de convivencia.',
  classification: 'normative',
  organization_type: 'numbered_articles',
  statistics: {
    total_chunks: 45,
    sections_detected: 12,
    hierarchy_levels: 3,
    has_existing_index: true,
  },
  file_metadata: {
    size_bytes: 234500,
    format: 'pdf',
    language: 'es',
    last_modified: null,
  },
  status: 'completed',
  outdated: false,
  model_id: 'groq/llama-3.3-70b-versatile',
  prompt_version: 'base-analysis-v1',
  created_at: '2026-07-26T10:30:00Z',
  updated_at: '2026-07-26T10:30:04Z',
};

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('fetchCard', () => {
  it('returns DocumentCard on 200 response', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(mockCompletedCard), { status: 200 }),
    );

    const result = await fetchCard('doc-123');

    expect(result).toEqual(mockCompletedCard);
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/documents/doc-123/card',
    );
  });

  it('throws CardApiError with card_not_found on 404 when card does not exist', async () => {
    const errorBody = { error: 'card_not_found', message: 'Card is not yet available' };

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 404 }),
    );

    const error = await fetchCard('doc-123').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CardApiError);
    expect(error).toMatchObject({
      status: 404,
      code: 'card_not_found',
      message: 'Card is not yet available',
    });
  });

  it('throws CardApiError with document_not_found on 404 when document does not exist', async () => {
    const errorBody = { error: 'document_not_found', message: 'Document not found' };

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 404 }),
    );

    const error = await fetchCard('doc-999').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CardApiError);
    expect(error).toMatchObject({
      status: 404,
      code: 'document_not_found',
      message: 'Document not found',
    });
  });

  it('throws CardApiError with defaults when response body is not JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    );

    const error = await fetchCard('doc-123').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CardApiError);
    expect(error).toMatchObject({
      status: 500,
      code: 'card_not_found',
      message: 'Request failed with status 500',
    });
  });
});

describe('retryLlm', () => {
  it('returns updated DocumentCard on 200 response', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(mockCompletedCard), { status: 200 }),
    );

    const result = await retryLlm('doc-123');

    expect(result).toEqual(mockCompletedCard);
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/documents/doc-123/card/retry-llm',
      { method: 'POST' },
    );
  });

  it('throws CardApiError with card_not_found on 404', async () => {
    const errorBody = { error: 'card_not_found', message: 'No card exists for this document' };

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 404 }),
    );

    const error = await retryLlm('doc-123').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CardApiError);
    expect(error).toMatchObject({
      status: 404,
      code: 'card_not_found',
      message: 'No card exists for this document',
    });
  });

  it('throws CardApiError with card_already_complete on 409', async () => {
    const errorBody = {
      error: 'card_already_complete',
      message: 'Card does not need LLM retry',
    };

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 409 }),
    );

    const error = await retryLlm('doc-123').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CardApiError);
    expect(error).toMatchObject({
      status: 409,
      code: 'card_already_complete',
      message: 'Card does not need LLM retry',
    });
  });
});
