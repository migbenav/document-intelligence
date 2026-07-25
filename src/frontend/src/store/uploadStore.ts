import { create } from 'zustand';
import { uploadDocument, getDocumentStatus, ApiError } from '@/api/documents';
import { POLL_INTERVAL_MS, MAX_POLL_FAILURES } from '@/api/client';

// --- Types ---

export type UploadStep =
  | 'idle'
  | 'file-selected'
  | 'consent-pending'
  | 'uploading'
  | 'processing'
  | 'ready'
  | 'error';

export type FileFormat = 'markdown' | 'plain_text' | 'pdf';

export interface SelectedFile {
  file: File;
  name: string;
  size: number;
  format: FileFormat;
}

export interface UploadResult {
  documentId: string;
  filename: string;
  format: string;
  language: string | null;
  chunkCount: number | null;
  warnings: string[];
}

export interface UploadError {
  type: 'validation' | 'network' | 'server' | 'processing' | 'connectivity';
  message: string;
  canRetry: boolean;
}

export interface UploadStore {
  // State
  step: UploadStep;
  selectedFile: SelectedFile | null;
  uploadProgress: number;
  result: UploadResult | null;
  error: UploadError | null;
  documentId: string | null;

  // Actions
  selectFile: (file: File) => void;
  openConsent: () => void;
  acceptConsent: () => void;
  declineConsent: () => void;
  startUpload: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
  reset: () => void;
}

// --- Helpers ---

function deriveFormat(filename: string): FileFormat {
  const ext = filename.toLowerCase().split('.').pop();
  switch (ext) {
    case 'md':
      return 'markdown';
    case 'pdf':
      return 'pdf';
    case 'txt':
    default:
      return 'plain_text';
  }
}

function classifyError(err: unknown): UploadError {
  if (err instanceof ApiError) {
    // Backend validation or processing error
    const errorCode = err.error;
    if (
      errorCode === 'unsupported_format' ||
      errorCode === 'file_too_large' ||
      errorCode === 'invalid_encoding'
    ) {
      return { type: 'validation', message: err.message, canRetry: false };
    }
    return { type: 'server', message: err.message, canRetry: true };
  }

  if (err instanceof Error) {
    if (err.message.includes('Network error') || err.message.includes('timed out')) {
      return { type: 'network', message: err.message, canRetry: true };
    }
    return { type: 'server', message: err.message, canRetry: true };
  }

  return { type: 'server', message: 'An unexpected error occurred', canRetry: true };
}

// --- Initial State ---

const initialState = {
  step: 'idle' as UploadStep,
  selectedFile: null as SelectedFile | null,
  uploadProgress: 0,
  result: null as UploadResult | null,
  error: null as UploadError | null,
  documentId: null as string | null,
};

// --- Store ---

// Internal polling state kept outside Zustand to avoid re-renders
let pollIntervalId: ReturnType<typeof setInterval> | null = null;
let pollAbortController: AbortController | null = null;
let consecutiveFailures = 0;

export const useUploadStore = create<UploadStore>((set, get) => ({
  ...initialState,

  selectFile: (file: File) => {
    const format = deriveFormat(file.name);
    set({
      step: 'file-selected',
      selectedFile: { file, name: file.name, size: file.size, format },
      uploadProgress: 0,
      result: null,
      error: null,
      documentId: null,
    });
  },

  openConsent: () => {
    const { step } = get();
    if (step !== 'file-selected') return;
    set({ step: 'consent-pending' });
  },

  acceptConsent: () => {
    const { step } = get();
    if (step !== 'consent-pending') return;
    set({ step: 'uploading', uploadProgress: 0 });
    // Fire and forget — startUpload manages its own transitions
    void get().startUpload();
  },

  declineConsent: () => {
    const { step } = get();
    if (step !== 'consent-pending') return;
    set({ step: 'file-selected' });
  },

  startUpload: async () => {
    const { selectedFile, step } = get();
    // Guard: only upload from uploading state (set by acceptConsent)
    if (step !== 'uploading' || !selectedFile) return;

    try {
      const response = await uploadDocument(selectedFile.file, {
        onProgress: (percent) => {
          set({ uploadProgress: percent });
        },
      });

      // Upload successful — transition to processing
      set({
        step: 'processing',
        documentId: response.document_id,
        uploadProgress: 100,
      });

      // Start polling for status
      get().startPolling();
    } catch (err) {
      const uploadError = classifyError(err);
      set({ step: 'error', error: uploadError });
    }
  },

  startPolling: () => {
    const { documentId } = get();
    if (!documentId) return;

    // Clean up any existing polling
    get().stopPolling();

    consecutiveFailures = 0;
    pollAbortController = new AbortController();

    const poll = async () => {
      const currentDocId = get().documentId;
      const currentStep = get().step;
      if (currentStep !== 'processing' || !currentDocId) {
        get().stopPolling();
        return;
      }

      try {
        const status = await getDocumentStatus(currentDocId, {
          signal: pollAbortController?.signal,
        });

        consecutiveFailures = 0;

        if (status.status === 'ready') {
          if (status.chunk_count && status.chunk_count > 0) {
            set({
              step: 'ready',
              result: {
                documentId: status.document_id,
                filename: status.filename,
                format: status.format,
                language: status.language,
                chunkCount: status.chunk_count,
                warnings: status.warnings,
              },
            });
          } else {
            set({
              step: 'error',
              error: {
                type: 'processing',
                message: 'No extractable content was found in this document.',
                canRetry: false,
              },
            });
          }
          get().stopPolling();
        } else if (status.status === 'failed') {
          set({
            step: 'error',
            error: {
              type: 'processing',
              message: status.error_message || 'Processing failed',
              canRetry: false,
            },
          });
          get().stopPolling();
        }
        // status === 'processing' → continue polling
      } catch (err) {
        // Ignore aborted requests (expected during cleanup)
        if (err instanceof Error && err.name === 'AbortError') return;

        consecutiveFailures++;
        if (consecutiveFailures >= MAX_POLL_FAILURES) {
          set({
            step: 'error',
            error: {
              type: 'connectivity',
              message: 'Unable to reach the server. Please check your connection.',
              canRetry: false,
            },
          });
          get().stopPolling();
        }
      }
    };

    // Run first poll immediately then set interval
    void poll();
    pollIntervalId = setInterval(() => void poll(), POLL_INTERVAL_MS);
  },

  stopPolling: () => {
    if (pollIntervalId !== null) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
    if (pollAbortController) {
      pollAbortController.abort();
      pollAbortController = null;
    }
    consecutiveFailures = 0;
  },

  reset: () => {
    get().stopPolling();
    set({ ...initialState });
  },
}));
