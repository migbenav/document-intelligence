import { create } from 'zustand';
import { API_BASE_URL, apiFetch } from '@/api/client';

// --- Types ---

export interface QuerySourceRef {
  document_id: string;
  chunk_id: string;
  page: number | null;
  section: string | null;
  evidence: string;
  evidence_verified: boolean;
}

export interface QueryMetadata {
  prompt_version: string;
  model_id: string;
  temperature: number;
  timestamp: string;
}

export interface QueryResponse {
  answer: string;
  answerable: boolean;
  source_refs: QuerySourceRef[];
  all_evidence_unverified: boolean;
  metadata: QueryMetadata;
}

export interface Message {
  question: string;
  answer: QueryResponse | null;
  error: string | null;
}

export interface QueryStore {
  // State
  messages: Message[];
  isLoading: boolean;
  error: string | null;

  // Actions
  submitQuery: (documentId: string, question: string) => Promise<void>;
  clearMessages: () => void;
}

// --- Constants ---

const QUERY_TIMEOUT_MS = 30_000;

// --- Helpers ---

function classifyQueryError(status: number, _body: unknown): string {
  if (status === 404) {
    return 'Document not found.';
  }
  if (status === 409) {
    return 'Knowledge Model analysis must be completed before querying.';
  }
  if (status === 422) {
    return 'Invalid question. Please check the length and try again.';
  }
  if (status >= 500) {
    return 'An error occurred while processing your question. Please try again later.';
  }
  return 'An unexpected error occurred. Please try again.';
}

// --- Initial State ---

const initialState = {
  messages: [] as Message[],
  isLoading: false,
  error: null as string | null,
};

// --- Store ---

export const useQueryStore = create<QueryStore>((set, get) => ({
  ...initialState,

  submitQuery: async (documentId: string, question: string) => {
    const { isLoading } = get();
    if (isLoading) return;

    // Add the question to messages immediately (answer pending)
    const newMessage: Message = { question, answer: null, error: null };
    set((state) => ({
      messages: [...state.messages, newMessage],
      isLoading: true,
      error: null,
    }));

    const messageIndex = get().messages.length - 1;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), QUERY_TIMEOUT_MS);

      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/documents/${documentId}/query`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
          signal: controller.signal,
        },
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        let body: unknown = null;
        try {
          body = await response.json();
        } catch {
          // Ignore parse errors for error responses
        }
        const errorMessage = classifyQueryError(response.status, body);

        set((state) => {
          const updatedMessages = [...state.messages];
          const existing = updatedMessages[messageIndex];
          if (!existing) return { isLoading: false };
          updatedMessages[messageIndex] = {
            question: existing.question,
            answer: existing.answer,
            error: errorMessage,
          };
          return { messages: updatedMessages, isLoading: false };
        });
        return;
      }

      const data: QueryResponse = await response.json();

      set((state) => {
        const updatedMessages = [...state.messages];
        const existing = updatedMessages[messageIndex];
        if (!existing) return { isLoading: false };
        updatedMessages[messageIndex] = {
          question: existing.question,
          answer: data,
          error: existing.error,
        };
        return { messages: updatedMessages, isLoading: false };
      });
    } catch (err) {
      let errorMessage: string;

      if (err instanceof Error && err.name === 'AbortError') {
        errorMessage = 'Request timed out. Please try again.';
      } else if (err instanceof Error && err.message.includes('fetch')) {
        errorMessage = 'Unable to reach the server. Please check your connection.';
      } else {
        errorMessage = 'An unexpected error occurred. Please try again.';
      }

      set((state) => {
        const updatedMessages = [...state.messages];
        const existing = updatedMessages[messageIndex];
        if (!existing) return { isLoading: false };
        updatedMessages[messageIndex] = {
          question: existing.question,
          answer: existing.answer,
          error: errorMessage,
        };
        return { messages: updatedMessages, isLoading: false };
      });
    }
  },

  clearMessages: () => {
    set({ ...initialState });
  },
}));
