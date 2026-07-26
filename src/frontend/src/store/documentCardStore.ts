import { create } from 'zustand';
import { fetchCard, retryLlm } from '@/api/documentCard';
import type { DocumentCard } from '@/types/documentCard';

// --- Store Interface ---

export interface DocumentCardStore {
  // State
  card: DocumentCard | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchCard: (documentId: string) => Promise<void>;
  retryLlm: (documentId: string) => Promise<void>;
  reset: () => void;
}

// --- Initial State ---

const initialState = {
  card: null as DocumentCard | null,
  loading: false,
  error: null as string | null,
};

// --- Store ---

export const useDocumentCardStore = create<DocumentCardStore>((set) => ({
  ...initialState,

  fetchCard: async (documentId: string) => {
    set({ loading: true, error: null });
    try {
      const card = await fetchCard(documentId);
      set({ card, loading: false });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to fetch document card';
      set({ error: message, loading: false });
    }
  },

  retryLlm: async (documentId: string) => {
    set({ loading: true, error: null });
    try {
      const card = await retryLlm(documentId);
      set({ card, loading: false });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to retry LLM analysis';
      set({ error: message, loading: false });
    }
  },

  reset: () => {
    set({ ...initialState });
  },
}));
