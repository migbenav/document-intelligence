import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useAnalysisStore } from '@/store/analysisStore';
import type { AnalysisStatusSummary, AnalysisRecord } from '@/types/analysis';

// Mock the API module
vi.mock('@/api/analyses', () => ({
  getAnalysisStatuses: vi.fn(),
  triggerAnalysis: vi.fn(),
  getAnalysisResult: vi.fn(),
}));

import {
  getAnalysisStatuses,
  triggerAnalysis as apiTriggerAnalysis,
  getAnalysisResult,
} from '@/api/analyses';

const mockGetAnalysisStatuses = vi.mocked(getAnalysisStatuses);
const mockTriggerAnalysis = vi.mocked(apiTriggerAnalysis);
const mockGetAnalysisResult = vi.mocked(getAnalysisResult);

function getState() {
  return useAnalysisStore.getState();
}

const mockStatuses: AnalysisStatusSummary = {
  build_index: { status: 'not_started', updated_at: null },
  section_relations: { status: 'not_started', updated_at: null },
  questions_answered: { status: 'completed', updated_at: '2024-01-01T00:00:00Z' },
  conclusions: { status: 'not_started', updated_at: null },
};

const mockAnalysisRecord: AnalysisRecord = {
  analysis_type: 'build_index',
  status: 'completed',
  result: { tree: [] },
  model_id: 'gemini-2.5-flash',
  prompt_version: 'v1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T12:00:00Z',
};

describe('analysisStore', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset();
    vi.clearAllMocks();
  });

  describe('Initial State', () => {
    it('starts with null statuses, empty results, no active analysis, no error', () => {
      const state = getState();
      expect(state.statuses).toBeNull();
      expect(state.results).toEqual({});
      expect(state.activeAnalysis).toBeNull();
      expect(state.error).toBeNull();
    });
  });

  describe('fetchStatuses', () => {
    it('fetches and stores analysis statuses on success', async () => {
      mockGetAnalysisStatuses.mockResolvedValue(mockStatuses);

      await getState().fetchStatuses('doc-123');

      const state = getState();
      expect(state.statuses).toEqual(mockStatuses);
      expect(state.error).toBeNull();
      expect(mockGetAnalysisStatuses).toHaveBeenCalledWith('doc-123');
    });

    it('sets error on failure', async () => {
      mockGetAnalysisStatuses.mockRejectedValue(new Error('Network error'));

      await getState().fetchStatuses('doc-123');

      const state = getState();
      expect(state.error).toBe('Network error');
      expect(state.statuses).toBeNull();
    });
  });

  describe('triggerAnalysis', () => {
    it('sets activeAnalysis and optimistically updates status to in_progress', async () => {
      // Pre-populate statuses
      mockGetAnalysisStatuses.mockResolvedValue(mockStatuses);
      await getState().fetchStatuses('doc-123');

      // Make triggerAnalysis hang so we can inspect intermediate state
      let resolveApi!: (value: AnalysisRecord) => void;
      mockTriggerAnalysis.mockImplementation(
        () => new Promise((resolve) => { resolveApi = resolve; }),
      );

      const promise = getState().triggerAnalysis('doc-123', 'build_index');

      // Intermediate state: activeAnalysis set, status is in_progress
      expect(getState().activeAnalysis).toBe('build_index');
      expect(getState().statuses!.build_index.status).toBe('in_progress');
      expect(getState().error).toBeNull();

      // Resolve the API call
      resolveApi(mockAnalysisRecord);
      await promise;

      // Final state: result stored, status completed, activeAnalysis cleared
      const state = getState();
      expect(state.activeAnalysis).toBeNull();
      expect(state.results.build_index).toEqual({ tree: [] });
      expect(state.statuses!.build_index.status).toBe('completed');
      expect(state.statuses!.build_index.updated_at).toBe('2024-01-01T12:00:00Z');
      expect(state.error).toBeNull();
    });

    it('sets error and status to failed on API failure', async () => {
      // Pre-populate statuses
      mockGetAnalysisStatuses.mockResolvedValue(mockStatuses);
      await getState().fetchStatuses('doc-123');

      mockTriggerAnalysis.mockRejectedValue(new Error('LLM timeout'));

      await getState().triggerAnalysis('doc-123', 'build_index');

      const state = getState();
      expect(state.activeAnalysis).toBeNull();
      expect(state.error).toBe('LLM timeout');
      expect(state.statuses!.build_index.status).toBe('failed');
    });

    it('works when statuses is null (no prior fetch)', async () => {
      mockTriggerAnalysis.mockResolvedValue(mockAnalysisRecord);

      await getState().triggerAnalysis('doc-123', 'build_index');

      const state = getState();
      expect(state.activeAnalysis).toBeNull();
      expect(state.results.build_index).toEqual({ tree: [] });
      expect(state.error).toBeNull();
    });
  });

  describe('fetchResult', () => {
    it('fetches and stores analysis result on success', async () => {
      mockGetAnalysisResult.mockResolvedValue(mockAnalysisRecord);

      await getState().fetchResult('doc-123', 'build_index');

      const state = getState();
      expect(state.results.build_index).toEqual({ tree: [] });
      expect(state.error).toBeNull();
      expect(mockGetAnalysisResult).toHaveBeenCalledWith('doc-123', 'build_index');
    });

    it('sets error on failure', async () => {
      mockGetAnalysisResult.mockRejectedValue(new Error('Not found'));

      await getState().fetchResult('doc-123', 'build_index');

      const state = getState();
      expect(state.error).toBe('Not found');
    });
  });

  describe('reset', () => {
    it('clears all state back to initial values', async () => {
      // Set up some state
      mockGetAnalysisStatuses.mockResolvedValue(mockStatuses);
      await getState().fetchStatuses('doc-123');
      mockGetAnalysisResult.mockResolvedValue(mockAnalysisRecord);
      await getState().fetchResult('doc-123', 'build_index');

      // Reset
      getState().reset();

      const state = getState();
      expect(state.statuses).toBeNull();
      expect(state.results).toEqual({});
      expect(state.activeAnalysis).toBeNull();
      expect(state.error).toBeNull();
    });
  });
});
