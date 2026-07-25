import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import App from '@/App';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';
import type { UploadResponse, StatusResponse } from '@/types/api';

// --- Mock the API module ---
vi.mock('@/api/documents', () => ({
  uploadDocument: vi.fn(),
  getDocumentStatus: vi.fn(),
  ApiError: class ApiError extends Error {
    public readonly error: string;
    constructor(response: { message: string; error: string }) {
      super(response.message);
      this.name = 'ApiError';
      this.error = response.error;
    }
  },
}));

import { uploadDocument, getDocumentStatus } from '@/api/documents';

const mockUploadDocument = vi.mocked(uploadDocument);
const mockGetDocumentStatus = vi.mocked(getDocumentStatus);

// --- Helpers ---

function renderApp() {
  return render(
    <TranslationProvider>
      <App />
    </TranslationProvider>,
  );
}

function createTestFile(name = 'test-document.md', content = 'Hello world') {
  return new File([content], name, { type: 'text/markdown' });
}

function createUploadResponse(overrides: Partial<UploadResponse> = {}): UploadResponse {
  return {
    document_id: 'test-doc-123',
    status: 'processing',
    filename: 'test-document.md',
    format: 'markdown',
    language: null,
    chunk_count: null,
    warnings: [],
    error_message: null,
    ...overrides,
  };
}

function createStatusResponse(overrides: Partial<StatusResponse> = {}): StatusResponse {
  return {
    document_id: 'test-doc-123',
    status: 'ready',
    filename: 'test-document.md',
    format: 'markdown',
    language: 'en',
    chunk_count: 5,
    warnings: [],
    error_message: null,
    ...overrides,
  };
}

// --- Tests ---

