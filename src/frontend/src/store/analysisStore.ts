import { create } from 'zustand';
import {
  getAnalysisStatuses,
  triggerAnalysis as apiTriggerAnalysis,
  getAnalysisResult,
} from '@/api/analyses';
import type { AnalysisType, AnalysisStatusSummary } from '@/types/analysis';

// --- Types ---

export interface AnalysisStore {
  // State
  statuses: AnalysisStatusSummary | null;
  results: Partial<Record<AnalysisType, unknown>>;
  activeAnalysis: AnalysisType | null;
  error: string | null;

  // Actions
  fetchStatuses: (documentId: string) => Promise<void>;
  triggerAnalysis: (documentId: string, type: AnalysisType) => Promise<void>;
  fetchResult: (documentId: string, type: AnalysisType) => Promise<void>;
  reset: () => void;
}

// --- Initial State ---

const initialState = {
  statuses: null as AnalysisStatusSummary | null,
  results: {} as Partial<Record<AnalysisType, unknown>>,
  activeAnalysis: null as AnalysisType | null,
  error: null as string | null,
};

// --- Store ---

export const useAnalysisStore = create<AnalysisStore>((set, get) => ({
  ...initialState,

  fetchStatuses: async (documentId: string) => {
    try {
      const statuses = await getAnalysisStatuses(documentId);
      set({ statuses, error: null });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch analysis statuses.';
      set({ error: message });
    }
  },

  triggerAnalysis: async (documentId: string, type: AnalysisType) => {
    // 1. Set activeAnalysis (shows spinner)
    set({ activeAnalysis: type, error: null });

    // 2. Optimistically update status for that type to "in_progress"
    const currentStatuses = get().statuses;
    if (currentStatuses) {
      set({
        statuses: {
          ...currentStatuses,
          [type]: { ...currentStatuses[type], status: 'in_progress' },
        },
      });
    }

    try {
      // 3. Call the API
      const record = await apiTriggerAnalysis(documentId, type);

      // 4. On success: update result, update status to "completed", clear activeAnalysis
      const updatedStatuses = get().statuses;
      set({
        results: { ...get().results, [type]: record.result },
        statuses: updatedStatuses
          ? {
              ...updatedStatuses,
              [type]: { status: 'completed', updated_at: record.updated_at },
            }
          : null,
        activeAnalysis: null,
        error: null,
      });
    } catch (err) {
      // 5. On failure: set error, update status to "failed", clear activeAnalysis
      const message =
        err instanceof Error ? err.message : 'Analysis failed. Please try again.';
      const updatedStatuses = get().statuses;
      set({
        error: message,
        statuses: updatedStatuses
          ? {
              ...updatedStatuses,
              [type]: { ...updatedStatuses[type], status: 'failed' },
            }
          : null,
        activeAnalysis: null,
      });
    }
  },

  fetchResult: async (documentId: string, type: AnalysisType) => {
    try {
      const record = await getAnalysisResult(documentId, type);
      set({
        results: { ...get().results, [type]: record.result },
        error: null,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch analysis result.';
      set({ error: message });
    }
  },

  reset: () => {
    set({ ...initialState });
  },
}));
