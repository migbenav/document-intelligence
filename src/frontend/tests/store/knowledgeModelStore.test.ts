import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { KnowledgeModelResponse } from '@/types/knowledgeModel';

// Mock the API module
vi.mock('@/api/knowledgeModel', () => ({
  getKnowledgeModel: vi.fn(),
  KnowledgeModelApiError: class KnowledgeModelApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, message: string) {
      super(message);
      this.name = 'KnowledgeModelApiError';
      this.status = status;
      if (status === 404) this.code = 'not_found';
      else if (status === 409) this.code = 'not_ready';
      else this.code = 'unknown';
    }
  },
  KnowledgeModelNetworkError: class KnowledgeModelNetworkError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.name = 'KnowledgeModelNetworkError';
      this.code = code;
    }
  },
}));

import {
  getKnowledgeModel,
  KnowledgeModelApiError,
  KnowledgeModelNetworkError,
} from '@/api/knowledgeModel';

const mockGetKnowledgeModel = vi.mocked(getKnowledgeModel);

function getState() {
  return useKnowledgeModelStore.getState();
}

function createMockKnowledgeModel(
  documentId = 'doc-123',
  elementCount = 3,
): KnowledgeModelResponse {
  const elements = Array.from({ length: elementCount }, (_, i) => ({
    id: `elem-${i}`,
    type: 'concepto' as const,
    name: `Element ${i}`,
    content: `Content for element ${i}`,
    source_ref: {
      document_id: documentId,
      chunk_id: `chunk-${i}`,
      page: i + 1,
      section: `Section ${i}`,
      evidence: `Evidence text for element ${i}`,
    },
    relations: [],
    verified: i % 2 === 0,
  }));

  return {
    document_id: documentId,
    document_type: 'legal_contract',
    elements,
    extraction_metadata: {
      prompt_version: 'v1',
      model_id: 'gpt-4',
      temperature: 0.2,
      element_count: elementCount,
      relationship_count: 0,
      verification_rate: 0.67,
      extracted_at: '2024-01-01T00:00:00Z',
    },
  };
}

