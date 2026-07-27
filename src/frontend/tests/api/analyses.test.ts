import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AnalysisApiError, triggerAnalysis } from '@/api/analyses';

// Mock the client module
vi.mock('@/api/client', () => ({
  API_BASE_URL: 'http://localhost:8000',
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/api/client';

const mockApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AnalysisApiError', () => {
  it('stores errorCode and modelId from options', () => {
    const err = new AnalysisApiError('quota_exhausted', 'Quota hit', {
      errorCode: 'quota_exhausted',
      modelId: 'gemini/gemini-2.5-flash',
    });

    expect(err.code).toBe('quota_exhausted');
    expect(err.errorCode).toBe('quota_exhausted');
    expect(err.modelId).toBe('gemini/gemini-2.5-flash');
    expect(err.message).toBe('Quota hit');
    expect(err.name).toBe('AnalysisApiError');
  });

  it('defaults errorCode from code when no options provided', () => {
    const err = new AnalysisApiError('analysis_failed', 'Something broke');

    expect(err.errorCode).toBe('analysis_failed');
    expect(err.modelId).toBeUndefined();
  });

  it('is an instance of Error', () => {
    const err = new AnalysisApiError('unknown_error', 'test');
    expect(err).toBeInstanceOf(Error);
  });
});

describe('handleErrorResponse (via triggerAnalysis)', () => {
  function mockResponse(status: number, body: Record<string, unknown>): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  it('handles 429 quota error with model_id', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(429, {
        error_code: 'quota_exhausted',
        model_id: 'gemini/gemini-2.5-flash',
        message: 'Rate limit exceeded for gemini-2.5-flash',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('quota_exhausted');
    expect(apiErr.modelId).toBe('gemini/gemini-2.5-flash');
    expect(apiErr.message).toBe('Rate limit exceeded for gemini-2.5-flash');
  });

  it('handles 504 timeout error', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(504, {
        error_code: 'timeout',
        message: 'Analysis timed out',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('timeout');
    expect(apiErr.modelId).toBeUndefined();
    expect(apiErr.message).toBe('Analysis timed out');
  });

  it('handles 401 auth error', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(401, {
        error_code: 'auth_error',
        message: 'Invalid API key for the selected model',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('auth_error');
    expect(apiErr.message).toBe('Invalid API key for the selected model');
  });

  it('handles 502 generic analysis failure', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(502, {
        error_code: 'analysis_failed',
        message: 'LLM returned invalid response',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('analysis_failed');
  });

  it('handles 404 document not found', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(404, {
        error_code: 'document_not_found',
        message: 'Document not found',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('document_not_found');
  });

  it('handles 409 document not ready', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(409, {
        error_code: 'document_not_ready',
        message: 'IR not yet available',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('document_not_ready');
  });

  it('falls back to status-based code when body has no error_code', async () => {
    mockApiFetch.mockResolvedValue(
      mockResponse(429, {
        message: 'Too many requests',
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('quota_exhausted');
    expect(apiErr.message).toBe('Too many requests');
  });

  it('handles non-JSON error response gracefully', async () => {
    mockApiFetch.mockResolvedValue(
      new Response('Internal Server Error', {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }),
    );

    const err = await triggerAnalysis('doc-1', 'build_index').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AnalysisApiError);
    const apiErr = err as AnalysisApiError;
    expect(apiErr.errorCode).toBe('unknown_error');
    expect(apiErr.message).toBe('Request failed with status 500');
  });
});
