import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ProcessingStatus } from '@/components/upload/ProcessingStatus';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('ProcessingStatus', () => {
  let startPollingSpy: ReturnType<typeof vi.fn>;
  let stopPollingSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    startPollingSpy = vi.fn();
    stopPollingSpy = vi.fn();
    useUploadStore.setState({
      step: 'idle',
      selectedFile: null,
      uploadProgress: 0,
      result: null,
      error: null,
      documentId: null,
      startPolling: startPollingSpy,
      stopPolling: stopPollingSpy,
    } as any);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('polling lifecycle', () => {
    it('calls startPolling on mount when step is processing', () => {
      useUploadStore.setState({ step: 'processing', documentId: 'doc-1' });
      renderWithProviders(<ProcessingStatus />);
      expect(startPollingSpy).toHaveBeenCalledTimes(1);
    });

    it('does not call startPolling when step is not processing', () => {
      useUploadStore.setState({ step: 'idle' });
      renderWithProviders(<ProcessingStatus />);
      expect(startPollingSpy).not.toHaveBeenCalled();
    });

    it('calls stopPolling on unmount', () => {
      useUploadStore.setState({ step: 'processing', documentId: 'doc-1' });
      const { unmount } = renderWithProviders(<ProcessingStatus />);
      unmount();
      expect(stopPollingSpy).toHaveBeenCalled();
    });

    it('calls stopPolling when transitioning away from processing', () => {
      useUploadStore.setState({ step: 'processing', documentId: 'doc-1' });
      const { unmount } = renderWithProviders(<ProcessingStatus />);
      // Simulate transition to ready
      unmount();
      expect(stopPollingSpy).toHaveBeenCalled();
    });
  });

  describe('processing state', () => {
    it('renders a spinner when step is processing', () => {
      useUploadStore.setState({ step: 'processing', documentId: 'doc-1' });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('shows "Extracting text content..." message during processing', () => {
      useUploadStore.setState({ step: 'processing', documentId: 'doc-1' });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByText('Extracting text content...')).toBeInTheDocument();
    });
  });

  describe('success state (ready)', () => {
    const mockResult = {
      documentId: 'doc-123',
      filename: 'report.pdf',
      format: 'pdf',
      language: 'en',
      chunkCount: 42,
      warnings: [],
    };

    it('renders a success card when step is ready', () => {
      useUploadStore.setState({ step: 'ready', result: mockResult });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByText('Document ready for analysis')).toBeInTheDocument();
    });

    it('displays the filename from result', () => {
      useUploadStore.setState({ step: 'ready', result: mockResult });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByTestId('result-filename')).toHaveTextContent('report.pdf');
    });

    it('displays the detected language from result', () => {
      useUploadStore.setState({ step: 'ready', result: mockResult });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByTestId('result-language')).toHaveTextContent('en');
    });

    it('displays the chunk count from result', () => {
      useUploadStore.setState({ step: 'ready', result: mockResult });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByTestId('result-chunk-count')).toHaveTextContent('42');
    });

    it('displays "Unknown" when language is null', () => {
      useUploadStore.setState({
        step: 'ready',
        result: { ...mockResult, language: null },
      });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByTestId('result-language')).toHaveTextContent('Unknown');
    });
  });

  describe('warnings', () => {
    it('renders warning alerts when result has warnings', () => {
      useUploadStore.setState({
        step: 'ready',
        result: {
          documentId: 'doc-123',
          filename: 'report.pdf',
          format: 'pdf',
          language: 'en',
          chunkCount: 10,
          warnings: ['Complex table skipped on page 3', 'Image caption not extracted'],
        },
      });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.getByText('Complex table skipped on page 3')).toBeInTheDocument();
      expect(screen.getByText('Image caption not extracted')).toBeInTheDocument();
    });

    it('does not render warnings section when there are no warnings', () => {
      useUploadStore.setState({
        step: 'ready',
        result: {
          documentId: 'doc-123',
          filename: 'report.pdf',
          format: 'pdf',
          language: 'en',
          chunkCount: 10,
          warnings: [],
        },
      });
      renderWithProviders(<ProcessingStatus />);
      expect(screen.queryByTestId('warnings-list')).not.toBeInTheDocument();
    });
  });

  describe('renders nothing for other steps', () => {
    it('renders nothing when step is idle', () => {
      useUploadStore.setState({ step: 'idle' });
      const { container } = renderWithProviders(<ProcessingStatus />);
      expect(container.firstChild).toBeNull();
    });

    it('renders nothing when step is uploading', () => {
      useUploadStore.setState({ step: 'uploading' });
      const { container } = renderWithProviders(<ProcessingStatus />);
      expect(container.firstChild).toBeNull();
    });
  });
});
