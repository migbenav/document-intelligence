import { create } from 'zustand';
import {
  getAnalysisStatuses,
  triggerAnalysis as apiTriggerAnalysis,
  getAnalysisResult,
  AnalysisApiError,
} from '@/api/analyses';
import type { AnalysisErrorCode } from '@/api/analyses';
import type { AnalysisType, AnalysisStatusSummary } from '@/types/analysis';

// --- Types ---

/** Metadata about which model produced an analysis result. */
export interface AnalysisModelInfo {
  model_id: string | null;
  fallback_used: boolean;
}

export interface AnalysisStore {
  // State
  statuses: AnalysisStatusSummary | null;
  results: Partial<Record<AnalysisType, unknown>>;
  modelInfo: Partial<Record<AnalysisType, AnalysisModelInfo>>;
  activeAnalysis: AnalysisType | null;
  error: string | null;
  errorCode: AnalysisErrorCode | null;
  errorModelId: string | null;

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
  modelInfo: {} as Partial<Record<AnalysisType, AnalysisModelInfo>>,
  activeAnalysis: null as AnalysisType | null,
  error: null as string | null,
  errorCode: null as AnalysisErrorCode | null,
  errorModelId: null as string | null,
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
    set({ activeAnalysis: type, error: null, errorCode: null, errorModelId: null });

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
        modelInfo: {
          ...get().modelInfo,
          [type]: { model_id: record.model_id, fallback_used: record.fallback_used ?? false },
        },
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
      const errorCode: AnalysisErrorCode | null =
        err instanceof AnalysisApiError ? err.errorCode : null;
      const errorModelId: string | null =
        err instanceof AnalysisApiError ? (err.modelId ?? null) : null;
      const updatedStatuses = get().statuses;
      set({
        error: message,
        errorCode,
        errorModelId,
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
        modelInfo: {
          ...get().modelInfo,
          [type]: { model_id: record.model_id, fallback_used: record.fallback_used ?? false },
        },
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
