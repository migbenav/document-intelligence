import { create } from 'zustand';
import {
  getKnowledgeModel,
  KnowledgeModelApiError,
  KnowledgeModelNetworkError,
} from '@/api/knowledgeModel';
import { runFullAnalysis } from '@/api/analysis';
import type { KnowledgeModelResponse } from '@/types/knowledgeModel';

// --- Types ---

export type KMStatus = 'idle' | 'loading' | 'loaded' | 'error' | 'empty';
export type ViewMode = 'list' | 'graph';

export interface KnowledgeModelStore {
  // State
  status: KMStatus;
  knowledgeModel: KnowledgeModelResponse | null;
  selectedElementId: string | null;
  viewMode: ViewMode;
  navigationHistory: string[];
  error: string | null;
  documentId: string | null;

  // Actions
  fetchKnowledgeModel: (documentId: string) => Promise<void>;
  selectElement: (elementId: string) => void;
  navigateToElement: (elementId: string) => void;
  goBack: () => void;
  setViewMode: (mode: ViewMode) => void;
  reset: () => void;
}

// --- Constants ---

const MAX_HISTORY_LENGTH = 50;
const KM_POLL_INTERVAL_MS = 3_000;
const KM_POLL_MAX_ATTEMPTS = 40; // 40 * 3s = 2 minutes max

// --- Helpers ---

async function pollForKnowledgeModel(
  documentId: string,
): Promise<KnowledgeModelResponse> {
  for (let i = 0; i < KM_POLL_MAX_ATTEMPTS; i++) {
    try {
      return await getKnowledgeModel(documentId);
    } catch (err) {
      // If not ready or not found, wait and retry
      if (
        err instanceof KnowledgeModelApiError &&
        (err.code === 'not_ready' || err.code === 'not_found')
      ) {
        await new Promise((resolve) => setTimeout(resolve, KM_POLL_INTERVAL_MS));
        continue;
      }
      throw err;
    }
  }
  throw new Error('Analysis timed out. The document may be too large or the server is busy.');
}

// --- Initial State ---

const initialState = {
  status: 'idle' as KMStatus,
  knowledgeModel: null as KnowledgeModelResponse | null,
  selectedElementId: null as string | null,
  viewMode: 'list' as ViewMode,
  navigationHistory: [] as string[],
  error: null as string | null,
  documentId: null as string | null,
};

// --- Store ---

export const useKnowledgeModelStore = create<KnowledgeModelStore>((set, get) => ({
  ...initialState,

  fetchKnowledgeModel: async (documentId: string) => {
    const { documentId: cachedDocId, status } = get();

    // Cache hit: same document already loaded, skip fetch
    if (documentId === cachedDocId && status === 'loaded') {
      return;
    }

    // Reset state for a new fetch
    set({
      status: 'loading',
      error: null,
      knowledgeModel: null,
      selectedElementId: null,
      navigationHistory: [],
      documentId,
    });

    try {
      const response = await getKnowledgeModel(documentId);

      if (response.elements.length === 0) {
        set({ status: 'empty', knowledgeModel: response });
      } else {
        set({ status: 'loaded', knowledgeModel: response });
      }
    } catch (err) {
      // If KM not found, auto-trigger the analysis pipeline
      if (err instanceof KnowledgeModelApiError && (err.code === 'not_found' || err.code === 'not_ready')) {
        try {
          await runFullAnalysis(documentId);
          // Poll for KM with retries (analysis may take time)
          const response = await pollForKnowledgeModel(documentId);
          if (response.elements.length === 0) {
            set({ status: 'empty', knowledgeModel: response });
          } else {
            set({ status: 'loaded', knowledgeModel: response });
          }
          return;
        } catch (analysisErr) {
          const message =
            analysisErr instanceof Error
              ? analysisErr.message
              : 'Analysis failed. Please try again.';
          set({ status: 'error', error: message });
          return;
        }
      }

      let message: string;

      if (err instanceof KnowledgeModelApiError) {
        switch (err.code) {
          case 'not_ready':
            message = 'Analysis is not yet completed. Please wait and try again.';
            break;
          default:
            message = 'Failed to load the Knowledge Model.';
        }
      } else if (err instanceof KnowledgeModelNetworkError) {
        switch (err.code) {
          case 'timeout':
            message =
              'Request timed out. The server may be starting up — please try again.';
            break;
          case 'network':
            message = 'Unable to reach the server. Please check your connection.';
            break;
          default:
            message = 'Failed to load the Knowledge Model.';
        }
      } else {
        message = 'Failed to load the Knowledge Model.';
      }

      set({ status: 'error', error: message });
    }
  },

  selectElement: (elementId: string) => {
    set({
      selectedElementId: elementId,
      navigationHistory: [],
    });
  },

  navigateToElement: (elementId: string) => {
    const { selectedElementId, navigationHistory } = get();

    let newHistory = [...navigationHistory];

    // Push current selection to history if there is one
    if (selectedElementId !== null) {
      newHistory.push(selectedElementId);
    }

    // Cap history at MAX_HISTORY_LENGTH
    if (newHistory.length > MAX_HISTORY_LENGTH) {
      newHistory = newHistory.slice(newHistory.length - MAX_HISTORY_LENGTH);
    }

    set({
      selectedElementId: elementId,
      navigationHistory: newHistory,
    });
  },

  goBack: () => {
    const { navigationHistory } = get();

    if (navigationHistory.length === 0) {
      // Empty history — deselect
      set({ selectedElementId: null });
      return;
    }

    const newHistory = [...navigationHistory];
    const previousId = newHistory.pop()!;

    set({
      selectedElementId: previousId,
      navigationHistory: newHistory,
    });
  },

  setViewMode: (mode: ViewMode) => {
    set({ viewMode: mode });
  },

  reset: () => {
    set({ ...initialState });
  },
}));
