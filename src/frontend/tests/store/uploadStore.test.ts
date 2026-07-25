import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useUploadStore } from '@/store/uploadStore';
import type { UploadStep } from '@/store/uploadStore';

// Mock the API modules
vi.mock('@/api/documents', () => ({
  uploadDocument: vi.fn(),
  getDocumentStatus: vi.fn(),
  ApiError: class ApiError extends Error {
    error: string;
    constructor(response: { error: string; message: string }) {
      super(response.message);
      this.name = 'ApiError';
      this.error = response.error;
    }
  },
}));

vi.mock('@/api/client', () => ({
  POLL_INTERVAL_MS: 100, // Fast polling for tests
  MAX_POLL_FAILURES: 3,
}));

import { uploadDocument, getDocumentStatus, ApiError } from '@/api/documents';

const mockUploadDocument = vi.mocked(uploadDocument);
const mockGetDocumentStatus = vi.mocked(getDocumentStatus);

function createMockFile(name = 'test.md', size = 1024): File {
  const content = new Uint8Array(size);
  return new File([content], name, { type: 'text/plain' });
}

function getState() {
  return useUploadStore.getState();
}

function act(fn: () => void) {
  fn();
}

describe('uploadStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useUploadStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useUploadStore.getState().stopPolling();
    vi.useRealTimers();
  });

  describe('Initial State', () => {
    it('starts in idle state with all fields null/zero', () => {
      const state = getState();
      expect(state.step).toBe('idle');
      expect(state.selectedFile).toBeNull();
      expect(state.uploadProgress).toBe(0);
      expect(state.result).toBeNull();
      expect(state.error).toBeNull();
      expect(state.documentId).toBeNull();
    });
  });

  describe('selectFile', () => {
    it('transitions from idle to file-selected', () => {
      const file = createMockFile('document.md', 500);
      act(() => getState().selectFile(file));

      const state = getState();
      expect(state.step).toBe('file-selected');
      expect(state.selectedFile).not.toBeNull();
      expect(state.selectedFile!.name).toBe('document.md');
      expect(state.selectedFile!.size).toBe(500);
      expect(state.selectedFile!.format).toBe('markdown');
    });

    it('derives format correctly for .txt files', () => {
      act(() => getState().selectFile(createMockFile('notes.txt')));
      expect(getState().selectedFile!.format).toBe('plain_text');
    });

    it('derives format correctly for .pdf files', () => {
      act(() => getState().selectFile(createMockFile('report.pdf')));
      expect(getState().selectedFile!.format).toBe('pdf');
    });

    it('clears previous error state when selecting a new file', () => {
      // Simulate an error state
      useUploadStore.setState({
        step: 'error',
        error: { type: 'network', message: 'fail', canRetry: true },
      });

      act(() => getState().selectFile(createMockFile('new.md')));
      expect(getState().step).toBe('file-selected');
      expect(getState().error).toBeNull();
    });

    it('handles rapid file changes (replaces previous selection)', () => {
      act(() => getState().selectFile(createMockFile('first.md')));
      act(() => getState().selectFile(createMockFile('second.txt')));

      const state = getState();
      expect(state.selectedFile!.name).toBe('second.txt');
      expect(state.selectedFile!.format).toBe('plain_text');
    });
  });

  describe('openConsent', () => {
    it('transitions from file-selected to consent-pending', () => {
      act(() => getState().selectFile(createMockFile()));
      act(() => getState().openConsent());
      expect(getState().step).toBe('consent-pending');
    });

    it('does nothing if not in file-selected state', () => {
      // From idle
      act(() => getState().openConsent());
      expect(getState().step).toBe('idle');
    });

    it('does nothing if in uploading state', () => {
      useUploadStore.setState({ step: 'uploading' });
      act(() => getState().openConsent());
      expect(getState().step).toBe('uploading');
    });
  });

  describe('acceptConsent', () => {
    it('transitions from consent-pending to uploading and triggers startUpload', () => {
      mockUploadDocument.mockResolvedValue({
        document_id: 'doc-123',
        status: 'processing',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });

      const file = createMockFile();
      act(() => getState().selectFile(file));
      act(() => getState().openConsent());
      act(() => getState().acceptConsent());

      expect(getState().step).toBe('uploading');
      expect(mockUploadDocument).toHaveBeenCalledWith(file, expect.any(Object));
    });

    it('does nothing if not in consent-pending state', () => {
      act(() => getState().selectFile(createMockFile()));
      // In file-selected, not consent-pending
      act(() => getState().acceptConsent());
      expect(getState().step).toBe('file-selected');
      expect(mockUploadDocument).not.toHaveBeenCalled();
    });
  });

  describe('declineConsent', () => {
    it('transitions from consent-pending back to file-selected', () => {
      act(() => getState().selectFile(createMockFile()));
      act(() => getState().openConsent());
      act(() => getState().declineConsent());

      expect(getState().step).toBe('file-selected');
      expect(getState().selectedFile).not.toBeNull();
    });

    it('does nothing if not in consent-pending state', () => {
      act(() => getState().selectFile(createMockFile()));
      act(() => getState().declineConsent());
      expect(getState().step).toBe('file-selected');
    });
  });

  describe('startUpload', () => {
    it('transitions to processing on successful upload (202)', async () => {
      mockUploadDocument.mockResolvedValue({
        document_id: 'doc-456',
        status: 'processing',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });
      // Mock getDocumentStatus for polling that starts after upload
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-456',
        status: 'processing',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });

      const file = createMockFile();
      act(() => getState().selectFile(file));
      act(() => getState().openConsent());
      act(() => getState().acceptConsent());

      await vi.waitFor(() => {
        expect(getState().step).toBe('processing');
      });

      expect(getState().documentId).toBe('doc-456');
      expect(getState().uploadProgress).toBe(100);
    });

    it('transitions to error on network failure', async () => {
      mockUploadDocument.mockRejectedValue(
        new Error('Network error during upload'),
      );

      const file = createMockFile();
      act(() => getState().selectFile(file));
      act(() => getState().openConsent());
      act(() => getState().acceptConsent());

      await vi.waitFor(() => {
        expect(getState().step).toBe('error');
      });

      expect(getState().error).not.toBeNull();
      expect(getState().error!.type).toBe('network');
      expect(getState().error!.canRetry).toBe(true);
    });

    it('transitions to error on API validation error', async () => {
      mockUploadDocument.mockRejectedValue(
        new ApiError({ error: 'file_too_large', message: 'File exceeds limit' }),
      );

      const file = createMockFile();
      act(() => getState().selectFile(file));
      act(() => getState().openConsent());
      act(() => getState().acceptConsent());

      await vi.waitFor(() => {
        expect(getState().step).toBe('error');
      });

      expect(getState().error!.type).toBe('validation');
      expect(getState().error!.canRetry).toBe(false);
    });

    it('does nothing if not in uploading state', async () => {
      // Force call startUpload directly from idle
      await getState().startUpload();
      expect(mockUploadDocument).not.toHaveBeenCalled();
    });
  });

  describe('startPolling', () => {
    it('transitions to ready when status is ready with chunks > 0', async () => {
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-789',
        status: 'ready',
        filename: 'test.md',
        format: 'markdown',
        language: 'en',
        chunk_count: 5,
        warnings: ['Table skipped on page 2'],
        error_message: null,
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());

      await vi.waitFor(() => {
        expect(getState().step).toBe('ready');
      });

      const state = getState();
      expect(state.result).not.toBeNull();
      expect(state.result!.documentId).toBe('doc-789');
      expect(state.result!.chunkCount).toBe(5);
      expect(state.result!.language).toBe('en');
      expect(state.result!.warnings).toEqual(['Table skipped on page 2']);
    });

    it('transitions to error when status is ready with chunk_count = 0', async () => {
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-789',
        status: 'ready',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: 0,
        warnings: [],
        error_message: null,
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());

      await vi.waitFor(() => {
        expect(getState().step).toBe('error');
      });

      expect(getState().error!.type).toBe('processing');
      expect(getState().error!.message).toContain('No extractable content');
    });

    it('transitions to error when status is ready with chunk_count = null', async () => {
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-789',
        status: 'ready',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());

      await vi.waitFor(() => {
        expect(getState().step).toBe('error');
      });

      expect(getState().error!.type).toBe('processing');
    });

    it('transitions to error when status is failed', async () => {
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-789',
        status: 'failed',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: 'PDF extraction failed: corrupted file',
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());

      await vi.waitFor(() => {
        expect(getState().step).toBe('error');
      });

      expect(getState().error!.type).toBe('processing');
      expect(getState().error!.message).toBe('PDF extraction failed: corrupted file');
    });

    it('transitions to connectivity error after MAX_POLL_FAILURES consecutive failures', async () => {
      mockGetDocumentStatus.mockRejectedValue(new Error('fetch failed'));

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());

      // Wait for the first poll (immediate)
      await vi.waitFor(() => {}, { timeout: 50 });

      // Advance timer for second poll
      await vi.advanceTimersByTimeAsync(100);
      // Advance timer for third poll
      await vi.advanceTimersByTimeAsync(100);

      await vi.waitFor(() => {
        expect(getState().step).toBe('error');
      });

      expect(getState().error!.type).toBe('connectivity');
    });

    it('continues polling when status is processing', async () => {
      let callCount = 0;
      mockGetDocumentStatus.mockImplementation(async () => {
        callCount++;
        if (callCount >= 3) {
          return {
            document_id: 'doc-789',
            status: 'ready' as const,
            filename: 'test.md',
            format: 'markdown',
            language: 'en',
            chunk_count: 3,
            warnings: [],
            error_message: null,
          };
        }
        return {
          document_id: 'doc-789',
          status: 'processing' as const,
          filename: 'test.md',
          format: 'markdown',
          language: null,
          chunk_count: null,
          warnings: [],
          error_message: null,
        };
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());

      // Advance through polls
      await vi.advanceTimersByTimeAsync(300);

      await vi.waitFor(() => {
        expect(getState().step).toBe('ready');
      });

      expect(callCount).toBeGreaterThanOrEqual(3);
    });
  });

  describe('stopPolling', () => {
    it('clears interval and aborts in-flight requests', () => {
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-789',
        status: 'processing',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());
      act(() => getState().stopPolling());

      // After stop, advancing timers should not cause new calls
      const callCountAfterStop = mockGetDocumentStatus.mock.calls.length;
      vi.advanceTimersByTime(500);
      expect(mockGetDocumentStatus.mock.calls.length).toBe(callCountAfterStop);
    });
  });

  describe('reset', () => {
    it('returns all state to initial values', () => {
      // Put store in a non-initial state
      useUploadStore.setState({
        step: 'ready',
        selectedFile: {
          file: createMockFile(),
          name: 'test.md',
          size: 1024,
          format: 'markdown',
        },
        uploadProgress: 100,
        documentId: 'doc-123',
        result: {
          documentId: 'doc-123',
          filename: 'test.md',
          format: 'markdown',
          language: 'en',
          chunkCount: 5,
          warnings: [],
        },
        error: null,
      });

      act(() => getState().reset());

      const state = getState();
      expect(state.step).toBe('idle');
      expect(state.selectedFile).toBeNull();
      expect(state.uploadProgress).toBe(0);
      expect(state.result).toBeNull();
      expect(state.error).toBeNull();
      expect(state.documentId).toBeNull();
    });

    it('stops polling when resetting from processing state', () => {
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-789',
        status: 'processing',
        filename: 'test.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });

      useUploadStore.setState({
        step: 'processing',
        documentId: 'doc-789',
      });

      act(() => getState().startPolling());
      act(() => getState().reset());

      const callCountAfterReset = mockGetDocumentStatus.mock.calls.length;
      vi.advanceTimersByTime(500);
      expect(mockGetDocumentStatus.mock.calls.length).toBe(callCountAfterReset);
      expect(getState().step).toBe('idle');
    });
  });

  describe('Correctness Properties', () => {
    describe('Property 1: Consent Gate', () => {
      it('no upload is triggered unless acceptConsent is called', () => {
        act(() => getState().selectFile(createMockFile()));
        act(() => getState().openConsent());
        // Decline instead of accept
        act(() => getState().declineConsent());

        expect(mockUploadDocument).not.toHaveBeenCalled();
      });

      it('selectFile alone never triggers upload', () => {
        act(() => getState().selectFile(createMockFile()));
        expect(mockUploadDocument).not.toHaveBeenCalled();
      });

      it('openConsent alone never triggers upload', () => {
        act(() => getState().selectFile(createMockFile()));
        act(() => getState().openConsent());
        expect(mockUploadDocument).not.toHaveBeenCalled();
      });
    });

    describe('Property 2: Single Upload Atomicity', () => {
      it('uploading state prevents re-trigger via acceptConsent', () => {
        mockUploadDocument.mockImplementation(
          () => new Promise(() => {}), // Never resolves
        );

        act(() => getState().selectFile(createMockFile()));
        act(() => getState().openConsent());
        act(() => getState().acceptConsent());

        expect(getState().step).toBe('uploading');

        // Attempt to trigger again — acceptConsent guards on consent-pending
        act(() => getState().acceptConsent());
        expect(mockUploadDocument).toHaveBeenCalledTimes(1);
      });

      it('startUpload guards against non-uploading state', async () => {
        useUploadStore.setState({ step: 'idle' });
        await getState().startUpload();
        expect(mockUploadDocument).not.toHaveBeenCalled();
      });
    });

    describe('Property 3: Polling Cleanup', () => {
      it('stopPolling prevents further poll calls', () => {
        mockGetDocumentStatus.mockResolvedValue({
          document_id: 'doc-789',
          status: 'processing',
          filename: 'test.md',
          format: 'markdown',
          language: null,
          chunk_count: null,
          warnings: [],
          error_message: null,
        });

        useUploadStore.setState({
          step: 'processing',
          documentId: 'doc-789',
        });

        act(() => getState().startPolling());
        act(() => getState().stopPolling());

        const calls = mockGetDocumentStatus.mock.calls.length;
        vi.advanceTimersByTime(1000);
        expect(mockGetDocumentStatus.mock.calls.length).toBe(calls);
      });
    });

    describe('Property 4: Reset Completeness', () => {
      it('reset clears ALL state fields to initial values', () => {
        useUploadStore.setState({
          step: 'error',
          selectedFile: {
            file: createMockFile(),
            name: 'x.md',
            size: 100,
            format: 'markdown',
          },
          uploadProgress: 50,
          documentId: 'doc-x',
          result: {
            documentId: 'doc-x',
            filename: 'x.md',
            format: 'markdown',
            language: 'es',
            chunkCount: 2,
            warnings: ['w1'],
          },
          error: { type: 'server', message: 'err', canRetry: true },
        });

        act(() => getState().reset());

        const s = getState();
        expect(s.step).toBe('idle');
        expect(s.selectedFile).toBeNull();
        expect(s.uploadProgress).toBe(0);
        expect(s.result).toBeNull();
        expect(s.error).toBeNull();
        expect(s.documentId).toBeNull();
      });
    });

    describe('Property 5: State Consistency', () => {
      it('idle state has all related fields null', () => {
        const s = getState();
        expect(s.step).toBe('idle');
        expect(s.selectedFile).toBeNull();
        expect(s.documentId).toBeNull();
        expect(s.result).toBeNull();
        expect(s.error).toBeNull();
      });

      it('file-selected state has selectedFile present', () => {
        act(() => getState().selectFile(createMockFile()));
        const s = getState();
        expect(s.step).toBe('file-selected');
        expect(s.selectedFile).not.toBeNull();
      });

      it('uploading state has selectedFile and progress >= 0', () => {
        mockUploadDocument.mockImplementation(
          () => new Promise(() => {}),
        );
        act(() => getState().selectFile(createMockFile()));
        act(() => getState().openConsent());
        act(() => getState().acceptConsent());

        const s = getState();
        expect(s.step).toBe('uploading');
        expect(s.selectedFile).not.toBeNull();
        expect(s.uploadProgress).toBeGreaterThanOrEqual(0);
      });

      it('processing state has documentId present', async () => {
        mockUploadDocument.mockResolvedValue({
          document_id: 'doc-abc',
          status: 'processing',
          filename: 'test.md',
          format: 'markdown',
          language: null,
          chunk_count: null,
          warnings: [],
          error_message: null,
        });
        mockGetDocumentStatus.mockResolvedValue({
          document_id: 'doc-abc',
          status: 'processing',
          filename: 'test.md',
          format: 'markdown',
          language: null,
          chunk_count: null,
          warnings: [],
          error_message: null,
        });

        act(() => getState().selectFile(createMockFile()));
        act(() => getState().openConsent());
        act(() => getState().acceptConsent());

        await vi.waitFor(() => {
          expect(getState().step).toBe('processing');
        });

        expect(getState().documentId).not.toBeNull();
      });

      it('ready state has result with chunkCount > 0', async () => {
        mockGetDocumentStatus.mockResolvedValue({
          document_id: 'doc-789',
          status: 'ready',
          filename: 'test.md',
          format: 'markdown',
          language: 'en',
          chunk_count: 5,
          warnings: [],
          error_message: null,
        });

        useUploadStore.setState({
          step: 'processing',
          documentId: 'doc-789',
        });

        act(() => getState().startPolling());

        await vi.waitFor(() => {
          expect(getState().step).toBe('ready');
        });

        const s = getState();
        expect(s.result).not.toBeNull();
        expect(s.result!.chunkCount).toBeGreaterThan(0);
      });

      it('error state has error present', async () => {
        mockUploadDocument.mockRejectedValue(new Error('Network error during upload'));

        act(() => getState().selectFile(createMockFile()));
        act(() => getState().openConsent());
        act(() => getState().acceptConsent());

        await vi.waitFor(() => {
          expect(getState().step).toBe('error');
        });

        expect(getState().error).not.toBeNull();
      });
    });
  });

  describe('Edge Cases', () => {
    it('double-click on acceptConsent only triggers one upload', () => {
      mockUploadDocument.mockImplementation(
        () => new Promise(() => {}),
      );

      act(() => getState().selectFile(createMockFile()));
      act(() => getState().openConsent());
      act(() => getState().acceptConsent());
      // Second click — state is already 'uploading', not 'consent-pending'
      act(() => getState().acceptConsent());

      expect(mockUploadDocument).toHaveBeenCalledTimes(1);
    });

    it('rapid file changes during consent resets correctly', () => {
      act(() => getState().selectFile(createMockFile('first.md')));
      act(() => getState().openConsent());
      // User selects a new file while consent is pending
      act(() => getState().selectFile(createMockFile('second.txt')));

      expect(getState().step).toBe('file-selected');
      expect(getState().selectedFile!.name).toBe('second.txt');
    });

    it('full workflow: idle → file-selected → consent-pending → uploading → processing → ready', async () => {
      mockUploadDocument.mockResolvedValue({
        document_id: 'doc-flow',
        status: 'processing',
        filename: 'flow.md',
        format: 'markdown',
        language: null,
        chunk_count: null,
        warnings: [],
        error_message: null,
      });
      mockGetDocumentStatus.mockResolvedValue({
        document_id: 'doc-flow',
        status: 'ready',
        filename: 'flow.md',
        format: 'markdown',
        language: 'en',
        chunk_count: 10,
        warnings: [],
        error_message: null,
      });

      const steps: UploadStep[] = [];
      const unsub = useUploadStore.subscribe((s) => {
        if (steps[steps.length - 1] !== s.step) {
          steps.push(s.step);
        }
      });

      act(() => getState().selectFile(createMockFile('flow.md')));
      act(() => getState().openConsent());
      act(() => getState().acceptConsent());

      await vi.waitFor(() => {
        expect(getState().step).toBe('ready');
      });

      unsub();

      expect(steps).toContain('file-selected');
      expect(steps).toContain('consent-pending');
      expect(steps).toContain('uploading');
      expect(steps).toContain('processing');
      expect(steps).toContain('ready');
    });
  });
});
