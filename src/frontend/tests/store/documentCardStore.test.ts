import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useDocumentCardStore } from '@/store/documentCardStore';
import type { DocumentCard } from '@/types/documentCard';

vi.mock('@/api/documentCard', () => ({
  fetchCard: vi.fn(),
  retryLlm: vi.fn(),
}));

import { fetchCard, retryLlm } from '@/api/documentCard';

const mockCard: DocumentCard = {
  id: 'card-001',
  document_id: 'doc-123',
  title: 'Test Document',
  summary: 'A short summary.',
  classification: 'normative',
  organization_type: 'numbered_articles',
  statistics: {
    total_chunks: 10,
    sections_detected: 3,
    hierarchy_levels: 2,
    has_existing_index: false,
  },
  file_metadata: {
    size_bytes: 50000,
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
  useDocumentCardStore.getState().reset();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('documentCardStore', () => {
  describe('initial state', () => {
    it('has null card, loading false, and null error', () => {
      const state = useDocumentCardStore.getState();
      expect(state.card).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe('fetchCard', () => {
    it('sets loading true then stores card on success', async () => {
      vi.mocked(fetchCard).mockResolvedValue(mockCard);

      const promise = useDocumentCardStore.getState().fetchCard('doc-123');

      // Loading should be true while fetching
      expect(useDocumentCardStore.getState().loading).toBe(true);

      await promise;

      const state = useDocumentCardStore.getState();
      expect(state.card).toEqual(mockCard);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('sets error on failure', async () => {
      vi.mocked(fetchCard).mockRejectedValue(new Error('Network error'));

      await useDocumentCardStore.getState().fetchCard('doc-123');

      const state = useDocumentCardStore.getState();
      expect(state.card).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Network error');
    });
  });

  describe('retryLlm', () => {
    it('sets loading true then stores updated card on success', async () => {
      vi.mocked(retryLlm).mockResolvedValue(mockCard);

      const promise = useDocumentCardStore.getState().retryLlm('doc-123');

      expect(useDocumentCardStore.getState().loading).toBe(true);

      await promise;

      const state = useDocumentCardStore.getState();
      expect(state.card).toEqual(mockCard);
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });

    it('sets error on failure', async () => {
      vi.mocked(retryLlm).mockRejectedValue(new Error('LLM unavailable'));

      await useDocumentCardStore.getState().retryLlm('doc-123');

      const state = useDocumentCardStore.getState();
      expect(state.card).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBe('LLM unavailable');
    });
  });

  describe('reset', () => {
    it('resets all state to initial values', async () => {
      // Set some state first
      vi.mocked(fetchCard).mockResolvedValue(mockCard);
      await useDocumentCardStore.getState().fetchCard('doc-123');

      expect(useDocumentCardStore.getState().card).not.toBeNull();

      // Reset
      useDocumentCardStore.getState().reset();

      const state = useDocumentCardStore.getState();
      expect(state.card).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
    });
  });
});