describe('knowledgeModelStore', () => {
  beforeEach(() => {
    useKnowledgeModelStore.getState().reset();
    vi.clearAllMocks();
  });

  describe('Initial State', () => {
    it('starts in idle state with all fields at defaults', () => {
      const state = getState();
      expect(state.status).toBe('idle');
      expect(state.knowledgeModel).toBeNull();
      expect(state.selectedElementId).toBeNull();
      expect(state.viewMode).toBe('list');
      expect(state.navigationHistory).toEqual([]);
      expect(state.error).toBeNull();
      expect(state.documentId).toBeNull();
    });
  });

  describe('fetchKnowledgeModel', () => {
    it('transitions to loading then loaded on successful fetch with elements', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      const fetchPromise = getState().fetchKnowledgeModel('doc-123');

      // Should be loading immediately
      expect(getState().status).toBe('loading');
      expect(getState().documentId).toBe('doc-123');

      await fetchPromise;

      const state = getState();
      expect(state.status).toBe('loaded');
      expect(state.knowledgeModel).toEqual(mockResponse);
      expect(state.error).toBeNull();
    });

    it('transitions to empty when response has zero elements', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 0);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      await getState().fetchKnowledgeModel('doc-123');

      const state = getState();
      expect(state.status).toBe('empty');
      expect(state.knowledgeModel).toEqual(mockResponse);
    });

    it('skips fetch if same documentId is already loaded (cache hit)', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      // First fetch
      await getState().fetchKnowledgeModel('doc-123');
      expect(mockGetKnowledgeModel).toHaveBeenCalledTimes(1);

      // Second fetch — same document, should skip
      await getState().fetchKnowledgeModel('doc-123');
      expect(mockGetKnowledgeModel).toHaveBeenCalledTimes(1);
      expect(getState().status).toBe('loaded');
    });

    it('re-fetches when documentId changes', async () => {
      const mockResponse1 = createMockKnowledgeModel('doc-123', 3);
      const mockResponse2 = createMockKnowledgeModel('doc-456', 2);
      mockGetKnowledgeModel
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      await getState().fetchKnowledgeModel('doc-123');
      expect(getState().knowledgeModel?.document_id).toBe('doc-123');

      await getState().fetchKnowledgeModel('doc-456');
      expect(getState().knowledgeModel?.document_id).toBe('doc-456');
      expect(mockGetKnowledgeModel).toHaveBeenCalledTimes(2);
    });

    it('sets error state with message on API 404 error', async () => {
      mockGetKnowledgeModel.mockRejectedValue(
        new KnowledgeModelApiError(404, 'Not found'),
      );

      await getState().fetchKnowledgeModel('doc-missing');

      const state = getState();
      expect(state.status).toBe('error');
      expect(state.error).toBe('Document not found.');
    });

    it('sets error state with message on API 409 error', async () => {
      mockGetKnowledgeModel.mockRejectedValue(
        new KnowledgeModelApiError(409, 'Not ready'),
      );

      await getState().fetchKnowledgeModel('doc-pending');

      const state = getState();
      expect(state.status).toBe('error');
      expect(state.error).toBe(
        'Analysis is not yet completed. Please wait and try again.',
      );
    });

    it('sets error state with message on network timeout', async () => {
      mockGetKnowledgeModel.mockRejectedValue(
        new KnowledgeModelNetworkError('timeout', 'Timed out'),
      );

      await getState().fetchKnowledgeModel('doc-123');

      const state = getState();
      expect(state.status).toBe('error');
      expect(state.error).toBe(
        'Request timed out. The server may be starting up — please try again.',
      );
    });

    it('sets error state with message on network failure', async () => {
      mockGetKnowledgeModel.mockRejectedValue(
        new KnowledgeModelNetworkError('network', 'Connection refused'),
      );

      await getState().fetchKnowledgeModel('doc-123');

      const state = getState();
      expect(state.status).toBe('error');
      expect(state.error).toBe(
        'Unable to reach the server. Please check your connection.',
      );
    });

    it('sets generic error message for unknown errors', async () => {
      mockGetKnowledgeModel.mockRejectedValue(new Error('something unexpected'));

      await getState().fetchKnowledgeModel('doc-123');

      const state = getState();
      expect(state.status).toBe('error');
      expect(state.error).toBe('Failed to load the Knowledge Model.');
    });

    it('allows retry from error state (error → loading)', async () => {
      // First fetch fails
      mockGetKnowledgeModel.mockRejectedValueOnce(
        new KnowledgeModelNetworkError('network', 'Failed'),
      );
      await getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('error');

      // Retry succeeds
      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValueOnce(mockResponse);
      await getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('loaded');
    });

    it('clears selection and history on new fetch', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      await getState().fetchKnowledgeModel('doc-123');
      getState().selectElement('elem-0');
      getState().navigateToElement('elem-1');

      expect(getState().selectedElementId).toBe('elem-1');
      expect(getState().navigationHistory).toEqual(['elem-0']);

      // Fetch different document clears everything
      const mockResponse2 = createMockKnowledgeModel('doc-456', 2);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse2);
      await getState().fetchKnowledgeModel('doc-456');

      expect(getState().selectedElementId).toBeNull();
      expect(getState().navigationHistory).toEqual([]);
    });
  });

  describe('selectElement', () => {
    it('sets selectedElementId and clears navigation history', () => {
      // Setup some history first
      getState().navigateToElement('elem-0');
      getState().navigateToElement('elem-1');

      // Select clears history
      getState().selectElement('elem-2');

      const state = getState();
      expect(state.selectedElementId).toBe('elem-2');
      expect(state.navigationHistory).toEqual([]);
    });
  });

  describe('navigateToElement', () => {
    it('pushes current selection to history and sets new selection', () => {
      getState().selectElement('elem-0');
      getState().navigateToElement('elem-1');

      const state = getState();
      expect(state.selectedElementId).toBe('elem-1');
      expect(state.navigationHistory).toEqual(['elem-0']);
    });

    it('builds up history stack through multiple navigations', () => {
      getState().selectElement('elem-0');
      getState().navigateToElement('elem-1');
      getState().navigateToElement('elem-2');
      getState().navigateToElement('elem-3');

      const state = getState();
      expect(state.selectedElementId).toBe('elem-3');
      expect(state.navigationHistory).toEqual(['elem-0', 'elem-1', 'elem-2']);
    });

    it('caps navigation history at 50 entries', () => {
      // Select initial element
      getState().selectElement('elem-start');

      // Navigate 55 times
      for (let i = 0; i < 55; i++) {
        getState().navigateToElement(`elem-${i}`);
      }

      const state = getState();
      expect(state.navigationHistory.length).toBe(50);
      // The oldest entries should have been trimmed
      expect(state.navigationHistory[0]).not.toBe('elem-start');
    });

    it('does not push null to history when no current selection exists', () => {
      // No selection made yet — selectedElementId is null
      getState().navigateToElement('elem-1');

      const state = getState();
      expect(state.selectedElementId).toBe('elem-1');
      expect(state.navigationHistory).toEqual([]);
    });
  });

  describe('goBack', () => {
    it('pops last element from history and sets as selected', () => {
      getState().selectElement('elem-0');
      getState().navigateToElement('elem-1');
      getState().navigateToElement('elem-2');

      getState().goBack();

      const state = getState();
      expect(state.selectedElementId).toBe('elem-1');
      expect(state.navigationHistory).toEqual(['elem-0']);
    });

    it('deselects when history is empty', () => {
      getState().selectElement('elem-0');

      getState().goBack();

      const state = getState();
      expect(state.selectedElementId).toBeNull();
      expect(state.navigationHistory).toEqual([]);
    });

    it('supports multiple back navigations through the stack', () => {
      getState().selectElement('elem-0');
      getState().navigateToElement('elem-1');
      getState().navigateToElement('elem-2');

      getState().goBack(); // → elem-1
      expect(getState().selectedElementId).toBe('elem-1');

      getState().goBack(); // → elem-0
      expect(getState().selectedElementId).toBe('elem-0');

      getState().goBack(); // → null (empty history)
      expect(getState().selectedElementId).toBeNull();
    });
  });

  describe('setViewMode', () => {
    it('changes view mode to graph', () => {
      getState().setViewMode('graph');
      expect(getState().viewMode).toBe('graph');
    });

    it('changes view mode back to list', () => {
      getState().setViewMode('graph');
      getState().setViewMode('list');
      expect(getState().viewMode).toBe('list');
    });
  });

  describe('reset', () => {
    it('resets all state to initial values', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      // Set up some state
      await getState().fetchKnowledgeModel('doc-123');
      getState().selectElement('elem-0');
      getState().navigateToElement('elem-1');
      getState().setViewMode('graph');

      // Reset
      getState().reset();

      const state = getState();
      expect(state.status).toBe('idle');
      expect(state.knowledgeModel).toBeNull();
      expect(state.selectedElementId).toBeNull();
      expect(state.viewMode).toBe('list');
      expect(state.navigationHistory).toEqual([]);
      expect(state.error).toBeNull();
      expect(state.documentId).toBeNull();
    });
  });

  describe('State Transitions', () => {
    it('follows idle → loading → loaded transition', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      expect(getState().status).toBe('idle');

      const promise = getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('loading');

      await promise;
      expect(getState().status).toBe('loaded');
    });

    it('follows idle → loading → empty transition', async () => {
      const mockResponse = createMockKnowledgeModel('doc-123', 0);
      mockGetKnowledgeModel.mockResolvedValue(mockResponse);

      const promise = getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('loading');

      await promise;
      expect(getState().status).toBe('empty');
    });

    it('follows idle → loading → error transition', async () => {
      mockGetKnowledgeModel.mockRejectedValue(new Error('fail'));

      const promise = getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('loading');

      await promise;
      expect(getState().status).toBe('error');
    });

    it('follows error → loading → loaded transition (retry)', async () => {
      mockGetKnowledgeModel.mockRejectedValueOnce(new Error('fail'));
      await getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('error');

      const mockResponse = createMockKnowledgeModel('doc-123', 3);
      mockGetKnowledgeModel.mockResolvedValueOnce(mockResponse);
      await getState().fetchKnowledgeModel('doc-123');
      expect(getState().status).toBe('loaded');
    });
  });
});