describe('Upload Flow Integration', () => {
  beforeEach(() => {
    useUploadStore.getState().reset();
    mockUploadDocument.mockReset();
    mockGetDocumentStatus.mockReset();
  });

  afterEach(() => {
    useUploadStore.getState().reset();
  });

  it('renders the upload page with upload zone in idle state', () => {
    renderApp();
    expect(screen.getByText('Drag and drop your file here, or click to browse')).toBeInTheDocument();
    expect(screen.getByText('Supported formats: .md, .txt, .pdf')).toBeInTheDocument();
  });

  it('shows file info and upload button after file selection', async () => {
    renderApp();

    const file = createTestFile();
    const input = screen.getByTestId('file-input');
    await act(async () => {
      await userEvent.upload(input, file);
    });

    expect(screen.getByText('test-document.md')).toBeInTheDocument();
    expect(screen.getByTestId('upload-button')).toBeInTheDocument();
    expect(screen.getByTestId('upload-button')).toHaveTextContent('Upload and Analyze');
  });

  it('opens consent dialog when upload button is clicked', async () => {
    renderApp();

    const file = createTestFile();
    const input = screen.getByTestId('file-input');
    await act(async () => {
      await userEvent.upload(input, file);
    });

    await act(async () => {
      await userEvent.click(screen.getByTestId('upload-button'));
    });

    expect(screen.getByText('External Processing Notice')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'I understand, proceed' })).toBeInTheDocument();
  });

  it('completes full flow: file select → consent → upload → poll → ready', async () => {
    // Mock upload to resolve with 202 response
    mockUploadDocument.mockImplementation((_file, options) => {
      // Simulate progress
      if (options?.onProgress) {
        options.onProgress(50);
        options.onProgress(100);
      }
      return Promise.resolve(createUploadResponse());
    });

    // Mock status polling: first call returns processing, second returns ready
    let pollCount = 0;
    mockGetDocumentStatus.mockImplementation(() => {
      pollCount++;
      if (pollCount === 1) {
        return Promise.resolve(createStatusResponse({ status: 'processing', language: null, chunk_count: null }));
      }
      return Promise.resolve(createStatusResponse({
        status: 'ready',
        language: 'en',
        chunk_count: 5,
        warnings: ['Complex table skipped on page 3'],
      }));
    });

    renderApp();

    // Step 1: Select file
    const file = createTestFile();
    const input = screen.getByTestId('file-input');
    await act(async () => {
      await userEvent.upload(input, file);
    });

    expect(screen.getByText('test-document.md')).toBeInTheDocument();

    // Step 2: Click upload button → opens consent dialog
    await act(async () => {
      await userEvent.click(screen.getByTestId('upload-button'));
    });

    expect(screen.getByText('External Processing Notice')).toBeInTheDocument();

    // Step 3: Accept consent → triggers upload
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'I understand, proceed' }));
    });

    // Step 4: Wait for the full flow to reach ready state (polling at 2s intervals)
    await waitFor(
      () => {
        expect(useUploadStore.getState().step).toBe('ready');
      },
      { timeout: 10000 },
    );

    // Verify success UI
    expect(screen.getByText('Document ready for analysis')).toBeInTheDocument();
    expect(screen.getByTestId('result-filename')).toHaveTextContent('test-document.md');
    expect(screen.getByTestId('result-language')).toHaveTextContent('en');
    expect(screen.getByTestId('result-chunk-count')).toHaveTextContent('5');
    expect(screen.getByText('Complex table skipped on page 3')).toBeInTheDocument();
  }, 15000);

  it('shows error display on upload failure and allows start over', async () => {
    // Mock upload to reject with an API error
    const { ApiError } = await import('@/api/documents');
    mockUploadDocument.mockRejectedValue(
      new ApiError({ message: 'This file format is not supported.', error: 'unsupported_format' }),
    );

    renderApp();

    // Select file
    const file = createTestFile('document.md', 'content');
    const input = screen.getByTestId('file-input');
    await act(async () => {
      await userEvent.upload(input, file);
    });

    // Click upload → consent
    await act(async () => {
      await userEvent.click(screen.getByTestId('upload-button'));
    });

    // Accept consent
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'I understand, proceed' }));
    });

    // Wait for error state
    await waitFor(() => {
      expect(useUploadStore.getState().step).toBe('error');
    });

    // Error display is shown
    expect(screen.getByTestId('error-display')).toBeInTheDocument();
    expect(screen.getByTestId('error-message')).toHaveTextContent('This file format is not supported.');

    // Click start over
    await act(async () => {
      await userEvent.click(screen.getByTestId('start-over-button'));
    });

    // Back to idle state with upload zone
    expect(useUploadStore.getState().step).toBe('idle');
    expect(screen.getByText('Drag and drop your file here, or click to browse')).toBeInTheDocument();
  });

  it('declines consent and returns to file-selected state', async () => {
    renderApp();

    // Select file
    const file = createTestFile();
    const input = screen.getByTestId('file-input');
    await act(async () => {
      await userEvent.upload(input, file);
    });

    // Click upload → consent
    await act(async () => {
      await userEvent.click(screen.getByTestId('upload-button'));
    });

    expect(screen.getByText('External Processing Notice')).toBeInTheDocument();

    // Decline consent
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    });

    // Back to file-selected: upload button should reappear
    expect(useUploadStore.getState().step).toBe('file-selected');
    await waitFor(() => {
      expect(screen.getByTestId('upload-button')).toBeInTheDocument();
    });
  });

  it('shows upload zone on error with validation type for re-selection', async () => {
    // Mock upload to reject with a validation error
    const { ApiError } = await import('@/api/documents');
    mockUploadDocument.mockRejectedValue(
      new ApiError({ message: 'This file format is not supported.', error: 'unsupported_format' }),
    );

    renderApp();

    // Select file and go through the flow to get a validation error
    const file = createTestFile();
    const input = screen.getByTestId('file-input');
    await act(async () => {
      await userEvent.upload(input, file);
    });

    await act(async () => {
      await userEvent.click(screen.getByTestId('upload-button'));
    });

    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'I understand, proceed' }));
    });

    await waitFor(() => {
      expect(useUploadStore.getState().step).toBe('error');
      expect(useUploadStore.getState().error?.type).toBe('validation');
    });

    // Validation error should show both the error display AND the upload zone for re-selection
    expect(screen.getByTestId('error-display')).toBeInTheDocument();
    expect(screen.getByText('Drag and drop your file here, or click to browse')).toBeInTheDocument();
  });
});
