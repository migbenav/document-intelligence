import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ErrorDisplay } from '@/components/upload/ErrorDisplay';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

describe('ErrorDisplay', () => {
  beforeEach(() => {
    useUploadStore.getState().reset();
  });

  it('renders nothing when step is not error', () => {
    useUploadStore.setState({ step: 'idle', error: null });

    const { container } = renderWithProviders(<ErrorDisplay />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the error message from the store', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'network',
        message: 'Connection failed. Please check your network and try again.',
        canRetry: true,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    expect(
      screen.getByText('Connection failed. Please check your network and try again.'),
    ).toBeInTheDocument();
  });

  it('renders in a destructive alert variant', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'server',
        message: 'Processing failed, please try again.',
        canRetry: true,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveClass('border-destructive/50');
  });

  it('shows the "Try again" button when error.canRetry is true', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'network',
        message: 'Connection failed. Please check your network and try again.',
        canRetry: true,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    expect(screen.getByTestId('retry-button')).toBeInTheDocument();
    expect(screen.getByTestId('retry-button')).toHaveTextContent('Try again');
  });

  it('hides the "Try again" button when error.canRetry is false', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'validation',
        message: 'This file format is not supported.',
        canRetry: false,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    expect(screen.queryByTestId('retry-button')).not.toBeInTheDocument();
  });

  it('always shows the "Start over" button', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'processing',
        message: 'No extractable content was found in this document.',
        canRetry: false,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    expect(screen.getByTestId('start-over-button')).toBeInTheDocument();
    expect(screen.getByTestId('start-over-button')).toHaveTextContent('Start over');
  });

  it('calls store.reset() when "Start over" is clicked', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'server',
        message: 'Processing failed, please try again.',
        canRetry: true,
      },
      selectedFile: {
        file: new File(['test'], 'test.txt', { type: 'text/plain' }),
        name: 'test.txt',
        size: 100,
        format: 'plain_text',
      },
    });

    renderWithProviders(<ErrorDisplay />);

    fireEvent.click(screen.getByTestId('start-over-button'));

    const state = useUploadStore.getState();
    expect(state.step).toBe('idle');
    expect(state.error).toBeNull();
    expect(state.selectedFile).toBeNull();
    expect(state.documentId).toBeNull();
  });

  it('re-invokes the upload when "Try again" is clicked', () => {
    const mockFile = new File(['content'], 'doc.pdf', { type: 'application/pdf' });

    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'network',
        message: 'Connection failed. Please check your network and try again.',
        canRetry: true,
      },
      selectedFile: {
        file: mockFile,
        name: 'doc.pdf',
        size: 1000,
        format: 'pdf',
      },
    });

    // Spy on startUpload
    const startUploadSpy = vi.fn().mockResolvedValue(undefined);
    useUploadStore.setState({ startUpload: startUploadSpy });

    renderWithProviders(<ErrorDisplay />);

    fireEvent.click(screen.getByTestId('retry-button'));

    // After retry, the step should be set to 'uploading' and startUpload called
    const state = useUploadStore.getState();
    expect(state.step).toBe('uploading');
    expect(state.error).toBeNull();
    expect(startUploadSpy).toHaveBeenCalled();
  });

  it('does not display error.type to the user', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'connectivity',
        message: 'Unable to reach the server. Please check your connection.',
        canRetry: false,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    // error.type should not appear anywhere in the rendered output
    expect(screen.queryByText('connectivity')).not.toBeInTheDocument();
    expect(screen.queryByText('network')).not.toBeInTheDocument();
    expect(screen.queryByText('server')).not.toBeInTheDocument();
    expect(screen.queryByText('validation')).not.toBeInTheDocument();
    expect(screen.queryByText('processing')).not.toBeInTheDocument();
  });

  it('does not expose HTTP status codes or technical details', () => {
    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'server',
        message: 'Processing failed, please try again.',
        canRetry: true,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    const container = screen.getByTestId('error-display');
    const textContent = container.textContent ?? '';

    // Should not contain status codes or technical patterns
    expect(textContent).not.toMatch(/\b(4\d{2}|5\d{2})\b/); // No HTTP status codes
    expect(textContent).not.toMatch(/stack\s*trace/i);
    expect(textContent).not.toMatch(/Error:/);
    expect(textContent).not.toMatch(/at\s+\w+\s*\(/); // No stack trace frames
  });

  it('only displays the error.message string', () => {
    const userFacingMessage = 'Unable to reach the server. Please check your connection.';

    useUploadStore.setState({
      step: 'error',
      error: {
        type: 'connectivity',
        message: userFacingMessage,
        canRetry: false,
      },
    });

    renderWithProviders(<ErrorDisplay />);

    const messageEl = screen.getByTestId('error-message');
    expect(messageEl).toHaveTextContent(userFacingMessage);
  });
});
